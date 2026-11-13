"""Create local Docker-only credentials (never modify the existing .env)."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')


def jwt(secret: str, role: str) -> str:
    now = int(time.time())
    head = b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    body = b64(
        json.dumps(
            {'iss': 'supabase', 'role': role, 'aud': 'authenticated', 'iat': now,
             'exp': now + 10 * 365 * 24 * 3600},
            separators=(',', ':'),
        ).encode()
    )
    unsigned = f'{head}.{body}'
    signature = b64(hmac.new(secret.encode(), unsigned.encode(), hashlib.sha256).digest())
    return f'{unsigned}.{signature}'


def previous_token() -> str:
    file = ROOT / '.env'
    if not file.exists():
        return ''
    for line in file.read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('TELEGRAM_BOT_TOKEN='):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


def main() -> None:
    path = ROOT / '.env.docker'
    if path.exists():
        print('Docker credentials already exist; left unchanged (.env.docker).')
        return
    secret = secrets.token_hex(32)
    data = {
        'POSTGRES_PASSWORD': secrets.token_hex(24),
        'AUTHENTICATOR_PASSWORD': secrets.token_hex(24),
        'AUTH_ADMIN_PASSWORD': secrets.token_hex(24),
        'JWT_SECRET': secret,
        'ANON_KEY': jwt(secret, 'anon'),
        'SERVICE_ROLE_KEY': jwt(secret, 'service_role'),
        'TELEGRAM_BOT_TOKEN': previous_token(),
    }
    path.write_text(''.join(f'{key}={value}\n' for key, value in data.items()), encoding='utf-8')
    print('Created .env.docker. Secrets were not printed.')
    print('Keep this file for the lifetime of the database volume; never rotate it blindly.')
    print('To add a bot token, edit TELEGRAM_BOT_TOKEN only.')


if __name__ == '__main__':
    main()
