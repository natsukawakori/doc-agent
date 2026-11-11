import unittest
import hashlib
import json
import tempfile
from pathlib import Path
from eval.holdout.metrics import summarize, verify_ids


class FinalMetricsTest(unittest.TestCase):
    def fixtures(self):
        cases=[{'id':str(i),'answer_label':'correct' if i<28 else 'unknown',
                'citation_presence':'present' if i<3 else 'absent'} for i in range(30)]
        citations=[{'case_id':str(i),'claim_id':'c1','citation_id':'s1','label':label}
                   for i,label in enumerate(('supported','partial','unknown'))]
        no_answers=[{'id':str(i),'label':'correct' if i<7 else 'incorrect' if i==7 else 'unknown'} for i in range(10)]
        return cases,citations,no_answers

    def test_denominators_and_partial_unknown_are_explicit(self):
        result=summarize(*self.fixtures())
        self.assertEqual(result['answer_correct_all'],{'numerator':28,'denominator':30,'value':28/30})
        self.assertEqual(result['answer_correct_assessed']['denominator'],28)
        self.assertEqual(result['citation_item_fully_supported']['value'],.5)
        self.assertEqual(result['citation_case_fully_supported']['denominator'],3)
        self.assertEqual(result['citation_case_fully_supported']['numerator'],1)
        self.assertEqual(result['no_answer_correct_all']['value'],.7)
        self.assertEqual(result['no_answer_correct_assessed']['denominator'],8)

    def test_duplicate_or_missing_citation_is_rejected(self):
        cases,citations,no_answers=self.fixtures()
        with self.assertRaises(ValueError): summarize(cases,citations+[citations[0]],no_answers)
        with self.assertRaises(ValueError): summarize(cases,citations[:-1],no_answers)
        with self.assertRaises(ValueError): summarize(cases[:-1],citations,no_answers)

    def test_frozen_ids_and_hashes_must_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); main=b'{"id":"a"}\n'; controlled=b'{"id":"n"}\n'
            (root/'holdout_30.jsonl').write_bytes(main)
            (root/'controlled_no_answer_10.jsonl').write_bytes(controlled)
            (root/'manifest.json').write_text(json.dumps({'holdout_sha256':hashlib.sha256(main).hexdigest(),
                'controlled_sha256':hashlib.sha256(controlled).hexdigest()}),encoding='utf-8')
            verify_ids([{'id':'a'}],[{'id':'n'}],root)
            with self.assertRaises(ValueError): verify_ids([{'id':'other'}],[{'id':'n'}],root)
            (root/'holdout_30.jsonl').write_bytes(main+b' ')
            with self.assertRaises(ValueError): verify_ids([{'id':'a'}],[{'id':'n'}],root)


if __name__=='__main__': unittest.main()
