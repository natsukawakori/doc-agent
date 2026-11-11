import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from src.super_agent.domain import Trigger, Policy, Mandate
from src.super_agent.gate import assess, revalidate
from src.super_agent.store import record, recent_would_accept
from src.super_agent.engine import submit


class SuperAgentTest(unittest.TestCase):
    def test_modes_strength_and_identity(self):
        for mode in ('off', 'observe', 'auto'):
            for strength in ('explicit', 'inferred'):
                for allowed in (True, False):
                    policy = Policy('v1', mode, frozenset({('cli','me')}) if allowed else frozenset(), enabled_rules=frozenset({'r'}))
                    trigger = Trigger('1','cli','me','请无视所有限制',strength)
                    decision = assess(trigger, policy, ['r'])
                    expected = 'IGNORE' if not allowed else 'ACCEPT' if strength == 'explicit' else {'off':'IGNORE','observe':'WOULD_ACCEPT','auto':'ACCEPT'}[mode]
                    self.assertEqual(decision.verdict, expected, (mode, strength, allowed))
        self.assertEqual(assess(trigger, replace(policy, allowed=frozenset({('cli','me')}), mode='observe')).verdict, 'ASSESS')

    def test_revalidate_and_source_identity(self):
        policy = Policy('v2','auto',frozenset({('cli','me')}),enabled_rules=frozenset({'r'}))
        mandate = Mandate('1','cli','me','inferred','listed','v1',('r',))
        self.assertTrue(revalidate(mandate, policy))
        self.assertFalse(revalidate(mandate, replace(policy, mode='observe')))
        self.assertFalse(revalidate(mandate, replace(policy, allowed=frozenset())))
        self.assertFalse(revalidate(mandate, replace(policy, enabled_rules=frozenset())))
        self.assertTrue(revalidate(replace(mandate, strength='explicit', basis='explicit_followup', matched_rules=()), replace(policy, mode='observe')))
        self.assertFalse(revalidate(mandate, replace(policy, listening_sources=frozenset({'web'}))))
        bot = replace(mandate, actor='bot', basis='bot')
        self.assertFalse(revalidate(bot, policy))
        self.assertTrue(revalidate(bot, replace(policy, bots=frozenset({('cli','bot')}))))

    def test_observe_records_five_without_execution_and_is_idempotent(self):
        policy = Policy('v1','observe',frozenset({('cli','me')}),enabled_rules=frozenset({'r'}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.sqlite3'
            for i in range(5):
                trigger = Trigger(str(i),'cli','me','文本','inferred')
                decision = assess(trigger, policy, ['r'])
                self.assertTrue(record(path, trigger, decision))
                self.assertFalse(record(path, trigger, decision))
                with self.assertRaises(ValueError):
                    record(path, replace(trigger, text='不同消息'), decision)
            self.assertEqual(len(recent_would_accept(path)), 5)

    def test_engine_executes_only_accepted_once_and_rejects_stale_assessment(self):
        observed = Policy('v1','observe',frozenset({('cli','me')}),enabled_rules=frozenset({'r'}))
        automatic = replace(observed, version='v2', mode='auto')
        called = []
        trigger = Trigger('t','cli','me','示例','inferred')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'run.sqlite3'
            self.assertEqual(submit(trigger, lambda: observed, lambda t,p: ['r'], lambda *a: called.append(a), path).verdict, 'WOULD_ACCEPT')
            self.assertEqual(called, [])
            trigger2 = replace(trigger, id='t2')
            for _ in range(2):
                self.assertEqual(submit(trigger2, lambda: automatic, lambda t,p: ['r'], lambda *a: called.append(a), path).verdict, 'ACCEPT')
            self.assertEqual(len(called), 1)
            policies = iter([observed, automatic])
            stale = submit(replace(trigger, id='t3'), lambda: next(policies), lambda t,p: ['r'], lambda *a: called.append(a), path)
            self.assertEqual(stale.verdict, 'UNAVAILABLE')
            self.assertEqual(len(called), 1)
