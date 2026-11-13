import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_docker_file_overrides_stale_cloud_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.docker'
            path.write_text(
                'ANON_KEY=local-public\nSERVICE_ROLE_KEY=local-server\n', encoding='utf-8'
            )
            with patch.dict(
                os.environ,
                {
                    'SUPABASE_URL': 'https://cloud.supabase.co',
                    'SUPABASE_SECRET_KEY': 'cloud-secret',
                },
            ):
                values = load_settings(path)
            self.assertEqual(values['SUPABASE_URL'], 'http://127.0.0.1:54321')
            self.assertEqual(values['SUPABASE_SECRET_KEY'], 'local-server')
            self.assertEqual(values['SUPABASE_PUBLIC_KEY'], 'local-public')

    def test_missing_docker_file_fails_without_cloud_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                load_settings(Path(directory) / '.env.docker')

    def test_incomplete_docker_file_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env.docker'
            path.write_text('ANON_KEY=public\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_settings(path)
