import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src import agent
from eval import no_answer_probe, no_answer_distractors, boundary_probe


class ProbeIsolationTest(unittest.TestCase):
    def test_synthetic_probes_disable_real_cache(self):
        def fake_run(question, **kwargs):
            self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '0')
            result, ok = agent.run_tool_details('search_docs', {'query':question})
            self.assertTrue(ok)
            json.loads(result)
            return '无法确定'
        with tempfile.TemporaryDirectory() as folder:
            previous = Path.cwd()
            try:
                os.chdir(folder)
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE':'1'}), \
                     patch.object(no_answer_probe, 'run', side_effect=fake_run), \
                     patch('sys.argv', ['probe', 'test']):
                    no_answer_probe.main()
                    self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '1')
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE':'1'}), \
                     patch.object(no_answer_distractors, 'run', side_effect=fake_run), \
                     patch('sys.argv', ['probe']):
                    no_answer_distractors.main()
                    self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '1')
            finally:
                os.chdir(previous)

    def test_boundary_probe_isolated_and_refuses_overwrite(self):
        def fake_run(question, **kwargs):
            self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '0')
            self.assertEqual(agent.run_tool_details('search_docs', {'query':question}), ('[]', True))
            return '回答'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'data/reports/m3_acceptance_dureader_m3_20261105/events.jsonl'
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps({'id':'549','type':'tool','result':'[]'})+'\n', encoding='utf-8')
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE':'1'}), \
                     patch.object(boundary_probe, 'run', side_effect=fake_run) as model:
                    boundary_probe.main()
                    with self.assertRaises(FileExistsError):
                        boundary_probe.main()
                    self.assertEqual(model.call_count, 1)
                    self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '1')
            finally:
                os.chdir(previous)
