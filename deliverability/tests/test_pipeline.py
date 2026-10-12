"""Integration tests for the gate + circuit breaker + pipeline.

These prove the CONTROL LOGIC end-to-end using MockSeedReader (no external
accounts needed). The real IMAP adapter (seed_tester.IMAPSeedReader) is wired the
same way; only the seed credentials differ. Run: python3 -m pytest tests/  (or
python3 tests/test_pipeline.py).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import state as st
from core import analyzer
from core import seed_tester
from core import gate as gate_mod
from core import circuit_breaker as cb_mod
from core import dns_checks
from core import pipeline as pipe

GOOD_EML = b"""From: hello@tanim.tech
To: lead@example.com
Subject: your videos
Date: Thu, 04 Sep 2026 12:00:00 +0000
Message-ID: <test@tanim.tech>
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="b"

--b
Content-Type: text/plain

Hi there, just wanted to follow up about your stack.
--b
Content-Type: text/html

<p>Hi there, just wanted to follow up about your stack.</p>
--b--
"""


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.gate = gate_mod.Gate(self.store, gate_mod.GateConfig())
        self.breaker = cb_mod.CircuitBreaker(self.store, cb_mod.BreakerConfig())
        self.analyzer_fn = lambda eml: analyzer.analyze(eml, None)

    def _runner(self, behavior):
        def runner(eml_bytes):
            return [seed_tester.SeedResult(p, behavior[p], f"<{p}>", behavior[p] == "INBOX")
                    for p in behavior]
        return runner

    def test_all_inbox_approves_and_sends(self):
        runner = self._runner({"gmail": "INBOX", "outlook": "INBOX", "yahoo": "INBOX"})
        decision = self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        self.assertTrue(decision["approved"])
        self.assertTrue(self.gate.is_fresh_approved(GOOD_EML))
        sent = []
        pipe.send_via_pipeline("lead@x.com", GOOD_EML, config={"smtp": {}, "pacing": {"min_delay_seconds": 0}},
                               store=self.store, gate=self.gate, breaker=self.breaker,
                               transport=lambda cfg, eml, rcpt: sent.append(rcpt))
        self.assertEqual(sent, ["lead@x.com"])

    def test_gmail_spam_blocks_gate(self):
        runner = self._runner({"gmail": "SPAM", "outlook": "INBOX", "yahoo": "INBOX"})
        decision = self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        self.assertFalse(decision["approved"])
        self.assertIn("gmail:SPAM", decision["reason"])
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline("lead@x.com", GOOD_EML, config={"smtp": {}},
                                   store=self.store, gate=self.gate, breaker=self.breaker,
                                   transport=lambda c, e, r: None)

    def test_promotions_is_failure(self):
        runner = self._runner({"gmail": "PROMOTIONS", "outlook": "INBOX"})
        decision = self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        self.assertFalse(decision["approved"])

    def test_changed_email_invalidates_approval(self):
        runner = self._runner({"gmail": "INBOX", "outlook": "INBOX"})
        self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        other = GOOD_EML.replace(b"Subject: your videos", b"Subject: Different")
        self.assertFalse(self.gate.is_fresh_approved(other))

    def test_circuit_breaker_trips_and_blocks(self):
        self.breaker.evaluate({"seed_inbox_pct": 50.0, "bounce_rate": 0,
                               "complaint_rate": 0, "analyzer_grade": "A",
                               "blacklisted": False})
        self.assertTrue(self.breaker.is_open())
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline("lead@x.com", GOOD_EML, config={"smtp": {}},
                                   store=self.store, gate=self.gate, breaker=self.breaker,
                                   transport=lambda c, e, r: None)

    def test_circuit_breaker_resume_requires_validation(self):
        self.breaker.evaluate({"seed_inbox_pct": 0.0, "bounce_rate": 5,
                               "complaint_rate": 1, "analyzer_grade": "F",
                               "blacklisted": True})
        self.assertTrue(self.breaker.is_open())
        # cannot resume without passing validation
        self.assertFalse(self.breaker.resume_after_validation(False, {}))
        self.assertTrue(self.breaker.is_open())
        # passes only after a fresh validation
        self.assertTrue(self.breaker.resume_after_validation(True, {}))
        self.assertFalse(self.breaker.is_open())

    def test_healthy_metrics_do_not_auto_resume_open_breaker(self):
        """monitor.run_tick() evaluates every cycle; a single healthy tick
        must NEVER silently close a tripped breaker (fail-closed)."""
        self.breaker.evaluate({"seed_inbox_pct": 100.0, "bounce_rate": 9,
                               "complaint_rate": 0, "analyzer_grade": "A",
                               "blacklisted": False})
        self.assertTrue(self.breaker.is_open())
        # All-healthy evaluation (even with default metrics) keeps it open.
        tripped, _ = self.breaker.evaluate({})
        self.assertFalse(tripped)
        self.assertTrue(self.breaker.is_open())
        tripped, _ = self.breaker.evaluate({"seed_inbox_pct": 100.0,
                                            "bounce_rate": 0,
                                            "complaint_rate": 0,
                                            "analyzer_grade": "A",
                                            "blacklisted": False})
        self.assertFalse(tripped)
        self.assertTrue(self.breaker.is_open())
        # Explicit validation is still the only resume path.
        self.assertTrue(self.breaker.resume_after_validation(True, {}))
        self.assertFalse(self.breaker.is_open())

    def test_half_open_circuit_enforces_probe_budget_in_pipeline(self):
        """While half-open, sends beyond the probe budget must be blocked."""
        breaker = cb_mod.CircuitBreaker(
            self.store, cb_mod.BreakerConfig(half_open_cooldown_seconds=0))
        breaker._trip("test", {})
        breaker.maybe_half_open()
        self.assertTrue(breaker.is_half_open())
        runner = self._runner({"gmail": "INBOX"})
        self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        cfg = {"smtp": {}, "transport": "smtp",
               "sending_domains": ["tanim.tech"],
               "profiles": ["hello@tanim.tech"],
               "pacing": {"min_delay_seconds": 0}}
        sent = []

        def transport(c, e, r):
            sent.append(r)

        # Default half_open_probe_count=5: the pipeline records each probe
        # itself after a successful transport send.
        for i in range(5):
            self.assertTrue(breaker.probe_send_allowed(),
                            f"probe {i} should be allowed")
            pipe.send_via_pipeline(f"lead{i}@x.com", GOOD_EML, config=cfg,
                                   store=self.store, gate=self.gate,
                                   breaker=breaker, transport=transport)
        self.assertEqual(len(sent), 5)
        # Batch complete -> circuit fully closed (not stuck half-open).
        self.assertFalse(breaker.is_half_open())
        self.assertFalse(breaker.is_open())
        # An open circuit still blocks sends (pipeline guard).
        breaker._trip("reopened", {})
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline("lead@x.com", GOOD_EML, config=cfg,
                                   store=self.store, gate=self.gate,
                                   breaker=breaker, transport=transport)

    def test_bounce_rate_trips(self):
        self.breaker.evaluate({"seed_inbox_pct": 100.0, "bounce_rate": 9,
                               "complaint_rate": 0, "analyzer_grade": "A",
                               "blacklisted": False})
        self.assertTrue(self.breaker.is_open())

    def test_sender_outside_profile_allowlist_blocked(self):
        runner = self._runner({"gmail": "INBOX", "outlook": "INBOX"})
        # GOOD_EML From is hello@tanim.tech but profiles only allow nasrullahtanim.me.
        cfg = {"transport": "smtp", "smtp": {},
               "profiles": ["hello@nasrullahtanim.me"],
               "sending_domains": ["nasrullahtanim.me"]}
        decision = self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        self.assertTrue(decision["approved"])  # gate is content-based...
        # ...but the pipeline must refuse the unapproved sender identity.
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline("lead@x.com", GOOD_EML, config=cfg,
                                   store=self.store, gate=self.gate, breaker=self.breaker,
                                   transport=lambda c, e, r: None)

    def test_sender_argument_must_match_from_header(self):
        runner = self._runner({"gmail": "INBOX"})
        cfg = {"transport": "smtp", "smtp": {}, "sending_domains": ["tanim.tech"]}
        self.gate.evaluate(GOOD_EML, self.analyzer_fn, runner)
        # GOOD_EML From = hello@tanim.tech; passing a different sender must block
        # so a profile can never be smuggled under an .eml gated with another id.
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline("lead@x.com", GOOD_EML, config=cfg,
                                   store=self.store, gate=self.gate, breaker=self.breaker,
                                   transport=lambda c, e, r: None,
                                   sender="talk@tanim.tech")

    def test_empty_seed_results_fail_closed(self):
        decision = self.gate.evaluate(GOOD_EML, self.analyzer_fn, lambda eml: [])
        self.assertFalse(decision["approved"])
        self.assertFalse(self.gate.is_fresh_approved(GOOD_EML))


class TestBlacklistGate(unittest.TestCase):
    """The blacklist pre-check must FAIL CLOSED.

    Regression: it used to wrap its own ``raise BlockedSend`` in
    ``except Exception: pass``, so a listed IP sailed straight through.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.gate = gate_mod.Gate(self.store, gate_mod.GateConfig())
        self.breaker = cb_mod.CircuitBreaker(self.store, cb_mod.BreakerConfig())
        self.analyzer_fn = lambda eml: analyzer.analyze(eml, None)

    @staticmethod
    def _check(status, detail):
        return dns_checks.Check("DNSBL:Spamhaus ZEN", status, detail)

    def test_listed_ip_blocks(self):
        with mock.patch("core.dns_checks.audit_blacklists",
                        return_value=[self._check("FAIL", "listed (127.0.0.2)")]):
            with self.assertRaises(pipe.BlockedSend) as ctx:
                pipe._check_blacklist("1.2.3.4", "", self.store)
        self.assertIn("PRECHECK BLOCKED", str(ctx.exception))

    def test_clean_ip_passes(self):
        with mock.patch("core.dns_checks.audit_blacklists",
                        return_value=[self._check("PASS", "not listed")]):
            pipe._check_blacklist("1.2.3.4", "", self.store)  # no raise

    def test_inconclusive_lookup_fails_closed(self):
        with mock.patch("core.dns_checks.audit_blacklists",
                        return_value=[self._check("WARN", "lookup failed: timeout")]):
            with self.assertRaises(pipe.BlockedSend) as ctx:
                pipe._check_blacklist("1.2.3.4", "", self.store)
        self.assertIn("inconclusive", str(ctx.exception))

    def test_dns_exception_fails_closed(self):
        with mock.patch("core.dns_checks.audit_blacklists",
                        side_effect=RuntimeError("resolver down")):
            with self.assertRaises(pipe.BlockedSend):
                pipe._check_blacklist("1.2.3.4", "", self.store)

    def test_explicit_fail_open_override(self):
        with mock.patch("core.dns_checks.audit_blacklists",
                        return_value=[self._check("WARN", "lookup failed")]):
            pipe._check_blacklist("1.2.3.4", "", self.store, fail_closed=False)

    def test_pipeline_blocks_listed_ip_end_to_end(self):
        cfg = {"smtp": {}, "pacing": {"min_delay_seconds": 0},
               "sending_ip": "1.2.3.4"}
        sent = []
        with mock.patch("core.dns_checks.audit_blacklists",
                        return_value=[self._check("FAIL", "listed (127.0.0.2)")]):
            with self.assertRaises(pipe.BlockedSend):
                pipe.send_via_pipeline("lead@x.com", GOOD_EML, config=cfg,
                                       store=self.store, gate=self.gate,
                                       breaker=self.breaker,
                                       transport=lambda c, e, r: sent.append(r))
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
