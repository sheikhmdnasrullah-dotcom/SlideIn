"""Tests for warmup tracker and end-to-end pipeline guards."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import state as st
from core import warmup
from core import pipeline as pipe
from core import circuit_breaker as cb_mod
from core import gate as gate_mod
from core import analyzer


class TestWarmupTracker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.conn = self.store.conn
        self.tracker = warmup.WarmupTracker(self.conn)
        self.tracker.initialize_domain("example.com")

    def test_initial_limit_is_default(self):
        status = self.tracker.status("example.com")
        self.assertEqual(status["current_daily_limit"], 20)
        self.assertEqual(status["sent_today"], 0)

    def test_can_send_until_limit(self):
        for i in range(20):
            ok, reason = self.tracker.can_send("example.com", self.store)
            self.assertTrue(ok, f"Send {i} should be allowed: {reason}")
            self.tracker.record_send("example.com", "hello@example.com", f"user{i}@example.com")

    def test_blocked_after_limit(self):
        for i in range(20):
            self.tracker.record_send("example.com", "hello@example.com", f"user{i}@example.com")
        ok, reason = self.tracker.can_send("example.com", self.store)
        self.assertFalse(ok)
        self.assertIn("warmup daily limit", reason)

    def test_ramp_up_after_ramp_step_days(self):
        # Manually set start_ts to 4 days ago
        self.conn.execute("UPDATE warmup_state SET start_ts=? WHERE domain=?",
                          (__import__('time').time() - 4 * 24 * 3600, "example.com"))
        self.conn.commit()
        self.tracker.ramp_up("example.com")
        status = self.tracker.status("example.com")
        self.assertEqual(status["current_daily_limit"], 40)


class TestEndToEndPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.gate = gate_mod.Gate(self.store, gate_mod.GateConfig(require_seed=False))
        self.breaker = cb_mod.CircuitBreaker(self.store, cb_mod.BreakerConfig())
        self.analyzer_fn = lambda eml: analyzer.analyze(eml, None)
        self.wtracker = warmup.WarmupTracker(self.store.conn)
        self.wtracker.initialize_domain("tanim.tech")

    def test_full_send_flow_with_warmup_and_pacing(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: test\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=\"b\"\r\n"
            b"\r\n"
            b"--b\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"body\r\n"
            b"--b\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<p>body</p>\r\n"
            b"--b--\r\n"
        )
        self.gate.evaluate(eml, self.analyzer_fn, lambda eml: [])
        # First send should succeed
        res = pipe.send_via_pipeline(
            "lead@example.com", eml,
            config={"smtp": {}, "transport": "smtp", "sending_domains": ["tanim.tech"], "pacing": {"min_delay_seconds": 0}},
            store=self.store, gate=self.gate, breaker=self.breaker,
            transport=lambda c, e, r: None,
        )
        self.assertEqual(res["status"], "sent")

    def test_suppressed_recipient_never_sends(self):
        eml = b"From: hello@tanim.tech\r\nTo: lead@example.com\r\nSubject: test\r\n\r\nbody\r\n"
        self.store.suppress("lead@example.com", "hard_bounce")
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline(
                "lead@example.com", eml,
                config={"smtp": {}, "transport": "smtp", "sending_domains": ["tanim.tech"]},
                store=self.store, gate=self.gate, breaker=self.breaker,
                transport=lambda c, e, r: None,
            )

    def test_auth_failure_blocks_send(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: test\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"Authentication-Results: spf=fail; dkim=fail; dmarc=fail\r\n"
            b"\r\nbody\r\n"
        )
        self.gate.evaluate(eml, self.analyzer_fn, lambda eml: [])
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline(
                "lead@example.com", eml,
                config={"smtp": {}, "transport": "smtp", "sending_domains": ["tanim.tech"]},
                store=self.store, gate=self.gate, breaker=self.breaker,
                transport=lambda c, e, r: None,
            )


if __name__ == "__main__":
    unittest.main()
