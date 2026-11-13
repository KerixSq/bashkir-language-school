import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


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
