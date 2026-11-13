import unittest

from scripts.check_rls import check_closed, check_public, permission_denied, unknown_column


class DbError(Exception):
    def __init__(self, code=None):
        self.code = code


class Query:
    def __init__(self, failure=None, rows=None):
        self.failure = failure
        self.rows = rows or []

    def select(self, field):
        self.field = field
        return self

    def limit(self, value):
        return self

    def execute(self):
        if self.failure:
            raise self.failure
        if self.field in ('user_id', 'telegram_id', 'username', 'display_name'):
            raise DbError('42703')
        return type('Response', (), {'data': self.rows})()


class Client:
    def __init__(self, error=None, rows=None):
        self.error = error
        self.rows = rows

    def table(self, name):
        return Query(self.error, self.rows)


class AccessTests(unittest.TestCase):
    def test_permission_code(self):
        self.assertTrue(permission_denied(DbError('42501')))
        self.assertFalse(permission_denied(ConnectionError('сеть недоступна')))
        self.assertFalse(permission_denied(DbError('PGRST205')))

    def test_missing_column_code(self):
        self.assertTrue(unknown_column(DbError('42703')))
        self.assertFalse(unknown_column(ConnectionError('нет связи')))

    def test_denied_table(self):
        check_closed(Client(DbError('42501')), 'users')

    def test_network_error_is_failure(self):
        with self.assertRaises(AssertionError):
            check_closed(Client(ConnectionError('сеть недоступна')), 'users')

    def test_public_view_rejects_private_field(self):
        check_public(Client(rows=[]), 'leaderboard_users')

    def test_public_view_with_private_field_fails(self):
        with self.assertRaises(AssertionError):
            check_public(Client(rows=[{'name': 'test', 'user_id': 'secret'}]), 'leaderboard_users')


if __name__ == '__main__':
    unittest.main()
