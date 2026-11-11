"""逐题执行已创建的工单；保留每次尝试的事件和上下文。"""
from src.agent import run as run_agent
from .final_answer import synthesize
from . import tickets


def run_ticket(ticket_id, *, path=tickets.DB, retry_failed=False, max_questions=None, agent=run_agent, on_event=None, summarizer=None, execution_control=None):
    if summarizer is None:
        summarizer = synthesize
    if max_questions is not None and max_questions < 1:
        raise ValueError('最多执行题数必须大于零')
    owner = tickets.acquire(ticket_id, retry_failed=retry_failed, path=path)
    completed = 0
    while True:
        item = tickets.next_question(ticket_id, owner, path=path)
        if item is None:
            return tickets.get_ticket(ticket_id, path=path)
        if item.get('kind') == 'final':
            try:
                if execution_control: execution_control.check()
                if on_event: on_event({'type':'final_start','attempt':item['attempt']})
                def delta(content):
                    if execution_control: execution_control.check()
                    if on_event: on_event({'type':'final_delta','content':content})
                result=summarizer(item,on_delta=delta)
                if execution_control: execution_control.check()
                answer=result.get('answer')
                if not isinstance(answer,str) or not answer.strip(): raise ValueError('最终汇总未返回有效回答')
                if result.get('notice'):
                    tickets.append_event(ticket_id,owner,{'position':None,'attempt':item['attempt']},
                                         {'type':'final_notice','content':result['notice']},path=path)
                    if on_event: on_event({'type':'final_notice','content':result['notice']})
                tickets.finish_final(ticket_id,owner,item,answer=answer,usage=result.get('usage'),path=path)
            except Exception as exc:
                tickets.finish_final(ticket_id,owner,item,error=f'{type(exc).__name__}: {exc}',path=path)
            else:
                if on_event: on_event({'type':'final_done','answer':answer})
            return tickets.get_ticket(ticket_id,path=path)
        try:
            if execution_control: execution_control.check()
            if on_event:
                on_event({'type':'question_start','position':item['position'],'question':item['question'],
                          'attempt':item['attempt'],'retrieval_policy':item.get('retrieval_policy')})
            tickets.append_event(ticket_id, owner, item, {'type':'question_start','question':item['question']}, path=path)
            def observe(event):
                tickets.append_event(ticket_id, owner, item, event, path=path)
                if on_event:
                    on_event({'type':'agent_event','position':item['position'],'event':event})
            options = {'history':item['history'], 'observer':observe}
            if item.get('prior_evidence'):
                options['prior_evidence'] = item['prior_evidence']
            if item.get('retrieval_policy') is not None:
                options['retrieval_level'] = item['retrieval_policy']['retrieval_level']
            if execution_control is not None:
                options['execution_control'] = execution_control
            answer = agent(item['question'], **options)
            if execution_control: execution_control.check()
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError('Agent 未返回有效回答')
            if item.get('policy_changed'):
                tickets.append_event(ticket_id, owner, item, {'type':'policy_choice_reply_excerpt','content':answer[:500]}, path=path)
            tickets.append_event(ticket_id, owner, item, {'type':'question_done'}, path=path)
            tickets.finish_question(ticket_id, owner, item, answer=answer, path=path)
            if on_event:
                on_event({'type':'question_done','position':item['position'],'answer':answer})
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            # 若执行权已丢失，不能覆盖其他执行者的状态。
            tickets.finish_question(ticket_id, owner, item, error=error, path=path)
            return tickets.get_ticket(ticket_id, path=path)
        completed += 1
        if max_questions is not None and completed >= max_questions:
            # 没有剩余问题时直接完成；否则在下一题之前暂停。
            snapshot = tickets.get_ticket(ticket_id, path=path)
            if any(q['status'] == 'pending' for q in snapshot['questions']):
                tickets.request_pause(ticket_id, path=path)
