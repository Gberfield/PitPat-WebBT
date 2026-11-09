import unittest
from bridge import safety_health

class Clock:
    def __init__(self): self.now=0
    def __call__(self): return self.now
    def advance(self,n): self.now+=n

class HealthTests(unittest.TestCase):
    def test_is_healthy_requires_an_accepted_answer(self):
        clock=Clock();m=safety_health.HealthMonitor(clock)
        self.assertFalse(m.answered);self.assertFalse(m.is_healthy())
        m.attach('app')
        self.assertFalse(m.expired())
        self.assertFalse(m.answered);self.assertFalse(m.is_healthy())
        self.assertTrue(m.accept_health(m.issue_challenge()))
        self.assertTrue(m.answered);self.assertTrue(m.is_healthy())
    def test_is_healthy_expires_without_clearing_answered(self):
        clock=Clock();m=safety_health.HealthMonitor(clock);m.attach('app')
        clock.advance(.25);self.assertTrue(m.accept_health(m.issue_challenge()))
        clock.advance(safety_health.HEALTH_TIMEOUT-.01)
        self.assertTrue(m.is_healthy())
        clock.advance(.01)
        self.assertFalse(m.is_healthy());self.assertTrue(m.answered)
        clock.advance(.01)
        self.assertFalse(m.is_healthy());self.assertTrue(m.answered)
    def test_detach_and_reattach_require_a_new_answer(self):
        clock=Clock();m=safety_health.HealthMonitor(clock);m.attach('app')
        self.assertTrue(m.accept_health(m.issue_challenge()))
        self.assertTrue(m.is_healthy())
        m.detach()
        self.assertFalse(m.answered);self.assertFalse(m.is_healthy())
        m.attach('new-app')
        self.assertFalse(m.expired())
        self.assertFalse(m.answered);self.assertFalse(m.is_healthy())
        self.assertTrue(m.accept_health(m.issue_challenge()))
        self.assertTrue(m.is_healthy())
    def test_expired_buffered_health_cannot_revive_application(self):
        self.assertTrue(hasattr(safety_health,'HealthMonitor'), 'independent health monitor missing')
        clock=Clock(); monitor=safety_health.HealthMonitor(clock);monitor.attach('app')
        challenge=monitor.issue_challenge()
        clock.advance(2.05)
        self.assertFalse(monitor.accept_health(challenge))
        self.assertTrue(monitor.expired())
    def test_nonce_is_single_use_and_sequences_do_not_replay(self):
        self.assertTrue(hasattr(safety_health,'HealthMonitor'), 'independent health monitor missing')
        clock=Clock();m=safety_health.HealthMonitor(clock);m.attach('app');c=m.issue_challenge()
        self.assertTrue(m.accept_health(c));self.assertFalse(m.accept_health(c))
        clock.advance(.25);new=m.issue_challenge();self.assertTrue(m.accept_health(new))
        self.assertFalse(m.accept_health(c))
