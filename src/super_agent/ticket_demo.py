"""真实模型的本地三题工单测试，第一次后暂停并恢复。"""
import json
from contextlib import redirect_stdout
from pathlib import Path
from .domain import Mandate
from .tickets import create_ticket
from .ticket_runner import run_ticket


def main():
    root = Path(__file__).resolve().parents[2]
    folder = root / 'data/reports/ticket_stage1_demo'
    folder.mkdir(parents=True, exist_ok=False)
    database = folder / 'tickets.sqlite3'
    questions = json.loads((root/'examples/对比问题清单.json').read_text(encoding='utf-8'))
    mandate = Mandate('ticket-stage1-demo','cli','local-demo','explicit','listed','local-demo-v1')
    ticket_id, _ = create_ticket(mandate, questions, database)
    duplicate, created = create_ticket(mandate, questions, database)
    if created or duplicate != ticket_id:
        raise RuntimeError('重复触发校验失败')
    with (folder/'run.log').open('w', encoding='utf-8') as log, redirect_stdout(log):
        first = run_ticket(ticket_id, path=database, max_questions=1)
        if first['status'] != 'paused':
            result = first
        else:
            result = run_ticket(ticket_id, path=database)
    (folder/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 第一阶段真实工单测试', '', '使用官方模型运行三题；第一题完成后暂停，再从下一题恢复。',
             f"工单 ID：{ticket_id}；第一次状态：{first['status']}；最终状态：{result['status']}。", '']
    for q in result['questions']:
        lines.extend([f"## 问题 {q['position']}：{q['question']}", '',
                      f"状态：{q['status']}；尝试次数：{q['attempt']}。", '', q['answer'] or q['error'] or '未执行', ''])
        for e in result['events']:
            if e['position'] == q['position'] and e['event'].get('type') == 'tool':
                event = e['event']
                lines.append(f"- 工具 `{event.get('name')}`；成功：{event.get('success')}；参数：`{event.get('arguments')}`")
        lines.append('')
    (folder/'工单测试记录.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'ticket_id':ticket_id,'first':first['status'],'final':result['status'],
                      'attempts':[q['attempt'] for q in result['questions']],'report':str(folder/'工单测试记录.md')},ensure_ascii=False))
    if result['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__': main()
