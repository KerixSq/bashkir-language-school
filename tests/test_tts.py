import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.generate_tts import (
    DECK,
    MODEL_SHA256,
    file_hash,
    generate,
    load_model,
    main,
    normalize,
    phrase_id,
    plan,
    safe_file,
    validate_wav,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / 'web/assets/audio'
ROWS = json.loads(DECK.read_text(encoding='utf-8'))['items']


class TTSTests(unittest.TestCase):
    def test_hash_and_normalization_are_stable(self):
        text = ROWS[0]['text_ba']
        self.assertEqual(phrase_id(text, 'bak_aigul'), phrase_id('  ' + text.upper(), 'bak_aigul'))
        self.assertNotEqual(phrase_id(text, 'bak_aigul'), phrase_id(text, 'bak_alfia'))
        self.assertEqual(normalize('  ' + text + '\n'), text.lower())
        self.assertEqual(len(phrase_id(text, 'bak_aigul')), 64)

    def test_filter_and_deduplication_use_only_corpus(self):
        entries = plan([ROWS[0], ROWS[0], dict(ROWS[0], text_ba='<script>')], 'bak_aigul')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['text'], normalize(ROWS[0]['text_ba']))
        for text in ('../secret', '<script>', ' ', 'a' * 501, '123', '\x00'):
            with self.assertRaises(ValueError):
                normalize(text)
        with self.assertRaises(ValueError):
            phrase_id(ROWS[0]['text_ba'], 'russian_voice')
        with self.assertRaises(ValueError):
            plan([dict(ROWS[0], lang_pair='ru-en')], 'bak_aigul')

    def test_audio_paths_cannot_escape_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ('../secret.wav', '/secret.wav', 'https://host/file.wav', 'x.wav'):
                with self.assertRaises(ValueError):
                    safe_file(Path(directory), path)

    def test_committed_audio_has_provenance_and_decodes(self):
        manifest = json.loads((AUDIO / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['model_sha256'], MODEL_SHA256)
        self.assertEqual(manifest['review_status'], 'requires_native_review')
        self.assertGreaterEqual(len(manifest['entries']), 40)
        corpus = {row['id']: row['text_ba'] for row in ROWS}
        identifiers = set()
        for entry in manifest['entries']:
            self.assertEqual(entry['id'], phrase_id(entry['text'], entry['voice']))
            self.assertNotIn(entry['id'], identifiers)
            identifiers.add(entry['id'])
            for source in entry['source_ids']:
                self.assertEqual(normalize(corpus[source]), entry['text'])
            audio = ROOT / 'web' / entry['path']
            validate_wav(audio)
            self.assertEqual(file_hash(audio), entry['sha256'])

    def test_existing_audio_skips_model_and_keeps_bytes(self):
        manifest = json.loads((AUDIO / 'manifest.json').read_text(encoding='utf-8'))
        entry = manifest['entries'][0]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            target = output / (entry['id'] + '.wav')
            source = (ROOT / 'web' / entry['path']).read_bytes()
            target.write_bytes(source)
            with (
                patch(
                    'scripts.generate_tts.load_model', side_effect=AssertionError('No model needed')
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(generate([entry], output, output / 'missing.pt', 'bak_aigul'), 0)
            self.assertEqual(target.read_bytes(), source)
            target.write_bytes(b'broken')
            with self.assertRaises(ValueError):
                validate_wav(target)

    def test_dry_run_needs_no_model_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'not-created'
            with contextlib.redirect_stdout(io.StringIO()):
                main(['--dry-run', '--limit', '3', '--output-dir', str(output)])
            self.assertFalse(output.exists())
            untrusted = Path(directory) / 'wrong.pt'
            untrusted.write_bytes(b'untrusted pickle')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                load_model(untrusted)
