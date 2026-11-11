import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import llm


class LLMProfileTest(unittest.TestCase):
    def test_deepseek_selected_and_missing_key_never_reuses_default(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'.env').write_text('LLM_API_KEY=legacy-test\nLLM_MODEL_ID=old\nLLM_BASE_URL=https://old.invalid\n', encoding='utf-8')
            (root/'.env.deepseek').write_text('LLM_API_KEY=\nLLM_MODEL_ID=deepseek-flash\nLLM_BASE_URL=https://api.deepseek.com\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(llm.configure_profile(root), 'deepseek')
                self.assertEqual(os.environ['LLM_API_KEY'], '')
                self.assertEqual(os.environ['LLM_MODEL_ID'], 'deepseek-flash')
                self.assertEqual(os.environ['LLM_BASE_URL'], 'https://api.deepseek.com')
                with patch.object(llm, 'PROFILE', 'deepseek'), patch.object(llm, 'OpenAI') as client:
                    with self.assertRaisesRegex(ValueError, r'\.env\.deepseek'):
                        llm.chat([{'role':'user','content':'test'}])
                    client.assert_not_called()

    def test_official_config_is_default_and_ignores_old_env(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'.env').write_text('LLM_API_KEY=default\n', encoding='utf-8')
            (root/'.env.deepseek').write_text('LLM_API_KEY=official-test\nLLM_MODEL_ID=deepseek-flash\nLLM_BASE_URL=https://api.deepseek.com\n', encoding='utf-8')
            with patch.dict(os.environ, {'LLM_API_KEY':'external'}, clear=True):
                self.assertEqual(llm.configure_profile(root), 'deepseek')
                self.assertEqual(os.environ['LLM_API_KEY'], 'official-test')

    def test_invalid_or_missing_official_configuration_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(llm.configure_profile(root),'deepseek')
                with self.assertRaisesRegex(ValueError, r'\.env\.deepseek'):
                    llm.chat([{'role':'user','content':'test'}])

    def test_non_official_endpoint_is_rejected(self):
        values = {'LLM_BASE_URL':'https://example.invalid/v1', 'LLM_API_KEY':'test-key', 'LLM_MODEL_ID':'test'}
        with patch.dict(os.environ, values, clear=True), patch.object(llm, 'OpenAI') as client:
            with self.assertRaisesRegex(ValueError, '官方 API'):
                llm.chat([{'role':'user','content':'test'}])
            client.assert_not_called()

    def test_official_passes_model_tools_and_stream_to_sdk(self):
        values = {'LLM_BASE_URL':'https://api.deepseek.com', 'LLM_API_KEY':'test-key',
                  'LLM_MODEL_ID':'deepseek-flash', 'LLM_INCLUDE_USAGE':'1'}
        with patch.dict(os.environ, values, clear=True), patch.object(llm, 'OpenAI') as client:
            llm.chat([{'role':'user','content':'test'}], stream=True, tools=[{'type':'function'}])
            client.assert_called_once_with(base_url='https://api.deepseek.com', api_key='test-key', timeout=90.0)
            kwargs = client.return_value.chat.completions.create.call_args.kwargs
            self.assertEqual(kwargs['model'], 'deepseek-flash')
            self.assertEqual(kwargs['tools'], [{'type':'function'}])
            self.assertEqual(kwargs['stream_options'], {'include_usage':True})


if __name__ == '__main__':
    unittest.main()
