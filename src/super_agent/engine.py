"""示范触发 → 准入 → 外部研判 → 记录 → 执行；不绑定现有网页入口。"""
from .domain import Decision
from .gate import assess
from .store import record


def submit(trigger, get_policy, assess_rules, execute, db_path):
    before = get_policy()
    decision = assess(trigger, before)
    if decision.verdict == 'ASSESS':
        # assess_rules 是宿主提供的研判函数，权限逻辑本身不调用模型。
        matches = assess_rules(trigger, before)
        after = get_policy()
        if after != before:
            return Decision('UNAVAILABLE', '研判期间策略变化；需要重新排队', after.version)
        decision = assess(trigger, after, matches)
    if get_policy() != before:
        return Decision('UNAVAILABLE', '落库前策略变化；需要重新排队', get_policy().version)
    first = record(db_path, trigger, decision)
    if first and decision.verdict == 'ACCEPT':
        execute(trigger, decision)
    return decision
