"""任务触发、策略、决定和授权：不可变数据，消息正文不授予权限。"""
from dataclasses import dataclass
from typing import Literal

Mode = Literal['off', 'observe', 'auto']
Strength = Literal['explicit', 'inferred']


@dataclass(frozen=True)
class Trigger:
    id: str
    source: str
    actor: str
    text: str
    strength: Strength
    is_bot: bool = False


@dataclass(frozen=True)
class Policy:
    version: str
    mode: Mode
    # (source, actor) 使用来源自己的身份，不将不同来源的账号合并。
    allowed: frozenset[tuple[str, str]]
    bots: frozenset[tuple[str, str]] = frozenset()
    enabled_rules: frozenset[str] = frozenset()
    listening_sources: frozenset[str] = frozenset({'cli', 'web'})


@dataclass(frozen=True)
class Decision:
    verdict: Literal['ACCEPT', 'WOULD_ACCEPT', 'IGNORE', 'ASSESS', 'UNAVAILABLE']
    reason: str
    policy_version: str
    matched_rules: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mandate:
    trigger_id: str
    source: str
    actor: str
    strength: Strength
    basis: Literal['listed', 'explicit_followup', 'table', 'bot']
    policy_version: str
    matched_rules: tuple[str, ...] = ()
