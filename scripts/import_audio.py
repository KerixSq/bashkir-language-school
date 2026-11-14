"""Import licensed, already transcribed audio; never performs speech recognition."""

import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audio_duration(path):
    if not path.is_file() or not 0 < path.stat().st_size <= 256 * 1024 * 1024:
        raise ValueError('Audio must be a nonempty file up to 256 MiB')
    if path.suffix.lower() == '.wav':
        with wave.open(str(path), 'rb') as audio:
            if audio.getcomptype() != 'NONE' or audio.getnchannels() not in (1, 2):
                raise ValueError('Expected mono/stereo uncompressed PCM WAV')
            frames = audio.getnframes()
            remaining = frames
            while remaining:
                count = min(remaining, 32768)
                if (
                    len(audio.readframes(count))
                    != count * audio.getnchannels() * audio.getsampwidth()
                ):
                    raise ValueError('Truncated WAV')
                remaining -= count
            duration = frames / audio.getframerate()
    elif path.suffix.lower() == '.mp3':
        probe = shutil.which('ffprobe')
        if not probe:
            raise ValueError('MP3 needs an existing ffprobe; use PCM WAV otherwise')
        result = subprocess.run(
            [
                probe,
                '-v',
                'error',
                '-show_entries',
                'format=duration:stream=codec_name,codec_type',
                '-of',
                'json',
                str(path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        if not any(
            s.get('codec_name') == 'mp3' and s.get('codec_type') == 'audio' for s in streams
        ):
            raise ValueError('File does not contain MP3 audio')
        duration = float(data['format']['duration'])
    else:
        raise ValueError('Only WAV and MP3 are supported')
    if not math.isfinite(duration) or not 0 < duration <= 8 * 3600:
        raise ValueError('Invalid audio duration')
    return duration


def read_segments(path, duration):
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError('Annotation must be a JSON/CSV file up to 2 MB')
    with path.open(encoding='utf-8-sig', newline='') as stream:
        if path.suffix.lower() == '.json':
            data = json.load(stream)
        elif path.suffix.lower() == '.csv':
            data = list(csv.DictReader(stream))
        else:
            raise ValueError('Annotation must be JSON or CSV')
    if not isinstance(data, list) or not 1 <= len(data) <= 1000:
        raise ValueError('Expected 1–1000 segments')
    result, seen = [], set()
    for row in data:
        if (
            not isinstance(row, dict)
            or not {'time_start', 'time_end', 'text_ba', 'translation', 'lang_pair'} <= row.keys()
        ):
            raise ValueError('Missing segment fields')
        start, end = float(row['time_start']), float(row['time_end'])
        if (
            any(isinstance(row[k], bool) for k in ('time_start', 'time_end'))
            or not all(math.isfinite(n) for n in (start, end))
            or not 0 <= start < end <= duration
        ):
            raise ValueError('Invalid timestamp range')
        if row['lang_pair'] not in ('ba-ru', 'ba-kk'):
            raise ValueError('Unsupported language pair')
        for key, limit in (('text_ba', 5000), ('translation', 500)):
            if (
                not isinstance(row[key], str)
                or not row[key].strip()
                or len(row[key]) > limit
                or any(ord(c) < 32 and c not in '\n\t\r' for c in row[key])
            ):
                raise ValueError('Invalid segment text')
        item = {key: row[key] for key in ('text_ba', 'translation', 'lang_pair')}
        item.update(time_start=start, time_end=end)
        key = (start, end, row['lang_pair'])
        if key in seen:
            raise ValueError('Duplicate interval/language pair')
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda row: (row['time_start'], row['time_end'], row['lang_pair']))


def plan(audio, annotation, title, license_name):
    if not title.strip() or not license_name.strip() or len(title) > 500 or len(license_name) > 500:
        raise ValueError('Explicit title and license required (up to 500 characters)')
    duration = audio_duration(audio)
    rows = read_segments(annotation, duration)
    sha = digest(audio)
    url = '/web/assets/original-audio/' + sha + audio.suffix.lower()
    identity = json.dumps([sha, rows, title, license_name], ensure_ascii=False, sort_keys=True)
    source_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'bashkir-original-audio:' + identity))
    source = {'id': source_id, 'kind': 'audio', 'title': title, 'license': license_name, 'url': url}
    fragments, identities = [], {}
    for row in rows:
        key = (row['time_start'], row['time_end'], row['text_ba'])
        if key not in identities:
            identities[key] = len(identities) + 1
        position = identities[key]
        fid = uuid.uuid5(uuid.UUID(source_id), str(position))
        fragments.append(
            {
                **row,
                'id': str(fid),
                'pair_id': str(uuid.uuid5(fid, row['lang_pair'])),
                'position': position,
            }
        )
    if (
        len(
            json.dumps({'p_source': source, 'p_segments': fragments}, ensure_ascii=False).encode(
                'utf-8'
            )
        )
        > 900_000
    ):
        raise ValueError('Annotation payload exceeds 900 kB; split into smaller source annotations')
    return source, fragments


def import_audio(db, audio, annotation, title, license_name, output_dir=None):
    source, rows = plan(audio, annotation, title, license_name)
    output_dir = output_dir or ROOT / 'web/assets/original-audio'
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / Path(source['url']).name
    expected = target.stem
    if target.exists():
        if digest(target) != expected:
            raise ValueError('Existing content-addressed asset is corrupt; not overwritten')
    else:
        with tempfile.NamedTemporaryFile(dir=output_dir, delete=False) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copyfile(audio, temporary)
            if digest(temporary) != expected:
                raise ValueError('Audio changed during copy')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    db.rpc('import_audio_fragments', {'p_source': source, 'p_segments': rows}).execute()
    return source, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--segments', type=Path, required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--license', required=True)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.dry_run:
        _, rows = plan(args.audio, args.segments, args.title, args.license)
        print(f'Validated {len(rows)} audio segments; no database/files changed')
        return
    if not args.env_file or not args.env_file.is_file():
        parser.error('--env-file must explicitly select the target environment')
    if __package__:
        from .settings import load_settings, read_env
    else:
        from settings import load_settings, read_env
    from supabase import create_client

    # General developer settings allow ambient overrides; a write importer must not.
    values = (
        load_settings(args.env_file.resolve())
        if args.env_file.name == '.env.docker'
        else read_env(args.env_file.resolve())
    )
    url = values.get('SUPABASE_URL')
    key = values.get('SUPABASE_SECRET_KEY') or values.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        parser.error('Selected env must contain its own API URL and server key')
    source, rows = import_audio(
        create_client(url, key), args.audio, args.segments, args.title, args.license
    )
    print(f'Imported {len(rows)} segments; rebuild app to serve {source["url"]}')


if __name__ == '__main__':
    main()
