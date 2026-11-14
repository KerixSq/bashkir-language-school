"""Upgrade/fresh-install parity for the protected expert RPC."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExpertSimilarityContractTests(unittest.TestCase):
    def test_migration_matches_fresh_install_and_keeps_authorization(self):
        pattern = r'create or replace function public.expert_list_queue\(.*?\n\$\$;'
        fresh = (ROOT / 'sql/logic.sql').read_text(encoding='utf-8')
        migration = (ROOT / 'sql/migrations/20261114_stage12_expert_similarity.sql').read_text(
            encoding='utf-8'
        )
        function = re.search(pattern, migration, re.S).group()
        self.assertEqual(function, re.search(pattern, fresh, re.S).group())
        self.assertIn('private.expert_authorized(p_code)', function)
        self.assertIn("set search_path = ''", function)
        self.assertTrue(migration.startswith('begin;'))
        self.assertTrue(migration.rstrip().endswith('commit;'))
        self.assertNotRegex(
            migration.lower(), r'(insert into|update|delete from) public.synonym_map'
        )
