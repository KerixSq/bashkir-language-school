import contextlib
import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from audio_fixture import audio_fixture

from scripts.import_audio import audio_duration, import_audio, main, plan, read_segments


class AudioImportTests(unittest.TestCase):
    def test_published_asset_is_readable_by_web_server(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            audio, annotation, _ = audio_fixture(folder)
            source, _ = import_audio(
                Mock(), audio, annotation, 'Technical', 'CC0', folder / 'public'
            )
            target = folder / 'public' / Path(source['url']).name
            self.assertEqual(target.stat().st_mode & 0o444, 0o444)
            target.chmod(0o600)
            import_audio(Mock(), audio, annotation, 'Technical', 'CC0', folder / 'public')
            self.assertEqual(target.stat().st_mode & 0o444, 0o444)

    def test_audio_migration_matches_fresh_rpc_and_assignment(self):
        root = Path(__file__).resolve().parents[1]
        fresh = (root / 'sql/logic.sql').read_text(encoding='utf-8')
        migration = (root / 'sql/migrations/20261114_stage13_original_audio.sql').read_text(
            encoding='utf-8'
        )
        for function in ('get_next_fragment', 'import_audio_fragments'):
            pattern = rf'create or replace function public.{function}\(.*?\n\$\$;'
            self.assertEqual(
                re.search(pattern, fresh, re.S).group(), re.search(pattern, migration, re.S).group()
            )

    def test_oversized_rpc_payload_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            audio, annotation, rows = audio_fixture(Path(directory))
            large = [
                {**rows[0], 'time_start': i / 200, 'time_end': (i + 1) / 200, 'text_ba': 'T' * 4900}
                for i in range(200)
            ]
            annotation.write_text(json.dumps(large), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '900 kB'):
                plan(audio, annotation, 'Technical', 'CC0')

    def test_explicit_env_does_not_inherit_another_server_key(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            audio, annotation, _ = audio_fixture(folder)
            env = folder / 'target.env'
            env.write_text('SUPABASE_URL=http://127.0.0.1:54321\n', encoding='utf-8')
            arguments = [
                'import_audio',
                '--audio',
                str(audio),
                '--segments',
                str(annotation),
                '--title',
                'Technical',
                '--license',
                'CC0',
                '--env-file',
                str(env),
            ]
            with (
                patch('sys.argv', arguments),
                patch.dict(os.environ, {'SUPABASE_SECRET_KEY': 'stale-key-must-not-be-used'}),
                patch(
                    'supabase.create_client', side_effect=AssertionError('Must not use ambient key')
                ),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main()
            self.assertEqual(error.exception.code, 2)

    def test_bilingual_interval_shares_fragment_not_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            audio, annotation, rows = audio_fixture(Path(directory))
            rows.append(
                {
                    **rows[0],
                    'lang_pair': 'ba-kk',
                    'translation': 'TECHNICAL FIXTURE NOT A KAZAKH TRANSLATION',
                }
            )
            annotation.write_text(json.dumps(rows), encoding='utf-8')
            _, segments = plan(audio, annotation, 'Technical', 'CC0')
            self.assertEqual(segments[0]['id'], segments[1]['id'])
            self.assertNotEqual(segments[0]['pair_id'], segments[1]['pair_id'])

    def test_wav_json_csv_and_repeat_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            audio, annotation, rows = audio_fixture(folder)
            self.assertEqual(audio_duration(audio), 2)
            planned = plan(audio, annotation, 'Technical tone', 'CC0 test')
            self.assertEqual(planned, plan(audio, annotation, 'Technical tone', 'CC0 test'))
            csv_file = folder / 'segments.csv'
            with csv_file.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            self.assertEqual(read_segments(csv_file, 2), read_segments(annotation, 2))

    def test_bad_times_duplicates_and_languages(self):
        with tempfile.TemporaryDirectory() as directory:
            _, annotation, rows = audio_fixture(Path(directory))
            for changes in (
                {'time_start': -1},
                {'time_end': 3},
                {'time_end': 0.1},
                {'time_end': 'NaN'},
                {'time_start': True},
                {'lang_pair': 'ru-en'},
                {'translation': ''},
            ):
                annotation.write_text(json.dumps([{**rows[0], **changes}]), encoding='utf-8')
                with self.assertRaises((ValueError, TypeError)):
                    read_segments(annotation, 2)
            annotation.write_text(json.dumps(rows * 2), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                read_segments(annotation, 2)

    def test_truncated_wav_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            audio, annotation, _ = audio_fixture(folder)
            source, _ = plan(audio, annotation, 'Test', 'CC0')
            output = folder / 'public'
            output.mkdir()
            target = output / Path(source['url']).name
            target.write_bytes(b'corrupt existing asset')
            with self.assertRaisesRegex(ValueError, 'corrupt'):
                import_audio(None, audio, annotation, 'Test', 'CC0', output)
            audio.write_bytes(audio.read_bytes()[:-100])
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                audio_duration(audio)

    @unittest.skipUnless(
        shutil.which('ffmpeg') and shutil.which('ffprobe'),
        'Existing FFmpeg/ffprobe required for MP3 conversion',
    )
    def test_real_mp3_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            audio, _, _ = audio_fixture(folder)
            mp3 = folder / 'tone.mp3'
            subprocess.run(
                [shutil.which('ffmpeg'), '-v', 'error', '-i', str(audio), str(mp3)],
                check=True,
                timeout=30,
            )
            self.assertGreater(audio_duration(mp3), 1.9)
