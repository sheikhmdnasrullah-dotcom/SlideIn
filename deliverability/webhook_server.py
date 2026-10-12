"""Webhook HTTP server for receiving delivery events.

Minimal HTTP server that receives webhooks from email providers
(SES, SendGrid, Postmark, Mailgun) and processes them.

Usage:
    python3 webhook_server.py [--port 8080] [--host 0.0.0.0]
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from urllib.parse import parse_qs, urlparse

# Add parent to path for imports
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from core.webhook import WebhookProcessor


# Configuration
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8080"))
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
DB_PATH = os.environ.get("DB_PATH", os.path.join(HERE, "deliverability_state.db"))
# Optional comma-separated SNS TopicArn allowlist for /webhook/ses.
# SNS cannot produce our HMAC (AWS signs differently), so HMAC routes and
# the SES route authenticate differently by design; full SNS message-
# signature verification remains a Stage 5 follow-up (needs non-stdlib
# crypto). When set, foreign TopicArns are rejected with 403.
SNS_TOPIC_ARNS = os.environ.get("SNS_TOPIC_ARNS", "")

# Genuine SNS subscription endpoints only: real SubscribeURL values always
# have this shape (https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html).
_SNS_HOST_RE = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com(\.cn)?$", re.IGNORECASE)

# Residual risk (documented, not fixed here): full SNS message-signature
# verification needs RSA/X.509, which the stdlib cannot do and this engine
# deliberately avoids adding as a dependency. The hostname allowlist +
# https-only + no-redirect fetch below kills the SSRF; signature checks
# remain a follow-up if provider-message authenticity is ever required.


def is_valid_sns_subscription_url(url: str) -> bool:
    """True only for genuine SNS subscription-confirmation endpoints."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https":
        return False
    if parsed.username or parsed.password:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None and port != 443:
        return False
    host = parsed.hostname or ""
    return _SNS_HOST_RE.match(host) is not None


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse all redirects: an allowlisted URL must not bounce elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            newurl, code, "redirects disabled for SNS confirmation", headers, fp
        )


def fetch_subscription_confirmation(url: str, timeout: int = 5) -> None:
    """GET a validated SNS SubscribeURL without following redirects."""
    opener = urllib.request.build_opener(_NoRedirectHandler)
    with opener.open(url, timeout=timeout) as resp:
        resp.read(65536)


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for webhook events."""
    
    processor: Optional[WebhookProcessor] = None
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass
    
    def do_GET(self):
        """Health check endpoint."""
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "timestamp": time.time()})
        else:
            self._send_json(404, {"error": "not found"})
    
    def do_POST(self):
        """Handle webhook POST requests."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        path = urlparse(self.path).path

        # HMAC routes require the shared secret; a missing secret fails
        # closed (503) instead of silently accepting unsigned traffic.
        # /webhook/ses is exempt: SNS authenticates via AWS signatures,
        # not our HMAC (see SNS_TOPIC_ARNS + Stage 5 follow-up).
        if path != "/webhook/ses":
            if not WEBHOOK_SECRET:
                self._send_json(503, {"error": "webhook receiver misconfigured: WEBHOOK_SECRET is not set"})
                return
            if not self._verify_signature(body):
                self._send_json(401, {"error": "invalid signature"})
                return

        try:
            if path == "/webhook/ses":
                self._handle_ses(body)
            elif path == "/webhook/sendgrid":
                self._handle_sendgrid(body)
            elif path == "/webhook/postmark":
                self._handle_postmark(body)
            elif path == "/webhook/mailgun":
                self._handle_mailgun(body)
            elif path == "/webhook/generic":
                self._handle_generic(body)
            else:
                self._send_json(404, {"error": "unknown webhook endpoint"})
        except Exception as e:
            self._send_json(500, {"error": str(e)})
    
    def _handle_ses(self, body: bytes):
        """Process AWS SES webhook."""
        payload = json.loads(body)

        allowed_topics = [a.strip() for a in SNS_TOPIC_ARNS.split(",") if a.strip()]
        if allowed_topics and payload.get("TopicArn") not in allowed_topics:
            self._send_json(403, {"error": "TopicArn not allowlisted"})
            return

        # Handle SNS subscription confirmation
        if payload.get("Type") == "SubscriptionConfirmation":
            subscribe_url = payload.get("SubscribeURL", "")
            if not is_valid_sns_subscription_url(subscribe_url):
                self._send_json(400, {"error": "invalid SubscribeURL"})
                return
            try:
                fetch_subscription_confirmation(subscribe_url, timeout=5)
                self._send_json(200, {"status": "confirmed"})
            except Exception as e:
                self._send_json(500, {"error": f"confirmation failed: {e}"})
            return
        
        events = self.processor.process_sns_notification(payload)
        self._send_json(200, {"status": "ok", "events_processed": len(events)})
    
    def _handle_sendgrid(self, body: bytes):
        """Process SendGrid webhook."""
        payload = json.loads(body)
        events = self.processor.process_sendgrid_webhook(payload)
        self._send_json(200, {"status": "ok", "events_processed": len(events)})
    
    def _handle_postmark(self, body: bytes):
        """Process Postmark webhook."""
        payload = json.loads(body)
        events = self.processor.process_postmark_webhook(payload)
        self._send_json(200, {"status": "ok", "events_processed": len(events)})
    
    def _handle_mailgun(self, body: bytes):
        """Process Mailgun webhook."""
        payload = json.loads(body)
        event_type = payload.get("event", "")
        events = self.processor.process_mailgun_webhook(event_type, payload)
        self._send_json(200, {"status": "ok", "events_processed": len(events)})
    
    def _handle_generic(self, body: bytes):
        """Process generic bounce message."""
        events = self.processor.process_generic_bounce(body)
        self._send_json(200, {"status": "ok", "events_processed": 1 if events else 0})
    
    def _verify_signature(self, body: bytes) -> bool:
        """Verify webhook signature."""
        signature = self.headers.get("X-Hub-Signature-256", "")
        if not signature:
            signature = self.headers.get("X-Webhook-Signature", "")
        
        if not signature:
            return False
        
        expected = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)
    
    def _send_json(self, status_code: int, data: dict):
        """Send JSON response."""
        response = json.dumps(data).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Webhook server for email delivery tracking")
    parser.add_argument("--port", type=int, default=WEBHOOK_PORT)
    parser.add_argument("--host", default=WEBHOOK_HOST)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    if not WEBHOOK_SECRET:
        print("WARNING: WEBHOOK_SECRET is not set — HMAC webhook routes "
              "will refuse all traffic (503).", file=sys.stderr)

    # Initialize processor
    WebhookHandler.processor = WebhookProcessor(args.db)
    
    # Start server
    server = HTTPServer((args.host, args.port), WebhookHandler)
    print(f"Webhook server listening on {args.host}:{args.port}")
    print(f"Endpoints:")
    print(f"  POST /webhook/ses        - AWS SES notifications")
    print(f"  POST /webhook/sendgrid   - SendGrid events")
    print(f"  POST /webhook/postmark   - Postmark events")
    print(f"  POST /webhook/mailgun    - Mailgun events")
    print(f"  POST /webhook/generic    - Generic bounce messages")
    print(f"  GET  /health             - Health check")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
        WebhookHandler.processor.close()


if __name__ == "__main__":
    main()
