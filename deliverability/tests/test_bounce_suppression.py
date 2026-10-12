"""Tests for bounce parser, suppression list, and new pipeline guards."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import state as st
from core import bounce_parser
from core import pipeline as pipe
from core import circuit_breaker as cb_mod
from core import gate as gate_mod
from core import analyzer


class TestBounceParser(unittest.TestCase):
    def test_hard_bounce_5xx(self):
        eml = b"""Content-Type: multipart/report; boundary="b"
--b
Content-Type: message/delivery-status

Final-Recipient: rfc822; user@example.com
Status: 5.1.1
Diagnostic-Code: smtp; 550 user unknown
--b--"""
        res = bounce_parser.parse_bounce(eml)
        self.assertEqual(res.status, "hard_bounce")
        self.assertEqual(res.recipient, "user@example.com")
        self.assertTrue(bounce_parser.should_suppress(res))

    def test_soft_bounce_4xx(self):
        eml = b"""Content-Type: multipart/report; boundary="b"
--b
Content-Type: message/delivery-status

Final-Recipient: rfc822; user@example.com
Status: 4.2.2
Diagnostic-Code: smtp; 421 mailbox full
--b--"""
        res = bounce_parser.parse_bounce(eml)
        self.assertEqual(res.status, "deferred")
        self.assertFalse(bounce_parser.should_suppress(res))

    def test_arf_complaint(self):
        eml = b"""Content-Type: multipart/report; boundary="b"
--b
Content-Type: message/feedback-report

Feedback-Type: abuse
User-Agent: Some Reporter/1.0
Version: 1
Original-Recipient: rfc822; user@example.com
Reported-Email: <msg@example.com>
--b--"""
        res = bounce_parser.parse_bounce(eml)
        self.assertEqual(res.status, "complaint")
        self.assertTrue(bounce_parser.should_suppress(res))


class TestSuppressionList(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)

    def test_suppress_and_check(self):
        self.assertFalse(self.store.is_suppressed("a@b.com"))
        self.store.suppress("a@b.com", "hard_bounce", "550 no such user")
        self.assertTrue(self.store.is_suppressed("a@b.com"))
        self.store.unsuppress("a@b.com")
        self.assertFalse(self.store.is_suppressed("a@b.com"))

    def test_suppressed_recipients_list(self):
        self.store.suppress("a@b.com", "complaint")
        self.store.suppress("c@d.com", "hard_bounce")
        self.assertEqual(sorted(self.store.suppressed_recipients()), ["a@b.com", "c@d.com"])


class TestPipelineSuppressionGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.gate = gate_mod.Gate(self.store, gate_mod.GateConfig(require_seed=False))
        self.breaker = cb_mod.CircuitBreaker(self.store, cb_mod.BreakerConfig())
        self.analyzer_fn = lambda eml: analyzer.analyze(eml, None)

    def test_suppressed_recipient_blocks_send(self):
        eml = b"From: hello@tanim.tech\r\nTo: lead@example.com\r\nSubject: test\r\n\r\nbody\r\n"
        self.store.suppress("lead@example.com", "hard_bounce", "550 no such user")
        self.gate.evaluate(eml, self.analyzer_fn, lambda eml: [])
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline("lead@example.com", eml, config={"smtp": {}},
                                   store=self.store, gate=self.gate, breaker=self.breaker,
                                   transport=lambda c, e, r: None)


class TestHalfOpenCircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.cfg = cb_mod.BreakerConfig(half_open_probe_count=2, half_open_cooldown_seconds=0)
        self.breaker = cb_mod.CircuitBreaker(self.store, self.cfg)

    def test_half_open_after_cooldown(self):
        self.breaker._trip("test", {})
        self.assertTrue(self.breaker.is_open())
        self.breaker.maybe_half_open()
        self.assertTrue(self.breaker.is_half_open())

    def test_probe_count_limits_sends(self):
        self.breaker._trip("test", {})
        self.breaker.maybe_half_open()
        self.assertTrue(self.breaker.probe_send_allowed())
        # First successful probe is not enough (half_open_probe_count=2):
        # the circuit must stay half-open until the batch completes.
        self.breaker.record_probe(True, {})
        self.assertTrue(self.breaker.is_half_open())
        self.assertTrue(self.breaker.probe_send_allowed())
        # Second success completes the batch -> fully closed.
        self.breaker.record_probe(True, {})
        self.assertFalse(self.breaker.is_half_open())
        self.assertFalse(self.breaker.is_open())

    def test_failed_probe_retrips(self):
        self.breaker._trip("test", {})
        self.breaker.maybe_half_open()
        self.assertTrue(self.breaker.probe_send_allowed())
        self.breaker.record_probe(False, {})
        self.assertTrue(self.breaker.is_open())


class TestPacingEnforcement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)

    def test_immediate_send_allowed(self):
        pipe._enforce_pacing(self.store, 60)

    def test_rapid_send_blocked(self):
        self.store.record_send_event("a@b.com", "smtp", "sent", "")
        with self.assertRaises(pipe.BlockedSend):
            pipe._enforce_pacing(self.store, 60)


if __name__ == "__main__":
    unittest.main()
