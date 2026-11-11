import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eval.prepare_review_packets import main


class ReviewPacketTest(unittest.TestCase):
    def test_keeps_completed_attempt_and_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / 'source', root / 'output'
            source.mkdir()
            result = {'id': '1', 'attempt': 'finished', 'question': '问题', 'answer': '实际回答'}
            events = [
                {'id': '1', 'attempt': 'failed', 'type': 'user'},
                {'id': '1', 'attempt': 'failed', 'type': 'tool', 'result': '旧证据'},
                {'id': '1', 'attempt': 'finished', 'type': 'user'},
                {'id': '1', 'attempt': 'finished', 'type': 'tool', 'name': 'search_docs', 'success': True, 'result': '[{"text":"新证据"}]'},
            ]
            (source / 'results.jsonl').write_text(json.dumps(result, ensure_ascii=False) + '\n', encoding='utf-8')
            (source / 'events.jsonl').write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
            with patch('sys.argv', ['prepare_review_packets', str(source), str(output)]):
                main()
            text = (output / '01_1.md').read_text(encoding='utf-8')
            self.assertIn('实际回答', text)
            self.assertIn('新证据', text)
            self.assertNotIn('旧证据', text)
            self.assertTrue((output / '阅读与填写指引.md').exists())
