"""SSRF tests for deliverability/webhook_server.py (audit S1).

SNS SubscriptionConfirmation must only ever fetch genuine AWS SNS
endpoints: https scheme, sns.<region>.amazonaws.com host, no redirects.
Anything else is rejected with 400 and NO fetch is attempted.

Socket-free: the handler instance is faked with in-memory streams, and
urllib is patched so no real HTTP request can leave the test process.

Run: python3 -m unittest discover -s deliverability/tests -p "test_*.py"
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
from email.message import Message
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import webhook_server as webhook_mod


GOOD_URL = (
    "https://sns.us-east-1.amazonaws.com/"
    "?Action=ConfirmSubscription&Token=abc&TopicArn=arn:aws:sns:us-east-1:123:t"
)

EVIL_URLS = [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata, plain http
    "https://169.254.169.254/latest/meta-data/",  # cloud metadata over TLS
    "http://127.0.0.1:8088/v1/status",  # loopback
    "https://sns.us-east-1.amazonaws.com.evil.com/",  # lookalike suffix
    "https://evil.com/?x=https://sns.us-east-1.amazonaws.com/",  # nested
    "https://sns.us-east-1.amazonaws.com:8443/",  # non-standard port
    "ftp://sns.us-east-1.amazonaws.com/",  # wrong scheme
    "not-a-url",
    "",
]


def make_handler(path, payload):
    handler = webhook_mod.WebhookHandler.__new__(webhook_mod.WebhookHandler)
    handler.command = "POST"
    handler.path = path
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"POST {path} HTTP/1.1"
    body = json.dumps(payload).encode("utf-8")
    headers = Message()
    headers["Content-Type"] = "application/json"
    headers["Content-Length"] = str(len(body))
    handler.headers = headers
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.client_address = ("127.0.0.1", 0)
    return handler


def post(path, payload):
    handler = make_handler(path, payload)
    handler.do_POST()
    raw = handler.wfile.getvalue()
    head, _, response_body = raw.partition(b"\r\n\r\n")
    status = int(head.split(b"\r\n")[0].decode("latin-1").split()[1])
    return status, response_body


class SnsConfirmationTest(unittest.TestCase):
    def setUp(self):
        # No signature gate in these tests; restore afterwards.
        self._old_secret = webhook_mod.WEBHOOK_SECRET
        webhook_mod.WEBHOOK_SECRET = ""
        self.addCleanup(setattr, webhook_mod, "WEBHOOK_SECRET", self._old_secret)
        # Forbid ALL real fetches: any urlopen call fails the test loudly.
        urlopen_patch = mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("real fetch attempted"),
        )
        urlopen_patch.start()
        self.addCleanup(urlopen_patch.stop)

    def confirm(self, url):
        return post(
            "/webhook/ses",
            {"Type": "SubscriptionConfirmation", "SubscribeURL": url},
        )

    def test_evil_urls_rejected_without_fetch(self):
        for url in EVIL_URLS:
            with self.subTest(url=url):
                status, body = self.confirm(url)
                self.assertEqual(status, 400, body.decode("utf-8"))

    def test_missing_url_rejected(self):
        status, _ = post("/webhook/ses", {"Type": "SubscriptionConfirmation"})
        self.assertEqual(status, 400)

    def test_valid_sns_url_confirms(self):
        opener = mock.Mock()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"<ConfirmSubscriptionResponse/>"
        opener.open.return_value = response
        with mock.patch(
            "urllib.request.build_opener", return_value=opener
        ) as build_opener:
            status, body = self.confirm(GOOD_URL)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "confirmed")
        # Exactly one fetch, to the validated URL, via a no-redirect opener.
        opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args[0][0], GOOD_URL)
        redirect_handlers = [
            handler
            for a in build_opener.call_args_list
            for handler in a[0]
            if "Redirect" in getattr(handler, "__name__", type(handler).__name__)
        ]
        self.assertTrue(
            redirect_handlers, "expected a redirect-blocking handler in opener"
        )


def signed_post(path, payload, secret):
    """POST with a valid HMAC signature for the given secret."""
    import hashlib
    import hmac

    body = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256).hexdigest()
    handler = make_handler(path, payload)
    handler.headers["X-Hub-Signature-256"] = sig
    handler.do_POST()
    raw = handler.wfile.getvalue()
    head = raw.partition(b"\r\n\r\n")[0]
    status = int(head.split(b"\r\n")[0].decode("latin-1").split()[1])
    return status


class WebhookSecretTest(unittest.TestCase):
    """HMAC routes refuse unsigned traffic; missing secret fails closed."""

    def setUp(self):
        self._old_secret = webhook_mod.WEBHOOK_SECRET
        self.addCleanup(setattr, webhook_mod, "WEBHOOK_SECRET", self._old_secret)
        processor = mock.Mock()
        processor.process_sendgrid_webhook.return_value = []
        processor.process_sns_notification.return_value = []
        proc_patch = mock.patch.object(
            webhook_mod.WebhookHandler, "processor", processor)
        proc_patch.start()
        self.addCleanup(proc_patch.stop)

    def test_unsigned_rejected_when_secret_set(self):
        webhook_mod.WEBHOOK_SECRET = "test-secret"
        status, _ = post("/webhook/sendgrid", [])
        self.assertEqual(status, 401)

    def test_signed_accepted_when_secret_set(self):
        webhook_mod.WEBHOOK_SECRET = "test-secret"
        status = signed_post("/webhook/sendgrid", [], "test-secret")
        self.assertEqual(status, 200)

    def test_missing_secret_fails_closed(self):
        webhook_mod.WEBHOOK_SECRET = ""
        status, body = post("/webhook/sendgrid", [])
        self.assertEqual(status, 503)
        self.assertIn("misconfigured", body.decode("utf-8"))

    def test_ses_exempt_from_hmac(self):
        # SNS cannot produce our HMAC (AWS signs differently); the SES
        # route must not 401 genuine SNS traffic when a secret is set.
        webhook_mod.WEBHOOK_SECRET = "test-secret"
        opener = mock.Mock()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"<ok/>"
        opener.open.return_value = response
        with mock.patch(
                "urllib.request.build_opener", return_value=opener):
            handler = make_handler("/webhook/ses", {
                "Type": "SubscriptionConfirmation",
                "SubscribeURL": GOOD_URL,
            })
            handler.do_POST()
            raw = handler.wfile.getvalue()
        status = int(raw.partition(b"\r\n\r\n")[0].split(b"\r\n")[0]
                     .decode("latin-1").split()[1])
        self.assertEqual(status, 200)


class SnsTopicAllowlistTest(unittest.TestCase):
    def setUp(self):
        self._old_secret = webhook_mod.WEBHOOK_SECRET
        self._old_topics = webhook_mod.SNS_TOPIC_ARNS
        self.addCleanup(setattr, webhook_mod, "WEBHOOK_SECRET", self._old_secret)
        self.addCleanup(setattr, webhook_mod, "SNS_TOPIC_ARNS", self._old_topics)
        webhook_mod.WEBHOOK_SECRET = ""
        processor = mock.Mock()
        processor.process_sns_notification.return_value = []
        proc_patch = mock.patch.object(
            webhook_mod.WebhookHandler, "processor", processor)
        proc_patch.start()
        self.addCleanup(proc_patch.stop)

    def test_foreign_topic_rejected_when_allowlist_set(self):
        webhook_mod.SNS_TOPIC_ARNS = "arn:aws:sns:us-east-1:123:good"
        status, _ = post("/webhook/ses", {
            "Type": "Notification",
            "TopicArn": "arn:aws:sns:us-east-1:999:evil",
            "Message": "{}",
        })
        self.assertEqual(status, 403)

    def test_listed_topic_accepted(self):
        webhook_mod.SNS_TOPIC_ARNS = "arn:aws:sns:us-east-1:123:good"
        status, _ = post("/webhook/ses", {
            "Type": "Notification",
            "TopicArn": "arn:aws:sns:us-east-1:123:good",
            "Message": "{}",
        })
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main()
