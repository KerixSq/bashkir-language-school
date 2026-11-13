import argparse
import secrets

from common import client
from pure import secret_hash


def main() -> None:
    parser = argparse.ArgumentParser(description='Настройка секретных кодов доступа')
    parser.add_argument('--kind', required=True, choices=['expert', 'teacher-invite'])
    args = parser.parse_args()
    key = 'expert_access_hash' if args.kind == 'expert' else 'teacher_invite_code'
    token = secrets.token_urlsafe(32)
    client().table('config').upsert(
        {'key': key, 'value': secret_hash(token)}, on_conflict='key'
    ).execute()
    print(f'Секрет {args.kind} (показывается один раз): {token}')


if __name__ == '__main__':
    main()
