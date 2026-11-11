import unittest
from eval.prepare_holdout30 import choose, normalize


class HoldoutTest(unittest.TestCase):
    def test_excludes_prior_and_deduplicates(self):
        prior = [{'id': '1', 'text': 'Ａ B', 'positive_ids': ['p']}]
        def row(i, text, gold):
            return {'query_id': i, 'query': text, 'positive_passages': [{'docid': gold}], 'negative_passages': [1]}
        rows = [row(1, 'old', 'z'), row(2, 'a b', 'z'), row(3, 'new', 'p'),
                row(4, 'unique', 'q'), row(5, 'other', 'r')]
        result, _ = choose(rows, prior, 2)
        self.assertEqual({x['id'] for x in result}, {'4', '5'})
        self.assertEqual(normalize('Ａ B'), 'ab')
        self.assertEqual(result, choose(list(reversed(rows)), prior, 2)[0])

    def test_insufficient(self):
        with self.assertRaises(ValueError):
            choose([], [], 1)

    def test_new_seed_is_deterministic_and_excludes_old_holdout(self):
        prior = [{'id':'old', 'text':'已使用的问题', 'positive_ids':['old-gold']}]
        def row(i, text, gold):
            return {'query_id':i, 'query':text, 'positive_passages':[{'docid':gold}], 'negative_passages':[1]}
        rows = [row('old','别的文字','p'), row('new1','已使用的问题','q'),
                row('new2','未见问题','old-gold'), row('new3','独立问题','r')]
        result, _ = choose(rows, prior, 1, seed='new-seed')
        self.assertEqual(result[0]['id'], 'new3')
        self.assertEqual(result, choose(list(reversed(rows)), prior, 1, seed='new-seed')[0])
