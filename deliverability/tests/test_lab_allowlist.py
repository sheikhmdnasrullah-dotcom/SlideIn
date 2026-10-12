"""Unit + integration tests for the lab-mode recipient allowlist gate.

Proves that send_via_pipeline refuses any recipient outside lab.allowed_recipients
when lab mode is enabled, fails closed on an empty allowlist, and stays out of the
way (no-op) when lab mode is disabled. Run: python3 tests/test_lab_allowlist.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import state as st
from core import analyzer
from core import seed_tester
from core import gate as gate_mod
from core import circuit_breaker as cb_mod
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
--b--
"""


class TestLabAllowlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = st.Store(os.path.join(self.tmp, "state.db"))
        self.gate = gate_mod.Gate(self.store, gate_mod.GateConfig())
        self.breaker = cb_mod.CircuitBreaker(self.store, cb_mod.BreakerConfig())
        # Pre-approve the .eml so the gate does not mask the lab gate.
        runner = lambda eml: [seed_tester.SeedResult(p, "INBOX", f"<{p}>", True)
                              for p in ("gmail", "outlook", "yahoo")]
        self.gate.evaluate(GOOD_EML, lambda e: analyzer.analyze(e, None), runner)

    def _send(self, recipient, lab):
        sent = []
        cfg = {"lab": lab, "smtp": {}, "pacing": {"min_delay_seconds": 0}}
        pipe.send_via_pipeline(recipient, GOOD_EML, config=cfg, store=self.store,
                               gate=self.gate, breaker=self.breaker,
                               transport=lambda c, e, r: sent.append(r))
        return sent

    def test_unit_empty_allowlist_blocks(self):
        with self.assertRaises(pipe.BlockedSend):
            pipe._check_lab_allowlist("anyone@example.com",
                                      {"lab": {"enabled": True, "allowed_recipients": []}})

    def test_unit_recipient_not_in_allowlist_blocks(self):
        with self.assertRaises(pipe.BlockedSend):
            pipe._check_lab_allowlist("x@x.com",
                                      {"lab": {"enabled": True, "allowed_recipients": ["ok@ok.com"]}})

    def test_unit_recipient_in_allowlist_passes(self):
        pipe._check_lab_allowlist("ok@ok.com",
                                  {"lab": {"enabled": True, "allowed_recipients": ["ok@ok.com"]}})

    def test_unit_disabled_mode_is_noop(self):
        pipe._check_lab_allowlist("anyone@example.com",
                                  {"lab": {"enabled": False, "allowed_recipients": []}})

    def test_lab_disabled_sends_normally(self):
        sent = self._send("lead@x.com", {"enabled": False, "allowed_recipients": []})
        self.assertEqual(sent, ["lead@x.com"])

    def test_lab_enabled_empty_allowlist_blocks_in_pipeline(self):
        with self.assertRaises(pipe.BlockedSend):
            self._send("lead@x.com", {"enabled": True, "allowed_recipients": []})

    def test_lab_enabled_recipient_not_allowed_blocks(self):
        with self.assertRaises(pipe.BlockedSend):
            self._send("lead@x.com", {"enabled": True, "allowed_recipients": ["allowed@x.com"]})

    def test_lab_enabled_allowed_recipient_sends(self):
        sent = self._send("allowed@x.com", {"enabled": True, "allowed_recipients": ["allowed@x.com"]})
        self.assertEqual(sent, ["allowed@x.com"])


if __name__ == "__main__":
    unittest.main()
