"""固定 10 条受控近邻证据问题，检索返回不包含被问事实；调用真实 LLM。"""
import json
import argparse
import hashlib
import os
import re
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from src.agent import run

CASES = [
 ('青杉计划的负责人是谁？', '青杉计划是一项虚构的文档整理活动，材料未提及负责人。'),
 ('蓝岚项目是哪一年结束的？', '蓝岚项目于 2020 年启动，结束年份未记录。'),
 ('纸鸢展览在哪里举办？', '纸鸢展览的主题是传统艺术，举办地点未记录。'),
 ('山竹实验一共有多少名参与者？', '山竹实验进行了两次访谈，参与者人数未记录。'),
 ('秋水公司第二季度利润是多少？', '秋水公司第二季度营收为 100 万元，利润未记录。'),
 ('红枫软件的最新版本号是多少？', '红枫软件最初版本号为 1.0，最新版本号未记录。'),
 ('星桥团队获得了什么奖项？', '星桥团队参加过演示活动，是否获奖未记录。'),
 ('月影活动的报名截止日是几号？', '月影活动计划在春季举办，报名截止日未记录。'),
 ('绿野设备的电池容量是多少？', '绿野设备重 200 克，电池容量未记录。'),
 ('北辰园区的开放时间是几点？', '北辰园区设有阅览室，开放时间未记录。'),
]


def load_scenarios(path):
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows or len({x['id'] for x in rows}) != len(rows):
        raise ValueError('开发场景为空或 ID 重复')
    for row in rows:
        if row.get('scope') != 'controlled' or not row.get('question') or not isinstance(row.get('documents'), list):
            raise ValueError('开发场景格式无效')
        for doc in row['documents']:
            if not re.fullmatch(r'[0-9a-f]{32}', doc.get('id', '')) or not isinstance(doc.get('text'), str):
                raise ValueError('模拟文档格式无效')
        if any(m.get('role') not in ('user', 'assistant') or not isinstance(m.get('content'), str)
               for m in row.get('history', [])):
            raise ValueError('模拟历史格式无效')
    return rows


def scenario_tool(documents):
    content = json.dumps([{'source': 'DuReader:' + d['id'], 'text': d['text']} for d in documents], ensure_ascii=False)
    def tool(name, arguments):
        return (content, True) if name == 'search_docs' else ('受控测试不允许该工具', False)
    return tool


def run_scenarios(rows, source, run_id):
    if not re.fullmatch(r'[A-Za-z0-9_]+', run_id):
        raise ValueError('运行标识无效')
    folder = Path('data/reports') / ('controlled_scenarios_' + run_id)
    folder.mkdir(parents=True, exist_ok=True)
    config = {'scenario_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'code_sha256': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (
                  'src/agent.py', 'src/llm.py', 'src/model_response.py', 'src/tool_dispatch.py',
                  'src/guard.py', 'src/trace.py', 'src/batch_dispatch.py', 'src/process_runner.py',
                  'src/search_cache.py', 'src/tools/registry.py', 'src/answer_guard.py', 'src/execution_control.py')},
              'model': os.getenv('LLM_MODEL_ID', ''),
              'provider_sha256': hashlib.sha256(os.getenv('LLM_BASE_URL', '').encode()).hexdigest(),
              'token_budget': os.getenv('DOC_AGENT_TOKEN_BUDGET', ''),
              'include_usage': os.getenv('LLM_INCLUDE_USAGE', '1'),
              'scope': 'controlled', 'case_count': len(rows), 'retrieval_level': 0,
              'note': '合成证据，不是 DuReader 真实段落；本运行结果需要人工标注。'}
    config_path=folder/'config.json'
    if config_path.exists():
        if json.loads(config_path.read_text(encoding='utf-8')) != config:
            raise ValueError('受控测试续跑配置与已有记录不一致')
    else:
        if any(folder.iterdir()): raise ValueError('目标目录已有无法关联的记录')
        with config_path.open('x',encoding='utf-8') as out:
            json.dump(config,out,ensure_ascii=False,indent=2)
    results_path=folder/'results.jsonl'
    previous=[json.loads(line) for line in results_path.read_text(encoding='utf-8').splitlines() if line.strip()] if results_path.exists() else []
    expected={str(row['id']) for row in rows}
    if any(str(row.get('id')) not in expected for row in previous): raise ValueError('已有结果包含不属于本次题集的 ID')
    done={str(row['id']) for row in previous if row.get('status')=='completed'}
    with results_path.open('a', encoding='utf-8') as out:
        for row in rows:
            if str(row['id']) in done: continue
            events, start = [], time.perf_counter()
            attempt=datetime.now().isoformat(timespec='microseconds')
            try:
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE': '0'}), \
                     patch('src.agent.run_tool_details', side_effect=scenario_tool(row['documents'])), \
                     patch('src.agent.run_batch', return_value=None):
                    answer = run(row['question'], history=row.get('history', []), max_steps=2, observer=events.append, retrieval_level=0)
                result = {'id': row['id'], 'category': row['category'], 'question': row['question'],
                          'documents': row['documents'], 'expected': row['expected'], 'answer': answer,
                          'events': events, 'seconds': time.perf_counter()-start, 'manual_label': 'unknown',
                          'status':'completed', 'attempt':attempt}
            except Exception as exc:
                out.write(json.dumps({'id': row['id'], 'status': 'error', 'attempt':attempt,
                                      'error_type': type(exc).__name__, 'events':events}, ensure_ascii=False)+'\n')
                out.flush()
                raise
            out.write(json.dumps(result, ensure_ascii=False)+'\n'); out.flush()
            print('完成场景', row['id'], flush=True)
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--scenarios', type=Path, help='受控场景 JSONL')
    group.add_argument('--final-controlled', action='store_true', help='验证并运行冻结的最终受控无依据场景')
    parser.add_argument('--validate-only', action='store_true', help='只验证场景，不调用模型')
    parser.add_argument('--run-id', help='受控场景运行标识')
    args = parser.parse_args()
    if args.final_controlled:
        root=Path(__file__).resolve().parents[1]
        args.scenarios=root/'eval/holdout/controlled_no_answer_10.jsonl'
        manifest=json.loads((root/'eval/holdout/manifest.json').read_text(encoding='utf-8'))
        if hashlib.sha256(args.scenarios.read_bytes()).hexdigest()!=manifest['controlled_sha256']:
            raise ValueError('受控题集与冻结清单不一致')
    if args.validate_only and not args.scenarios:
        parser.error('--validate-only 必须提供 --scenarios')
    if args.scenarios:
        rows = load_scenarios(args.scenarios)
        if args.validate_only:
            print(f'验证 {len(rows)} 个受控场景；未调用模型。')
            return
        if not args.run_id:
            parser.error('运行场景需提供 --run-id，避免覆盖旧记录')
        run_scenarios(rows, args.scenarios, args.run_id)
        return
    folder = Path('data/reports/no_answer_distractors_v1')
    folder.mkdir(parents=True, exist_ok=False)
    with (folder/'results.jsonl').open('x', encoding='utf-8') as out:
        for i, (question, evidence) in enumerate(CASES, 1):
            events = []
            document = json.dumps([{'source': 'DuReader:' + f'{i:032x}', 'text': evidence}], ensure_ascii=False)
            def tool(name, args):
                return (document, True) if name == 'search_docs' else ('受控测试不允许该工具', False)
            start = time.perf_counter()
            try:
                with patch.dict(os.environ, {'DOC_AGENT_SEARCH_CACHE': '0'}), \
                     patch('src.agent.run_tool_details', side_effect=tool), patch('src.agent.run_batch', return_value=None):
                    answer = run(question, max_steps=2, observer=events.append, retrieval_level=0)
                row = {'id': i, 'question': question, 'evidence': evidence, 'answer': answer,
                       'seconds': time.perf_counter()-start, 'status': 'completed', 'events': events,
                       'manual_label': 'unknown'}
            except Exception as exc:
                row = {'id': i, 'question': question, 'status': 'error', 'error_type': type(exc).__name__}
                out.write(json.dumps(row, ensure_ascii=False)+'\n'); out.flush()
                raise
            out.write(json.dumps(row, ensure_ascii=False)+'\n'); out.flush()
            print(f'已完成 {i}/10；等待质量判断。', flush=True)


if __name__ == '__main__':
    main()
