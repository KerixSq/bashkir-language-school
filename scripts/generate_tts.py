"""Generate static Bashkir WAVs from the committed BGPU deck, never user input.

No PyTorch import or network access for --dry-run and already generated audio.
The pinned model comes from Silero's official registry (MIT LICENSE_CIS).
"""

import argparse
import array
import hashlib
import json
import re
import sys
import unicodedata
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / 'web/assets/learning-deck.json'
MODEL = 'v5_cis_base_nostress'
MODEL_URL = f'https://models.silero.ai/models/tts/ru/{MODEL}.pt'
MODEL_SHA256 = '0405777e332906f0644e08a680f7cfdc2137ea864090079c1fdd30a43c1b8761'
VOICES = ('bak_aigul', 'bak_alfia', 'bak_alfia2', 'bak_miyau', 'bak_ramilia')
RATE = 24000
NOTICE = 'Синтезированная речь, требует оценки носителем'
ALLOWED = re.compile(r"""[а-яёәөүҙҡңғһҫ0-9 .,!?;:…()«»"'–—\-]+""")


def normalize(text):
    if not isinstance(text, str) or not text or len(text) > 500:
        raise ValueError('Phrase must contain 1–500 characters')
    text = ' '.join(unicodedata.normalize('NFC', text).lower().split())
    if not ALLOWED.fullmatch(text) or not re.search('[а-яёәөүҙҡңғһҫ]', text):
        raise ValueError('Unsupported characters in corpus phrase')
    return text


def phrase_id(text, voice):
    if voice not in VOICES:
        raise ValueError('Only verified Bashkir speakers are allowed')
    payload = json.dumps([MODEL, MODEL_SHA256, voice, normalize(text)], ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def plan(items, voice, limit=None):
    grouped = {}
    for row in items:
        if row.get('lang_pair') not in ('ba-ru', 'ba-kk'):
            raise ValueError('Unexpected corpus language pair')
        try:
            text = normalize(row['text_ba'])
        except ValueError:
            continue  # Slash alternatives / unsupported corpus text stay text-only.
        entry = grouped.setdefault(
            text,
            {
                'id': phrase_id(text, voice),
                'text': text,
                'lang': 'ba',
                'voice': voice,
                'model': MODEL,
                'source_ids': [],
                'notice': NOTICE,
            },
        )
        entry['source_ids'].append(row['id'])
    entries = sorted(grouped.values(), key=lambda entry: entry['id'])
    return entries if limit is None else entries[:limit]


def safe_file(directory, name):
    if not re.fullmatch(r'[0-9a-f]{64}\.wav|manifest\.json', name):
        raise ValueError('Unsafe audio filename')
    target = directory / name
    if target.resolve().parent != directory.resolve():
        raise ValueError('Audio path escapes output directory')
    return target


def validate_wav(path):
    if not 1000 < path.stat().st_size <= RATE * 2 * 30 + 100:
        raise ValueError(f'Invalid WAV size: {path.name}')
    with wave.open(str(path), 'rb') as audio:
        if (
            audio.getnchannels() != 1
            or audio.getsampwidth() != 2
            or audio.getframerate() != RATE
            or not 0.05 <= audio.getnframes() / RATE <= 30
        ):
            raise ValueError(f'Invalid WAV format: {path.name}')
        frames = audio.readframes(audio.getnframes())
        if len(frames) != audio.getnframes() * 2 or not any(frames):
            raise ValueError(f'Truncated or silent WAV: {path.name}')


def file_hash(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def load_model(path, download=False):
    if not path.exists():
        if not download:
            raise ValueError('Model missing; provide --model-file or --download-model')
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.download')
        urllib.request.urlretrieve(MODEL_URL, temp)
        if file_hash(temp) != MODEL_SHA256:
            raise ValueError('Official model checksum changed; review provenance before loading')
        temp.replace(path)
    if file_hash(path) != MODEL_SHA256:
        raise ValueError('Model checksum does not match the verified official release')
    import torch

    torch.set_num_threads(4)
    model = torch.package.PackageImporter(str(path)).load_pickle('tts_models', 'model')
    model.to(torch.device('cpu'))
    return model, torch


def generate(entries, output, model_file, voice, download=False):
    output.mkdir(parents=True, exist_ok=True)
    model = torch = None
    generated = 0
    for entry in entries:
        path = safe_file(output, entry['id'] + '.wav')
        if not path.exists():
            if model is None:
                model, torch = load_model(model_file, download)
                if voice not in model.speakers:
                    raise ValueError('Selected Bashkir voice absent from model')
            with torch.inference_mode():
                audio = model.apply_tts(text=entry['text'], speaker=voice, sample_rate=RATE)
            if not torch.isfinite(audio).all() or not 0.05 <= audio.numel() / RATE <= 30:
                raise ValueError('Invalid generated audio')
            samples = array.array('h', audio.clamp(-1, 1).mul(32767).to(torch.int16).tolist())
            if sys.byteorder != 'little':
                samples.byteswap()
            temp = path.with_suffix('.tmp')
            with wave.open(str(temp), 'wb') as target:
                target.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                target.writeframes(samples.tobytes())
            validate_wav(temp)
            temp.replace(path)
            generated += 1
        validate_wav(path)
        entry['path'] = 'assets/audio/' + path.name
        entry['sha256'] = file_hash(path)
        print(f'OK {entry["id"][:12]}', flush=True)
    manifest = {
        'version': 1,
        'model': MODEL,
        'model_sha256': MODEL_SHA256,
        'model_url': MODEL_URL,
        'voice': voice,
        'sample_rate': RATE,
        'license': 'MIT (Silero LICENSE_CIS)',
        'review_status': 'requires_native_review',
        'notice': NOTICE,
        'entries': entries,
    }
    target = safe_file(output, 'manifest.json')
    temp = target.with_suffix('.json.tmp')
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(target)
    return generated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--voice', choices=VOICES, default='bak_aigul')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'web/assets/audio')
    parser.add_argument('--model-file', type=Path, default=ROOT / '.cache/tts' / (MODEL + '.pt'))
    parser.add_argument('--download-model', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    if DECK.stat().st_size > 3_000_000:
        raise ValueError('Corpus exceeds 3 MB')
    entries = plan(json.loads(DECK.read_text(encoding='utf-8'))['items'], args.voice, args.limit)
    if args.dry_run:
        print(f'DRY RUN: {len(entries)} unique Bashkir phrases, {MODEL}, {args.voice}')
        return
    count = generate(entries, args.output_dir, args.model_file, args.voice, args.download_model)
    print(f'Generated {count}; manifest covers {len(entries)} unique phrases')


if __name__ == '__main__':
    main()
