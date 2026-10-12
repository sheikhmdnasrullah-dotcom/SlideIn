"""DSN / bounce / complaint parser for deliverability.

Parses inbound bounce and complaint notifications so the pipeline can:
- classify hard vs soft vs transient bounces
- record spam complaints (ARF)
- auto-suppress dead/unwanted addresses
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Optional


@dataclass
class DSNResult:
    recipient: str
    status: str          # "hard_bounce" | "soft_bounce" | "deferred" | "complaint" | "unknown"
    dsn_code: str        # raw DSN status code if present
    diagnostic: str = ""


def _parse_multipart_report(msg: EmailMessage) -> dict:
    """Extract the machine-parsable report body from multipart/report."""
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "message/delivery-status":
            return {"type": "dsn", "part": part}
        if ct == "message/feedback-report":
            return {"type": "arf", "part": part}
    return {}


def _parse_dsn(part) -> Optional[DSNResult]:
    """Parse a message/delivery-status part into per-recipient status."""
    try:
        content = part.get_content()
    except Exception:
        try:
            content = part.get_payload(decode=True)
        except Exception:
            return None
    if isinstance(content, bytes):
        content = content.decode(errors="ignore")

    recipient = ""
    status_code = ""
    diagnostic = ""
    for line in content.splitlines():
        line_l = line.lower()
        if line_l.startswith("final-recipient:"):
            recipient = line.split(":", 1)[1].strip()
            if ";" in recipient:
                recipient = recipient.split(";", 1)[1].strip()
        if line_l.startswith("status:"):
            status_code = line.split(":", 1)[1].strip()
        if line_l.startswith("diagnostic-code:"):
            diagnostic = line.split(":", 1)[1].strip()

    status = _classify_dsn(status_code)
    return DSNResult(recipient=recipient, status=status, dsn_code=status_code, diagnostic=diagnostic)


def _parse_arf(part) -> Optional[DSNResult]:
    """Parse a message/feedback-report part (spam complaint)."""
    try:
        content = part.get_content()
    except Exception:
        try:
            content = part.get_payload(decode=True)
        except Exception:
            return None
    if isinstance(content, bytes):
        content = content.decode(errors="ignore")

    recipient = ""
    for line in content.splitlines():
        if line.lower().startswith("reported-email:"):
            recipient = line.split(":", 1)[1].strip()
            break
        if line.lower().startswith("original-rcpt-to:"):
            recipient = line.split(":", 1)[1].strip()
            break

    return DSNResult(recipient=recipient, status="complaint", dsn_code="ARF", diagnostic="spam complaint")


def _classify_dsn(code: str) -> str:
    """Map RFC 3464 DSN codes to deliverability actions."""
    code = code.strip()
    if not code:
        return "unknown"
    if code.startswith("5"):
        return "hard_bounce"
    if code.startswith("4"):
        return "deferred"
    if code.startswith("2"):
        return "delivered"
    return "unknown"


def parse_bounce(eml_bytes: bytes) -> DSNResult:
    """Parse a bounce/complaint notification and return structured status."""
    try:
        msg = BytesParser(policy=policy.default).parsebytes(eml_bytes)
    except Exception:
        return DSNResult(recipient="", status="unknown", dsn_code="", diagnostic="parse error")

    ct = msg.get_content_type()
    if ct == "multipart/report":
        report = _parse_multipart_report(msg)
        if report.get("type") == "dsn":
            return _parse_dsn(report["part"]) or DSNResult(recipient="", status="unknown", dsn_code="", diagnostic="no dsn body")
        if report.get("type") == "arf":
            return _parse_arf(report["part"]) or DSNResult(recipient="", status="unknown", dsn_code="", diagnostic="no arf body")

    # Try plain text DSN (non-multipart)
    if ct == "message/delivery-status":
        return _parse_dsn(msg) or DSNResult(recipient="", status="unknown", dsn_code="", diagnostic="no dsn body")

    return DSNResult(recipient="", status="unknown", dsn_code=ct, diagnostic=f"unexpected content-type {ct}")


def should_suppress(result: DSNResult) -> bool:
    """True when the recipient should be added to the suppression list."""
    return result.status in ("hard_bounce", "complaint")
