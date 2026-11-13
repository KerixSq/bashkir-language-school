import argparse
from datetime import datetime, timedelta, timezone

from common import client
from pure import new_api_key, secret_hash


def main() -> None:
    parser = argparse.ArgumentParser(description='Создать ключ партнёра')
    parser.add_argument('--partner', required=True)
    parser.add_argument('--permission', choices=['read', 'write'], default='read')
    parser.add_argument('--days', type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error('--days должен быть от 1 до 365')
    token = new_api_key()
    expires = (datetime.now(timezone.utc) + timedelta(days=args.days)).isoformat()
    client().table('api_keys').insert(
        {
            'partner_name': args.partner[:100],
            'key_hash': secret_hash(token),
            'permission': args.permission,
            'expires_at': expires,
        }
    ).execute()
    print('Сохрани ключ сейчас: он больше не отображается.\n' + token)


if __name__ == '__main__':
    main()
