"""Tests for approved-sender parsing, envelope resolution, and rotation.

Run: python3 -m pytest tests/  (or python3 tests/test_profiles.py)
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core import state as st
from core import profiles as pm

CFG = {
    "sending_domains": ["nasrullahtanim.me"],
    "profiles": ["hello@nasrullahtanim.me", "talk@nasrullahtanim.me", "connect@nasrullahtanim.me"],
}

EML = (
    b"From: Nasrullah Tanim <hello@nasrullahtanim.me>\r\n"
    b"To: someone@example.com\r\n"
    b"Subject: your videos\r\n"
    b"\r\n"
    b"Hi, quick personal note.\r\n"
)


class TestProfiles(unittest.TestCase):
    def test_approved_profiles_flat_list(self):
        self.assertEqual(
            pm.approved_profiles(CFG),
            ["hello@nasrullahtanim.me", "talk@nasrullahtanim.me", "connect@nasrullahtanim.me"],
        )

    def test_approved_profiles_dict_entries(self):
        cfg = {"profiles": [{"email": "a@b.co"}, {"email": "c@d.co"}, {"email": "a@b.co"}]}
        self.assertEqual(pm.approved_profiles(cfg), ["a@b.co", "c@d.co"])

    def test_approved_profiles_filters_garbage(self):
        cfg = {"profiles": ["ok@b.co", "", "not-an-address", "x@y.z"]}
        self.assertEqual(pm.approved_profiles(cfg), ["ok@b.co", "x@y.z"])

    def test_is_approved_sender_allow_and_deny(self):
        self.assertTrue(pm.is_approved_sender(CFG, "hello@nasrullahtanim.me"))
        self.assertFalse(pm.is_approved_sender(CFG, "hello@tanim.tech"))
        self.assertFalse(pm.is_approved_sender(CFG, ""))

    def test_is_approved_sender_domain_only_when_no_profiles(self):
        cfg = {"sending_domains": ["tanim.tech"]}
        self.assertTrue(pm.is_approved_sender(cfg, "talk@tanim.tech"))

    def test_envelope_sender_strips_display_name(self):
        self.assertEqual(pm.envelope_sender(EML), "hello@nasrullahtanim.me")
        self.assertEqual(pm.envelope_sender(EML, "talk@nasrullahtanim.me"),
                         "talk@nasrullahtanim.me")

    def test_rotation_round_robin_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = st.Store(os.path.join(tmp, "state.db"))
            picks = [
                pm.rotate_sender(CFG, store),
                pm.rotate_sender(CFG, store),
                pm.rotate_sender(CFG, store),
                pm.rotate_sender(CFG, store),
            ]
        self.assertEqual(
            picks,
            ["hello@nasrullahtanim.me", "talk@nasrullahtanim.me",
             "connect@nasrullahtanim.me", "hello@nasrullahtanim.me"],
        )

    def test_rotation_without_store_returns_first(self):
        self.assertEqual(pm.rotate_sender(CFG, None), "hello@nasrullahtanim.me")


if __name__ == "__main__":
    unittest.main()
