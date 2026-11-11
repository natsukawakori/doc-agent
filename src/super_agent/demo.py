"""离线演示观察模式与自动模式，不请求模型、不调用真实工具。"""
import json
import tempfile
from dataclasses import replace
from pathlib import Path
from .domain import Policy, Trigger
from .engine import submit
from .store import recent_would_accept


def main():
    policy = Policy('demo-observe', 'observe', frozenset({('cli', 'local-user')}), enabled_rules=frozenset({'doc_question'}))
    executions = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / 'demo.sqlite3'
        for i in range(5):
            submit(Trigger(f'observe-{i}', 'cli', 'local-user', '模拟触发', 'inferred'),
                   lambda: policy, lambda trigger, current: ['doc_question'],
                   lambda trigger, decision: executions.append(trigger.id), db)
        observed = len(recent_would_accept(db))
        observe_executions = len(executions)
        policy = replace(policy, version='demo-auto', mode='auto')
        decision = submit(Trigger('auto-1', 'cli', 'local-user', '模拟触发', 'inferred'),
                          lambda: policy, lambda trigger, current: ['doc_question'],
                          lambda trigger, decision: executions.append(trigger.id), db)
        print(json.dumps({'observe_records': observed, 'observe_executions': observe_executions,
                          'auto_decision': decision.verdict, 'simulated_executions': executions}, ensure_ascii=False))


if __name__ == '__main__':
    main()
