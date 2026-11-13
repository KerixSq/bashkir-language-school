"""Configure local Supabase connection without printing or losing existing secrets."""

import argparse
import datetime as dt
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_LINE = re.compile(r'^([A-Z][A-Z_0-9]*)=(.*)$')
MANAGED = ('SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'SUPABASE_PUBLIC_KEY')


def parse_status(raw: str) -> dict[str, str]:
    """Read the KEY=value format produced by `supabase status -o env`."""
    result = {}
    for original in raw.splitlines():
        match = STATUS_LINE.fullmatch(original.strip())
        if not match:
            continue
        key, value = match.groups()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        result[key] = value
    return result


def local_values(raw: str) -> dict[str, str]:
    status = parse_status(raw)
    selected = {
        'SUPABASE_URL': status.get('API_URL', ''),
        'SUPABASE_PUBLIC_KEY': status.get('PUBLISHABLE_KEY') or status.get('ANON_KEY', ''),
        'SUPABASE_SECRET_KEY': status.get('SECRET_KEY') or status.get('SERVICE_ROLE_KEY', ''),
    }
    if not all(selected.values()):
        raise ValueError('Supabase CLI did not return API_URL, public key and server key')
    local_url = r'https?://(?:127\.0\.0\.1|localhost)(?::\d+)?/?'
    if not re.fullmatch(local_url, selected['SUPABASE_URL']):
        raise ValueError('Only local Supabase URLs are accepted by the local setup script')
    if any('\n' in value or '\r' in value for value in selected.values()):
        raise ValueError('Unexpected newline in local Supabase credentials')
    return selected


def merge_env(existing: str, changes: dict[str, str]) -> str:
    """Replace only connection settings; keep BotFather token and custom settings."""
    result = []
    seen = set()
    for line in existing.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=', line)
        if not match or match[1] not in changes:
            result.append(line)
            continue
        key = match[1]
        if key not in seen:
            result.append(f'{key}={changes[key]}')
            seen.add(key)
        # A duplicate managed key could override the updated value in dotenv.
    for key in MANAGED:
        if key not in seen:
            result.append(f'{key}={changes[key]}')
    if not any(re.match(r'^\s*TELEGRAM_BOT_TOKEN\s*=', line) for line in result):
        result.append('TELEGRAM_BOT_TOKEN=')
    return '\n'.join(result).rstrip('\n') + '\n'


def write_env(path: Path, new_contents: str) -> bool:
    original = path.read_text(encoding='utf-8-sig') if path.exists() else None
    if original == new_contents:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if original is not None:
        stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
        backup = path.with_name(f'{path.name}.backup-{stamp}-{uuid.uuid4().hex[:8]}')
        backup.write_text(original, encoding='utf-8')
    temp_path = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        temp_path.write_text(new_contents, encoding='utf-8')
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-path', type=Path, default=ROOT / '.env')
    args = parser.parse_args()
    try:
        values = local_values(sys.stdin.read())
        original = args.env_path.read_text(encoding='utf-8-sig') if args.env_path.exists() else ''
        changed = write_env(args.env_path, merge_env(original, values))
    except (ValueError, OSError) as error:
        print(f'ERROR: local configuration was not applied: {error}', file=sys.stderr)
        return 1
    message = (
        'OK: local keys written into .env; existing Telegram token preserved.'
        if changed
        else 'OK: .env already uses local Supabase keys.'
    )
    print(message)
    if changed and original:
        print('A backup was created before the existing .env was updated.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
