import json
import unittest
from pathlib import Path


class OfflineScenariosTest(unittest.TestCase):
    def test_schema_ids_and_coverage(self):
        path = Path(__file__).resolve().parents[1]/'eval/offline_scenarios.jsonl'
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({r['id'] for r in rows}), 12)
        self.assertEqual(len({r['category'] for r in rows}), 12)
        self.assertTrue(all(r['scope'] == 'controlled' and r['question'] and r['expected'] for r in rows))
        for row in rows:
            for doc in row['documents']:
                self.assertRegex(doc['id'], r'^[0-9a-f]{32}$')
                self.assertTrue(doc['text'])
        self.assertTrue(any('history' in r for r in rows))
        self.assertTrue(any(not r['documents'] for r in rows))
