"""Read-only local setup check: credentials, files and public Supabase REST."""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COLUMNS = {'lang_pair', 'confirmed', 'collecting', 'expert_review'}


if __package__:
    from .settings import load_settings
    from .settings import read_env as read_env
else:
    from settings import load_settings
    from settings import read_env as read_env


def validate_settings(values: dict[str, str], require_bot: bool = False) -> tuple[str, str]:
    url = values.get('SUPABASE_URL', '').rstrip('/')
    public_key = values.get('SUPABASE_PUBLIC_KEY', '')
    private_key = values.get('SUPABASE_SECRET_KEY') or values.get('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not public_key or not private_key:
        raise ValueError(
            'Complete SUPABASE_URL, SUPABASE_PUBLIC_KEY and SUPABASE_SECRET_KEY in .env'
        )
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Doctor checks only the local Supabase. Use http://127.0.0.1:54321')
    if public_key.startswith('sb_secret_') or public_key == private_key:
        raise ValueError('Public API key looks like a secret key')
    if not values.get('TELEGRAM_BOT_TOKEN'):
        if require_bot:
            raise ValueError('TELEGRAM_BOT_TOKEN is empty; add BotFather token to .env')
        print('WARN: TELEGRAM_BOT_TOKEN is empty; website can work, bot cannot start')
    return url, public_key


def rest_get(url: str, key: str, resource: str):
    request = urllib.request.Request(
        f'{url}/rest/v1/{resource}',
        headers={'apikey': key, 'Authorization': 'Bearer ' + key, 'accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read(100_000)
            return response.status, json.loads(body)
    except urllib.error.HTTPError as error:
        return error.code, None


def check_public_api(url: str, key: str) -> None:
    status, rows = rest_get(
        url, key, 'adventure_progress?select=lang_pair,confirmed,collecting,expert_review&limit=2'
    )
    if status != 200 or not isinstance(rows, list):
        raise RuntimeError(
            f'Public adventure_progress REST returned HTTP {status}; check SQL setup'
        )
    if any(not isinstance(row, dict) or not REQUIRED_COLUMNS <= row.keys() for row in rows):
        raise RuntimeError('Public adventure_progress response has unexpected columns')
    print(f'PASS: public REST view reachable ({len(rows)} rows in sample)')

    # Never accept a successful SELECT on a raw users table, even when empty.
    status, _ = rest_get(url, key, 'users?select=telegram_id&limit=1')
    if status == 200:
        raise RuntimeError('Public key can SELECT users; close this permission before the demo')
    if status not in (401, 403):
        raise RuntimeError(f'Users access check returned unexpected HTTP {status}')
    print(f'PASS: direct access to users is denied (HTTP {status})')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-path', type=Path, default=None)
    parser.add_argument('--offline', action='store_true', help='Check settings and files only')
    parser.add_argument('--require-bot', action='store_true', help='Require a Telegram bot token')
    args = parser.parse_args()
    try:
        values = load_settings(args.env_path)
        url, key = validate_settings(values, require_bot=args.require_bot)
        print('PASS: local connection settings exist (keys hidden)')
        for path in ('web/index.html', 'web/assets/learning-deck.json', 'sql/logic.sql'):
            if not (ROOT / path).is_file():
                raise RuntimeError(f'Missing file: {path}')
        print('PASS: site, learning deck and SQL logic are present')
        if not args.offline:
            check_public_api(url, key)
        else:
            print('SKIP: network and RLS checks (offline requested)')
    except (
        OSError,
        ValueError,
        RuntimeError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ) as error:
        print(f'FAIL: {error.__class__.__name__}: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
