"""Select one environment file; Compose credentials never fall back to cloud."""

import os
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for raw in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$', raw)
            if match:
                values[match[1]] = match[2].strip().strip('"').strip("'")
    return values


def load_settings(path: Path | None = None) -> dict[str, str]:
    selected = path or os.getenv('BASHKIR_ENV_FILE')
    selected = (
        Path(selected)
        if selected
        else ROOT / ('.env.docker' if (ROOT / '.env.docker').exists() else '.env')
    )
    values = read_env(selected)
    if selected.name == '.env.docker':
        if not selected.is_file():
            raise ValueError('Selected .env.docker does not exist')
        for key in ('ANON_KEY', 'SERVICE_ROLE_KEY'):
            if not values.get(key):
                raise ValueError(f'Missing {key} in .env.docker')
        values.update(
            SUPABASE_URL='http://127.0.0.1:54321',
            SUPABASE_PUBLIC_KEY=values['ANON_KEY'],
            SUPABASE_SECRET_KEY=values['SERVICE_ROLE_KEY'],
        )
        if urlparse(values['SUPABASE_URL']).hostname != '127.0.0.1':
            raise ValueError('Docker checks must target loopback')
    else:
        values = {**values, **os.environ}
    return values
