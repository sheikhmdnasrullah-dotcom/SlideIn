"""Safety tests for deliverability/unspam_client.py (audit S6).

The Unspam API client must only talk to genuine Unspam endpoints over
https, must refuse to send unauthenticated requests, and must not let
caller-supplied IDs escape the intended URL path.

Run: python3 -m unittest discover -s deliverability/tests -p "test_*.py"
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import unspam_client as unspam


class UnspamClientTest(unittest.TestCase):
    def setUp(self):
        # Forbid ALL real HTTP: any request call fails the test loudly.
        req_patch = mock.patch.object(
            unspam, "requests", side_effect=AssertionError("real HTTP"))
        req_patch.start()
        self.addCleanup(req_patch.stop)

    def test_evil_base_url_rejected(self):
        for base in [
            "http://169.254.169.254/",
            "https://169.254.169.254/",
            "http://127.0.0.1:8088/",
            "https://unspam.email.evil.com/ext/v2",
            "https://evil.com/",
            "ftp://unspam.email/ext/v2",
        ]:
            with self.subTest(base=base), mock.patch.object(
                    unspam, "_cfg", return_value=("key", base)):
                with self.assertRaises(ValueError):
                    unspam.create_spam_check()

    def test_missing_api_key_rejected_before_request(self):
        with mock.patch.object(
                unspam, "_cfg",
                return_value=(None, "https://unspam.email/ext/v2")):
            with self.assertRaises(RuntimeError):
                unspam.create_spam_check()

    def test_path_traversal_id_rejected(self):
        with mock.patch.object(
                unspam, "_cfg",
                return_value=("key", "https://unspam.email/ext/v2")):
            for bad_id in ["../../etc/passwd", "a/b", "", "a b", "a?x=1"]:
                with self.subTest(bad_id=bad_id):
                    with self.assertRaises(ValueError):
                        unspam.get_spam_result(bad_id, timeout=1, poll=10)

    def test_valid_request_reaches_correct_host(self):
        fake_requests = mock.Mock()
        response = mock.Mock()
        response.json.return_value = {"id": "abc123"}
        fake_requests.post.return_value = response
        with mock.patch.object(unspam, "requests", fake_requests):
            with mock.patch.object(
                    unspam, "_cfg",
                    return_value=("key", "https://api.unspam.email/ext/v2")):
                unspam.create_spam_check()
        url = fake_requests.post.call_args[0][0]
        self.assertTrue(
            url.startswith("https://api.unspam.email/ext/v2/spam-check"),
            url)
        headers = fake_requests.post.call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer key")


if __name__ == "__main__":
    unittest.main()
