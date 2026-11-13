import base64
import hashlib
import hmac
import json
import unittest
from pathlib import Path

from scripts.create_docker_env import jwt

ROOT = Path(__file__).resolve().parents[1]


class DockerSetupTests(unittest.TestCase):
    def test_jwt_signature_and_claims(self):
        token = jwt('a' * 64, 'anon')
        head, body, signature = token.split('.')
        expected = base64.urlsafe_b64encode(
            hmac.new(b'a' * 64, f'{head}.{body}'.encode(), hashlib.sha256).digest()
        ).decode().rstrip('=')
        self.assertEqual(signature, expected)
        claims = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        self.assertEqual(claims['role'], 'anon')
        self.assertGreater(claims['exp'], claims['iat'])

    def test_app_uses_supabase_compatible_paths(self):
        nginx = (ROOT / 'docker/nginx.conf').read_text(encoding='utf-8')
        self.assertIn('location /rest/v1/', nginx)
        self.assertIn('location /auth/v1/', nginx)
        self.assertIn('location /web/', nginx)
        init = (ROOT / 'docker/init_roles.sh').read_text(encoding='utf-8')
        self.assertIn('CREATE ROLE service_role NOLOGIN BYPASSRLS', init)
        self.assertIn('CREATE OR REPLACE FUNCTION auth.uid()', init)

    def test_database_is_not_published_to_host(self):
        compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
        db_block = compose.split('  db:', 1)[1].split('\n  rest:', 1)[0]
        self.assertNotIn('    ports:', db_block)
        self.assertIn('127.0.0.1:54321:80', compose)
        self.assertIn('postgres_data:/var/lib/postgresql/data', compose)


if __name__ == '__main__':
    unittest.main()
