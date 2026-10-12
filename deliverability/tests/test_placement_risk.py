"""Tests for placement risk classifier and pipeline integration."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import state as st
from core import placement_risk
from core import pipeline as pipe
from core import circuit_breaker as cb_mod
from core import gate as gate_mod
from core import analyzer


class TestPlacementRiskClassifier(unittest.TestCase):
    def test_clean_email_low_risk(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: your videos\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=\"b\"\r\n"
            b"\r\n"
            b"--b\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Hey, I know you're busy. Just a quick note about your recent content.\r\n"
            b"--b\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<p>Hey, I know you're busy. Just a quick note about your recent content.</p>\r\n"
            b"--b--\r\n"
        )
        risk = placement_risk.classify_placement_risk(eml)
        self.assertEqual(risk.overall_risk, "low")
        self.assertLess(risk.promotions_risk, 30)
        self.assertLess(risk.spam_risk, 30)

    def test_promotion_triggers_increase_risk(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: limited time offer for you\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=\"b\"\r\n"
            b"\r\n"
            b"--b\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Click here to get your free discount now!\r\n"
            b"--b\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<p>Click here to get your free discount now!</p>\r\n"
            b"--b--\r\n"
        )
        risk = placement_risk.classify_placement_risk(eml)
        self.assertGreater(risk.promotions_risk, 30)
        self.assertIn("click here", [s.lower() for s in risk.promotions_signals])

    def test_list_unsubscribe_increases_promotions_risk(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: your videos\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"List-Unsubscribe: <mailto:unsub@example.com>\r\n"
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
        risk = placement_risk.classify_placement_risk(eml)
        self.assertIn("list_unsubscribe_present", [s.lower() for s in risk.promotions_signals])
        self.assertGreaterEqual(risk.promotions_risk, 20)

    def test_all_caps_increases_spam_risk(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: AMAZING DEAL\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=\"b\"\r\n"
            b"\r\n"
            b"--b\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"ACT NOW!!!\r\n"
            b"--b\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<p>ACT NOW!!!</p>\r\n"
            b"--b--\r\n"
        )
        risk = placement_risk.classify_placement_risk(eml)
        self.assertGreaterEqual(risk.spam_risk, 20)
        self.assertIn("excessive_punctuation", [s.lower() for s in risk.spam_signals])


class TestPipelinePlacementRiskGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = os.path.join(self.tmp, "state.db")
        self.store = st.Store(self.db)
        self.gate = gate_mod.Gate(self.store, gate_mod.GateConfig(require_seed=False))
        self.breaker = cb_mod.CircuitBreaker(self.store, cb_mod.BreakerConfig())
        self.analyzer_fn = lambda eml: analyzer.analyze(eml, None)

    def test_high_risk_email_blocks_send(self):
        eml = (
            b"From: hello@tanim.tech\r\n"
            b"To: lead@example.com\r\n"
            b"Subject: limited time offer\r\n"
            b"Date: Thu, 04 Sep 2026 12:00:00 +0000\r\n"
            b"Message-ID: <test@tanim.tech>\r\n"
            b"MIME-Version: 1.0\r\n"
            b"Content-Type: multipart/alternative; boundary=\"b\"\r\n"
            b"\r\n"
            b"--b\r\n"
            b"Content-Type: text/plain\r\n"
            b"\r\n"
            b"Click here for free discount!\r\n"
            b"--b\r\n"
            b"Content-Type: text/html\r\n"
            b"\r\n"
            b"<p>Click here for free discount!</p>\r\n"
            b"--b--\r\n"
        )
        self.gate.evaluate(eml, self.analyzer_fn, lambda eml: [])
        with self.assertRaises(pipe.BlockedSend):
            pipe.send_via_pipeline(
                "lead@example.com", eml,
                config={"smtp": {}, "transport": "smtp", "sending_domains": ["tanim.tech"],
                        "placement": {"max_promotions_risk": 10}},
                store=self.store, gate=self.gate, breaker=self.breaker,
                transport=lambda c, e, r: None,
            )


if __name__ == "__main__":
    unittest.main()
