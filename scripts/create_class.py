import argparse
import secrets

from common import client
from pure import new_join_code


def main() -> None:
    parser = argparse.ArgumentParser(description='Создать класс от имени организатора')
    parser.add_argument('--school-id', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    db = client()
    for _ in range(5):
        join = new_join_code()
        if not db.table('classes').select('id').eq('join_code', join).execute().data:
            break
    else:
        raise SystemExit('Не удалось создать уникальный код')
    teacher = secrets.token_urlsafe(32)
    db.table('classes').insert(
        {
            'school_id': args.school_id,
            'name': args.name.strip()[:60],
            'join_code': join,
            'teacher_code': teacher,
        }
    ).execute()
    print(f'Код ученика: {join}\nКод преподавателя (не публиковать): {teacher}')


if __name__ == '__main__':
    main()
