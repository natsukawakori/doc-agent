"""真实双层模型与 0→3→0 强度变化的本地测试。"""
import json
import argparse
from contextlib import redirect_stdout
from pathlib import Path
from . import simulation, orchestrator, tickets


def main():
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=root/'data/reports/super_integration_demo')
    folder=parser.parse_args().output
    folder.mkdir(parents=True,exist_ok=False)
    simdb=folder/'simulation.sqlite3'; ticketdb=folder/'tickets.sqlite3'
    orchestrator.configure('auto',sim_db=simdb,ticket_db=ticketdb)
    questions=json.loads((root/'examples/对比问题清单.json').read_text(encoding='utf-8'))
    trigger=simulation.emit('owner','inferred','发现需要处理的文档问答清单',questions,simdb)
    decision=orchestrator.process(trigger.id,'auto',sim_db=simdb,ticket_db=ticketdb)
    result={'trigger_id':trigger.id,'decision':decision}
    if decision.get('verdict') != 'ACCEPT':
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        raise SystemExit('外层未接受事件，已保存实际结果。')
    ticket=decision['ticket_id']
    with (folder/'run.log').open('w',encoding='utf-8') as log, redirect_stdout(log):
        tickets.set_retrieval_level(ticket,0,path=ticketdb)
        first=orchestrator.run_approved(ticket,sim_db=simdb,ticket_db=ticketdb,max_questions=1)
        if first['status'] != 'paused': raise RuntimeError('第一题后未暂停')
        tickets.set_retrieval_level(ticket,3,path=ticketdb)
        second=orchestrator.run_approved(ticket,sim_db=simdb,ticket_db=ticketdb,max_questions=1)
        if second['status'] != 'paused': raise RuntimeError('第二题后未暂停')
        tickets.set_retrieval_level(ticket,0,path=ticketdb)
        final=orchestrator.run_approved(ticket,sim_db=simdb,ticket_db=ticketdb)
    result.update({'first_status':first['status'],'second_status':second['status'],'ticket':final})
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 双层模型与检索策略实测','',f"外层决定：{decision['verdict']}；工单：{ticket}。",
           f"外层研判记录：{decision.get('assessment_json')}。",'',f"阶段状态：{first['status']} → {second['status']} → {final['status']}。",'']
    for q in final['questions']:
        lines.extend([f"## 问题 {q['position']}：{q['question']}",'',f"状态：{q['status']}；尝试：{q['attempt']}",'',q['answer'] or q['error'] or '未执行',''])
        for event in final['events']:
            if event['position'] != q['position']: continue
            e=event['event']
            if e.get('type') in ('question_policy','policy_change_context','policy_choice_reply_excerpt'):
                lines.append('- '+json.dumps(e,ensure_ascii=False))
            if e.get('type')=='tool':
                lines.append(f"- 工具 {e.get('name')}；成功 {e.get('success')}；参数 {e.get('arguments')}")
        lines.append('')
    (folder/'双层与策略实测.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'outer':decision['verdict'],'first':first['status'],'second':second['status'],
                      'final':final['status'],'report':str(folder/'双层与策略实测.md')},ensure_ascii=False))
    if final['status']!='completed': raise SystemExit(1)


if __name__=='__main__': main()
