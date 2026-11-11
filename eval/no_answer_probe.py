"""受控空检索的无依据开发探针；真实调用 LLM，不评估全量语料。"""
import json
import os
import time
import re
import sys
from pathlib import Path
from unittest.mock import patch
from src.agent import run

QUESTIONS = [f'请根据资料说明“紫松计划{n:02d}”的发布日期和负责人；如果资料没有提及请明确说明。' for n in range(1, 11)]


def main():
    run_id = sys.argv[1] if len(sys.argv) > 1 else 'v1'
    if not re.fullmatch(r'[A-Za-z0-9_]+', run_id):
        raise ValueError('运行标识不合法')
    folder = Path('data/reports') / ('no_answer_controlled_' + run_id)
    folder.mkdir(parents=True, exist_ok=False)
    with (folder/'results.jsonl').open('x', encoding='utf-8') as f:
        for index, question in enumerate(QUESTIONS, 1):
            events = []
            start = time.perf_counter()
            # 此受控测试只允许空的文档搜索；不进行真实语料检索或网页访问。
            def tool(name, args):
                return ('[]', True) if name == 'search_docs' else ('受控测试不允许该工具', False)
            try:
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE': '0'}), \
                     patch('src.agent.run_tool_details', side_effect=tool), patch('src.agent.run_batch', return_value=None):
                    answer = run(question, max_steps=2, observer=events.append)
                row = {'id': index, 'question': question, 'answer': answer, 'seconds': time.perf_counter()-start,
                       'events': events, 'status': 'completed', 'manual_label': 'unknown'}
            except Exception as exc:
                row = {'id': index, 'question': question, 'status': 'error', 'error_type': type(exc).__name__,
                       'seconds': time.perf_counter()-start, 'manual_label': 'unknown'}
                f.write(json.dumps(row, ensure_ascii=False)+'\n'); f.flush()
                print('停止：模型请求失败，已保存部分记录。', flush=True)
                raise
            f.write(json.dumps(row, ensure_ascii=False)+'\n'); f.flush()
            print(f'已完成 {index}/{len(QUESTIONS)}；仍需人工判断。', flush=True)


if __name__ == '__main__':
    main()
