"""Eligibility tests for deliverability/campaign_worker.py.

The bulk sender must consult the same safety core as the approved
pipeline path: per-recipient suppression and the circuit-breaker state.
Suppressed recipients are skipped and an open breaker halts the run —
in both cases WITHOUT dispatching.

Run: python3 -m unittest discover -s deliverability/tests -p "test_*.py"
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import campaign_worker as worker
from core import state as st
from core.circuit_breaker import BreakerConfig, CircuitBreaker


def make_lead(email="prospect@example.com"):
    return {
        "Email": email,
        "First Name": "Pat",
        "Last Name": "Lee",
        "Position": "Owner",
        "csv_source": "safe1.csv",
    }


FAKE_META = {
    "subject": "Pat?",
    "message_id": "<fake@example.com>",
    "mx_id": "mx.test",
    "provider": "test",
    "detected_niche": "test",
    "ghost_ink_length": 200,
}


class CampaignEligibilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.conn = worker.init_db(os.path.join(self.tmp.name, "outreach.db"))
        self.addCleanup(self.conn.close)
        self.store = st.Store(os.path.join(self.tmp.name, "state.db"))
        self.breaker = CircuitBreaker(self.store, BreakerConfig())
        self.profile = {"name": "Test Sender", "email": "hello@example.com"}

    def process(self, lead):
        with mock.patch.object(
            worker, "send_canonical_bulletproof_outreach",
            return_value=dict(FAKE_META),
        ) as dispatch:
            result = worker.process_lead(
                self.conn, self.store, self.breaker, {}, lead, self.profile
            )
        return result, dispatch

    def test_suppressed_recipient_skipped_without_dispatch(self):
        self.store.suppress("prospect@example.com", "bounce")
        result, dispatch = self.process(make_lead())
        self.assertEqual(result["status"], "skipped_suppressed")
        dispatch.assert_not_called()
        self.assertFalse(
            worker.is_already_sent(self.conn, "prospect@example.com"))

    def test_open_breaker_halts_without_dispatch(self):
        self.store.set_circuit("open", "test trip", {})
        result, dispatch = self.process(make_lead())
        self.assertEqual(result["status"], "blocked_breaker")
        dispatch.assert_not_called()

    def test_eligible_recipient_sends(self):
        result, dispatch = self.process(make_lead())
        self.assertEqual(result["status"], "sent")
        dispatch.assert_called_once()
        self.assertTrue(
            worker.is_already_sent(self.conn, "prospect@example.com"))

    def test_duplicate_send_skipped_without_dispatch(self):
        self.process(make_lead())
        result, dispatch = self.process(make_lead())
        self.assertEqual(result["status"], "already_sent")
        dispatch.assert_not_called()

    def test_invalid_email_rejected_without_dispatch(self):
        result, dispatch = self.process(make_lead(email="not-an-email"))
        self.assertEqual(result["status"], "error_invalid_email")
        dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
