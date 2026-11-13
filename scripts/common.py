import os
from pathlib import Path

from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
if __package__:
    from .settings import load_settings
else:
    from settings import load_settings
os.environ.update(load_settings())


def client():
    url = os.getenv('SUPABASE_URL', '').strip()
    key = (os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY') or '').strip()
    if not url or not key:
        raise SystemExit('Заполни SUPABASE_URL и SUPABASE_SECRET_KEY в .env')
    return create_client(url, key)


def all_rows(builder, page_size: int = 500) -> list[dict]:
    rows = []
    offset = 0
    while True:
        page = builder().range(offset, offset + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size
