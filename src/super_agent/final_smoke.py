"""真实 API 小样本：observe→auto→自动规划→工单→强度切换。"""
import json
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.server import app
from app import super_api


def main():
    root=Path(__file__).resolve().parents[2]
    folder=root/'data/reports/super_final_answer_acceptance'
    folder.mkdir(parents=True,exist_ok=False)
    sim=folder/'simulation.sqlite3'; ticketdb=folder/'tickets.sqlite3'
    report={'stages':[]}
    def save(): (folder/'结果.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    def post(client,url,body):
        response=client.post(url,json=body)
        if response.status_code!=200: raise RuntimeError(f'{url} HTTP {response.status_code}: {response.text[:500]}')
        return response.json()
    def stream(client,url,body):
        response=client.post(url,json=body)
        if response.status_code!=200: raise RuntimeError(f'{url} HTTP {response.status_code}: {response.text[:500]}')
        events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        if not events or events[-1]['type']!='done': raise RuntimeError('执行流未正常结束')
        return events
    try:
        with patch.object(super_api,'SIM_DB',sim), patch.object(super_api,'TICKET_DB',ticketdb), TestClient(app) as client, \
             (folder/'运行日志.txt').open('w',encoding='utf-8') as log, redirect_stdout(log):
            post(client,'/api/super/policy',{'mode':'observe'})
            goal='请先分别解释 Native App 与 Web App，再比较二者主要区别，引用资料并指出可能过时之处。'
            first=post(client,'/api/super/triggers',{'role':'owner','kind':'inferred','text':goal,
                       'questions':[goal],'retrieval_level':0,'plan':True})
            report['stages'].append({'name':'observe','response':first}); save()
            if first['decision']['verdict']!='WOULD_ACCEPT' or first['decision']['ticket_id']:
                raise RuntimeError('观察模式结果不符合预期')
            post(client,'/api/super/policy',{'mode':'auto'})
            second=post(client,f"/api/super/triggers/{first['trigger_id']}/process",{'level':0})
            report['stages'].append({'name':'auto_reassessment','response':second}); save()
            d=second['decision']
            if d['verdict']!='ACCEPT' or not d['ticket_id'] or not d['plan_json']:
                raise RuntimeError('重新研判或规划未成功')
            plan=json.loads(d['plan_json'])
            ticket=d['ticket_id']; report['ticket_id']=ticket; report['plan']=plan; save()
            before=client.get(f'/api/super/tickets/{ticket}').json()
            if before['original_goal']!=goal or [q['question'] for q in before['questions']]!=plan['questions']:
                raise RuntimeError('规划没有正确进入工单')
            first_run=stream(client,f'/api/super/tickets/{ticket}/run',{'max_questions':1})
            report['stages'].append({'name':'first_run','events':first_run}); save()
            state=first_run[-1]['result']
            if len(plan['questions'])>1 and state['status']!='paused': raise RuntimeError('应在第一题后暂停')
            if len(plan['questions'])>1:
                post(client,f'/api/super/tickets/{ticket}/retrieval',{'level':3})
                next_run=stream(client,f'/api/super/tickets/{ticket}/run',{'max_questions':1})
                report['stages'].append({'name':'forced_web','events':next_run}); save()
                tools=[e['event'] for e in next_run if e['type']=='agent_event' and e['event'].get('type')=='tool']
                if not any(e.get('name')=='web_search' for e in tools): raise RuntimeError('最高档没有联网尝试')
                state=next_run[-1]['result']
            if state['status']=='paused':
                post(client,f'/api/super/tickets/{ticket}/retrieval',{'level':0})
                last=stream(client,f'/api/super/tickets/{ticket}/run',{})
                report['stages'].append({'name':'resume_local','events':last}); save()
                state=last[-1]['result']
            report['final']=state; save()
            if state['status']!='completed': raise RuntimeError(f"工单未完成：{state['status']}")
            if not state.get('final_answer') or not state['final_answer'].get('answer'):
                raise RuntimeError('最终综合回答缺失')
            all_events=[e for stage in report['stages'] for e in stage.get('events',[])]
            if not all(any(e['type']==kind for e in all_events) for kind in ('final_start','final_delta','final_done')):
                raise RuntimeError('最终综合回答流式事件缺失')
    except Exception as exc:
        report['error']=f'{type(exc).__name__}: {exc}'; save(); raise
    summary=['# 外层规划与网页接口真实测试','',f"原始目标：{goal}",'',
             f"观察模式：{first['decision']['verdict']}；切换自动模式重新研判：{d['verdict']}。",'',
             '## 外层规划','',plan.get('reason',''), '']
    for i,q in enumerate(plan['questions'],1): summary.append(f'{i}. {q}')
    summary+=['',f"工单最终状态：{state['status']}。",'']
    summary += ['## 最终综合回答','',state['final_answer']['answer'],'']
    for q in state['questions']:
        summary += [f"## 子问题 {q['position']}：{q['question']}",'',f"状态：{q['status']}；尝试：{q['attempt']}",'',q['answer'] or q['error'] or '未执行','']
    summary += ['完整外层决定、逐事件输出与工具返回见同目录 `结果.json`。本例只验证流程，不代表答案正确率或外层规划稳定性。']
    (folder/'真实测试记录.md').write_text('\n'.join(summary),encoding='utf-8')
    print(json.dumps({'status':state['status'],'questions':len(plan['questions']), 'report':str(folder/'真实测试记录.md')},ensure_ascii=False))


if __name__=='__main__': main()
