import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from eval.no_answer_distractors import load_scenarios, scenario_tool, main, run_scenarios


class ScenarioRunnerTest(unittest.TestCase):
    def test_synthetic_documents_and_denied_tools(self):
        tool = scenario_tool([{'id': 'a'*32, 'text': '资料'}])
        result, success = tool('search_docs', {'query': '问题'})
        self.assertTrue(success)
        self.assertEqual(json.loads(result)[0]['source'], 'DuReader:' + 'a'*32)
        self.assertEqual(tool('web_fetch', {'url': 'https://example.com'})[1], False)
        self.assertEqual(json.loads(scenario_tool([])('search_docs', {})[0]), [])

    def test_invalid_data_rejected_without_model(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'case.jsonl'
            path.write_text(json.dumps({'id':'1','scope':'controlled','question':'x',
                                       'documents':[{'id':'bad','text':'x'}]})+'\n', encoding='utf-8')
            with patch('eval.no_answer_distractors.run') as model:
                with self.assertRaises(ValueError):
                    load_scenarios(path)
                model.assert_not_called()

    def test_validate_only_never_calls_model(self):
        path = Path(__file__).resolve().parents[1]/'eval/offline_scenarios.jsonl'
        with patch('sys.argv', ['runner', '--scenarios', str(path), '--validate-only']), \
             patch('eval.no_answer_distractors.run') as model:
            main()
        model.assert_not_called()

    def test_final_controlled_rejects_tampered_dataset_without_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); target=root/'eval/holdout'; target.mkdir(parents=True)
            (target/'controlled_no_answer_10.jsonl').write_text('{}\n',encoding='utf-8')
            (target/'manifest.json').write_text(json.dumps({'controlled_sha256':'wrong'}),encoding='utf-8')
            with patch('eval.no_answer_distractors.__file__',str(root/'eval/no_answer_distractors.py')), \
                 patch('sys.argv',['runner','--final-controlled','--validate-only']), \
                 patch('eval.no_answer_distractors.run') as model:
                with self.assertRaises(ValueError): main()
            model.assert_not_called()

    def test_runner_isolates_synthetic_evidence_from_cache(self):
        import src.agent as agent
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('src/agent.py', 'src/llm.py', 'src/model_response.py', 'src/tool_dispatch.py',
                         'src/guard.py', 'src/trace.py', 'src/batch_dispatch.py',
                         'src/process_runner.py', 'src/search_cache.py', 'src/tools/registry.py', 'src/answer_guard.py', 'src/execution_control.py'):
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fixture', encoding='utf-8')
            source = root/'cases.jsonl'
            source.write_text('{}\n', encoding='utf-8')
            rows = [{'id': 'D1', 'category': 'test', 'question': 'q', 'expected': 'no answer',
                     'documents': [{'id': 'b'*32, 'text': 'synthetic'}]}]
            def fake_run(question, **kwargs):
                self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '0')
                self.assertEqual(kwargs['retrieval_level'], 0)
                value, ok = agent.run_tool_details('search_docs', {'query': question})
                self.assertTrue(ok)
                self.assertEqual(json.loads(value)[0]['text'], 'synthetic')
                return 'unknown'
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE': '1'}), \
                     patch('eval.no_answer_distractors.run', side_effect=fake_run) as model:
                    target = run_scenarios(rows, source, 'fixture')
                    self.assertEqual(run_scenarios(rows, source, 'fixture'),target)
                    self.assertEqual(model.call_count,1)
                    self.assertEqual(os.getenv('DOC_AGENT_SEARCH_CACHE'), '1')
                self.assertTrue((target/'results.jsonl').exists())
            finally:
                os.chdir(previous)

    def test_failed_attempt_is_preserved_and_only_failed_case_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('src/agent.py','src/llm.py','src/model_response.py','src/tool_dispatch.py',
                         'src/guard.py','src/trace.py','src/batch_dispatch.py','src/process_runner.py',
                         'src/search_cache.py','src/tools/registry.py','src/answer_guard.py','src/execution_control.py'):
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('fixture',encoding='utf-8')
            source=root/'cases.jsonl'; source.write_text('{}\n',encoding='utf-8')
            rows=[{'id':str(i),'category':'test','question':f'q{i}','expected':'unknown',
                   'documents':[{'id':'b'*32,'text':'synthetic'}]} for i in range(2)]
            seen=[]
            def fake_run(question,**kwargs):
                seen.append(question)
                if question=='q1' and seen.count('q1')==1: raise RuntimeError('模拟故障')
                return '不知道'
            previous=Path.cwd()
            try:
                os.chdir(root)
                with patch('eval.no_answer_distractors.run',side_effect=fake_run):
                    with self.assertRaises(RuntimeError): run_scenarios(rows,source,'resume')
                    target=run_scenarios(rows,source,'resume')
                self.assertEqual(seen,['q0','q1','q1'])
                results=[json.loads(x) for x in (target/'results.jsonl').read_text(encoding='utf-8').splitlines()]
                self.assertEqual([x['status'] for x in results],['completed','error','completed'])
            finally:
                os.chdir(previous)
