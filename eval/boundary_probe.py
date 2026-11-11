"""固定历史工具结果，真实 LLM 复测淘宝等级边界；不运行检索。"""
import json
import os
from pathlib import Path
from unittest.mock import patch
from src.agent import run

def main():
    source = Path('data/reports/m3_acceptance_dureader_m3_20261105/events.jsonl')
    events = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines()]
    tool_result = next(e['result'] for e in events if e.get('id') == '549' and e.get('type') == 'tool')
    output = Path('data/reports/boundary_probe_20261106.json')
    if output.exists():
        raise FileExistsError('报告已存在，拒绝调用模型和覆盖记录')
    seen = []
    with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE': '0'}), \
         patch('src.agent.run_tool_details', return_value=(tool_result, True)), patch('src.agent.run_batch', return_value=None):
        answer = run('淘宝两颗心是多少笔交易', max_steps=2, observer=seen.append)
    with output.open('x', encoding='utf-8') as f:
        json.dump({'question_id': '549', 'answer': answer, 'events': seen, 'human_verification': 'pending'}, f, ensure_ascii=False, indent=2)
    print('复测已记录；仍需核对完整回答。')


if __name__ == '__main__':
    main()
