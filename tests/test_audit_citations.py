import json
import unittest
from eval.audit_citations import audit, nearby_candidate


class CitationAuditTest(unittest.TestCase):
    def test_presence_never_claims_local_support(self):
        valid, missing = 'a'*32, 'b'*32
        results = [{'id': '1', 'answer': '一些文本 [DuReader:' + valid + '] ' + missing}]
        events = [{'id': '1', 'type': 'tool', 'name': 'search_docs',
                   'result': json.dumps([{'source': 'DuReader:' + valid, 'text': '内容'}])}]
        claims = [{'case_id': '1', 'claim_id': '1', 'source_ids': ['DuReader:' + valid], 'annotation': '主张'}]
        cases, found = audit(results, events, claims)
        self.assertEqual(cases[0]['not_in_tool_results'], [missing])
        self.assertEqual(found[0]['status'], 'needs_context_review')
        self.assertEqual(found[0]['present_somewhere_in_answer'], [valid])

    def test_location_is_only_a_candidate(self):
        source = 'a'*32
        same = nearby_candidate('这是一个足够长的事实主张', '这是一个足够长的事实主张 [DuReader:'+source+']', [source])
        self.assertEqual(same['status'], 'id_on_same_line')
        missing = nearby_candidate('这是一个足够长的事实主张', '这是一个足够长的事实主张\n别段 [DuReader:'+source+']', [source])
        self.assertEqual(missing['status'], 'check_nearby')
        self.assertEqual(nearby_candidate('甲', '完全不相关', [])['status'], 'no_reliable_anchor')
