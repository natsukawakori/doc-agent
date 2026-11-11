"""确定性准入与恢复校验；推断候选须由独立研判提供结果。"""
from .domain import Decision, Mandate, Policy, Trigger


def assess(trigger: Trigger, policy: Policy, matched_rules=None) -> Decision:
    if policy.mode not in ('off', 'observe', 'auto') or trigger.strength not in ('explicit', 'inferred'):
        raise ValueError('无效策略模式或触发强度')
    identity = (trigger.source, trigger.actor)
    if trigger.source not in policy.listening_sources:
        return Decision('IGNORE', '来源未启用', policy.version)
    if trigger.is_bot:
        if identity not in policy.bots or trigger.strength != 'inferred':
            return Decision('IGNORE', '机器人未获准或强度无效', policy.version)
    elif identity not in policy.allowed:
        return Decision('IGNORE', '来源身份未获准', policy.version)
    if trigger.strength == 'explicit':
        return Decision('ACCEPT', '获准的明确请求', policy.version)
    if policy.mode == 'off':
        return Decision('IGNORE', '推断请求未启用', policy.version)
    if matched_rules is None:
        return Decision('ASSESS', '需要独立研判', policy.version)
    matches = tuple(sorted(set(matched_rules)))
    if not matches or not set(matches).issubset(policy.enabled_rules):
        return Decision('IGNORE', '没有匹配已启用规则', policy.version)
    verdict = 'WOULD_ACCEPT' if policy.mode == 'observe' else 'ACCEPT'
    return Decision(verdict, '推断请求命中规则', policy.version, matches)


def revalidate(mandate: Mandate, policy: Policy) -> bool:
    if mandate.source not in policy.listening_sources:
        return False
    if mandate.basis == 'explicit_followup':
        return mandate.strength == 'explicit'
    if mandate.strength == 'inferred' and (
        policy.mode != 'auto' or not mandate.matched_rules
        or not set(mandate.matched_rules).issubset(policy.enabled_rules)
    ):
        return False
    identity = (mandate.source, mandate.actor)
    if mandate.basis == 'bot':
        return mandate.strength == 'inferred' and identity in policy.bots
    if mandate.basis in ('listed', 'table'):
        # 当前学习原型的 table 是身份白名单；尚未支持更细的来源准入表。
        return identity in policy.allowed
    return False
