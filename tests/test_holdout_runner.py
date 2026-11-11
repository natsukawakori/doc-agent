import hashlib
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from eval import acceptance_m3
from eval.acceptance_m3 import load_cases, scores


class HoldoutRunnerTest(unittest.TestCase):
    def test_final_validate_only_checks_hash_without_model_or_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); target=root/'eval/holdout'; target.mkdir(parents=True)
            rows=[{'id':str(i),'question':f'q{i}','gold_passage_ids':[f'd{i}']} for i in range(30)]
            raw=''.join(json.dumps(x)+'\n' for x in rows).encode()
            (target/'holdout_30.jsonl').write_bytes(raw)
            (target/'manifest.json').write_text(json.dumps({'holdout_sha256':hashlib.sha256(raw).hexdigest()}),encoding='utf-8')
            with patch.object(acceptance_m3,'PROJECT',root), patch.object(acceptance_m3,'run') as model, \
                 patch('sys.argv',['runner','--holdout-final','--validate-only']):
                acceptance_m3.main()
            model.assert_not_called()
            self.assertFalse((root/'data/reports').exists())
    def test_frozen_holdout_and_integrity(self):
        rows = [{'id': str(i), 'question': f'q{i}', 'gold_passage_ids': [f'd{i}']} for i in range(30)]
        raw = ''.join(json.dumps(x) + '\n' for x in rows).encode()
        manifest = {'holdout_sha256': hashlib.sha256(raw).hexdigest()}
        cases, ids, expected = load_cases(manifest, raw, True)
        self.assertEqual((len(cases), len(ids), expected), (30, 30, 30))
        self.assertEqual(cases['2']['positive_ids'], ['d2'])
        with self.assertRaises(ValueError):
            load_cases(manifest, raw + b' ', True)
        rows[-1]['id'] = rows[0]['id']
        duplicate = ''.join(json.dumps(x) + '\n' for x in rows).encode()
        with self.assertRaises(ValueError):
            load_cases({'holdout_sha256': hashlib.sha256(duplicate).hexdigest()}, duplicate, True)

    def test_development_compatibility_and_summary_size(self):
        rows = [{'id': str(i), 'text': f'q{i}', 'positive_ids': [f'd{i}']} for i in range(20)]
        raw = json.dumps({'queries': rows}).encode()
        cases, ids, count = load_cases({'queries_sha256': hashlib.sha256(raw).hexdigest(),
                                        'query_ids': [str(i) for i in range(20)]}, raw, False)
        self.assertEqual((len(cases), len(ids), count), (20, 20, 20))
        result = scores([{'steps': 1, 'hit1': True, 'hit3': True, 'seconds': 1,
                          'failures': 0, 'answer': 'a', 'tokens': None}], 30)
        self.assertEqual(result['expected'], 30)
        self.assertEqual(result['tokens_known'], 0)


if __name__ == '__main__':
    unittest.main()
