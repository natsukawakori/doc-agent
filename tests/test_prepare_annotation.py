import unittest
from eval.prepare_annotation import prepare


class AnnotationTest(unittest.TestCase):
    def test_preserves_evidence_and_unknown(self):
        rows = [{'id': '1', 'question': '问题', 'answer': '回答', 'seconds': 2, 'tokens': None}]
        events = [{'id': '1', 'attempt': 'a', 'type': 'user'},
                  {'id': '1', 'attempt': 'a', 'type': 'tool', 'name': 'search_docs', 'success': True, 'result': '证据'}]
        cases, text = prepare(rows, events)
        self.assertEqual(cases[0]['answer_label'], 'unknown')
        self.assertIn('证据', text)
        with self.assertRaises(ValueError):
            prepare(rows, events + [{'id': '1', 'attempt': 'b', 'type': 'user'}])
