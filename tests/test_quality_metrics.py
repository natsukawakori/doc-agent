import unittest
from eval.quality_metrics import summarize


class QualityMetricsTest(unittest.TestCase):
    def test_counts_unknown_and_percentile(self):
        cases = [{'id': '1', 'answer_label': 'correct', 'no_answer_label': 'correct', 'seconds': 2, 'tokens': 10},
                 {'id': '2', 'answer_label': 'partial', 'no_answer_label': 'unknown', 'seconds': 4, 'tokens': None},
                 {'id': '3', 'answer_label': 'unknown'}]
        citations = [{'case_id': '1', 'claim_id': '1', 'label': 'supported'},
                     {'case_id': '2', 'claim_id': '1', 'label': 'unsupported'}]
        result = summarize(cases, citations)
        self.assertEqual(result['answer_correct_rate']['value'], .5)
        self.assertEqual(result['answer_correct_rate']['unknown'], 1)
        self.assertEqual(result['citation_support_rate']['value'], .5)
        self.assertEqual(result['no_answer_correct_rate']['denominator'], 1)
        self.assertEqual(result['p95_latency_seconds'], 4)
        self.assertEqual(result['token_per_case'], 10)

    def test_invalid_or_duplicate_labels_fail(self):
        with self.assertRaises(ValueError):
            summarize([{'id': '1', 'answer_label': 'yes'}], [])
        with self.assertRaises(ValueError):
            summarize([{'id': '1', 'answer_label': 'correct'}], [{'case_id': '2', 'claim_id': '1', 'label': 'supported'}])

    def test_missing_data_stays_null(self):
        result = summarize([], [])
        self.assertIsNone(result['answer_correct_rate']['value'])
        self.assertIsNone(result['p95_latency_seconds'])
        self.assertIsNone(result['token_per_case'])

    def test_no_answer_scopes_and_uncited_claims(self):
        cases = [{'id': '1', 'answer_label': 'correct', 'no_answer_label': 'correct', 'no_answer_scope': 'controlled'},
                 {'id': '2', 'answer_label': 'incorrect', 'no_answer_label': 'incorrect', 'no_answer_scope': 'full_corpus'}]
        citations = [{'case_id': '1', 'claim_id': '1', 'label': 'unsupported', 'citation_status': 'uncited'},
                     {'case_id': '2', 'claim_id': '1', 'label': 'unknown'}]
        result = summarize(cases, citations)
        self.assertEqual(result['no_answer_error_rate']['value'], .5)
        self.assertEqual(result['no_answer_by_scope']['controlled']['value'], 0)
        self.assertEqual(result['no_answer_by_scope']['full_corpus']['value'], 1)
        self.assertEqual(result['citation_status'], {'uncited': 1, 'unknown': 1})
        self.assertIsNone(result['explicit_citation_support_rate']['value'])

    def test_explicit_citations_exclude_unknown_and_uncited(self):
        cases = [{'id': '1', 'answer_label': 'unknown'}]
        claims = [{'case_id': '1', 'claim_id': '1', 'label': 'supported', 'citation_status': 'cited'},
                  {'case_id': '1', 'claim_id': '2', 'label': 'unsupported', 'citation_status': 'uncited'},
                  {'case_id': '1', 'claim_id': '3', 'label': 'unsupported', 'citation_status': 'unknown'}]
        result = summarize(cases, claims)
        self.assertEqual(result['citation_support_rate']['value'], 1/3)
        self.assertEqual(result['explicit_citation_support_rate']['value'], 1)
        self.assertEqual(result['explicit_citation_support_rate']['denominator'], 1)
