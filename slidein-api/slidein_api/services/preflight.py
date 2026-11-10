"""Pre-send deliverability preflight — the canonical path.

This transfers the verified operational practice from the live daemon
(`deliverability/advanced_deliverability.py`) into the reusable API:

  * MX / recipient-domain resolution via stdlib (no new dependency),
  * spam-copy heuristic audit ported from the daemon's SpamHeuristicScanner,
  * Reacher recipient verification through the canonical HTTP adapter.

Design choices that follow the project's "never infer deliverability" rule:

  * MX resolution degrades to "unverified" (never "ok") when DNS is
    unavailable, so the canonical path never fakes a positive verdict.
  * The copy audit is a pure function — testable offline with no network.
  * Dry-run transport records DNS and Reacher outcomes without blocking.
  * Live transports (kumo/smtp) require a clean copy audit and Reacher `safe`
    verdict. Verification never establishes consent.
"""

from __future__ import annotations

import re
import socket
import subprocess
from dataclasses import dataclass, field

from ..errors import ProviderError, SlideinError
from ..integrations.reacher import ReacherAdapter

HIGH_RISK_TRIGGERS: tuple[str, ...] = (
    "100% free", "guaranteed income", "risk free", "no risk",
    "make money fast", "act now", "limited time offer", "urgent response",
    "wire transfer", "click here", "buy now", "credit card", "winner",
)

_ALLCAPS_ALLOWLIST = frozenset(
    {"SEO", "API", "URL", "ICP", "SaaS", "USA", "UK", "CRM", "PPM", "HMO"}
)


class PreflightError(SlideinError):
    """Raised when a pre-send check fails for a live (non dry-run) transport."""

    code = "transport_rejected"


@dataclass
class MxResult:
    domain: str
    valid: bool
    mx_id: str = ""
    provider: str = "Standard SMTP"
    detail: str = ""
    verified: bool = False


@dataclass
class PreflightResult:
    recipient_domain: str
    mx: MxResult
    audit: dict
    passed: bool = True
    errors: list[str] = field(default_factory=list)


def audit_copy(subject: str, body: str) -> dict:
    """Spam-heuristic audit of outbound copy (pure function, no I/O).

    Ported from the daemon's SpamHeuristicScanner.audit_copy so the
    canonical send path enforces the same copy-quality bar that live
    operations already use.
    """
    combined = f"{subject or ''} {body or ''}".lower()
    flags: list[str] = []

    for phrase in HIGH_RISK_TRIGGERS:
        if phrase in combined:
            flags.append(f"High-risk spam phrase detected: '{phrase}'")

    if body.count("!") > 3:
        flags.append(f"Excessive exclamation marks ({body.count('!')} total)")

    all_caps = [
        w for w in re.findall(r"\b[A-Z]{3,}\b", (subject or "") + " " + (body or ""))
        if w not in _ALLCAPS_ALLOWLIST
    ]
    if len(all_caps) > 2:
        flags.append(f"Multiple all-caps words detected: {all_caps}")

    return {"score": len(flags), "passed": len(flags) == 0, "flags": flags}


def _mx_provider(h_hosts: str) -> str:
    h = h_hosts.lower()
    if "google" in h or "googlemail" in h or "aspmx" in h:
        return "Google Workspace / Gmail"
    if "outlook" in h or "microsoft" in h or "office365" in h or "pphosted" in h:
        return "Microsoft 365"
    if "zoho" in h:
        return "Zoho Mail"
    if "icloud" in h or "apple" in h:
        return "Apple iCloud"
    if "yahoo" in h or "yahoodns" in h:
        return "Yahoo Mail"
    if "mimecast" in h:
        return "Mimecast Secure"
    return "Standard SMTP"


def resolve_mx(domain: str) -> MxResult:
    """Resolve MX records for a recipient domain.

    Uses stdlib subprocess (host/dig) plus a socket A-record fallback — no
    third-party DNS dependency. When DNS cannot be resolved the result is
    marked ``verified=False`` (never silently "valid"), so callers cannot
    mistake an offline probe for deliverability proof.
    """
    domain = domain.strip().lower()
    if not domain:
        return MxResult(domain=domain, valid=False, detail="Empty domain", verified=False)

    mx_hosts: list[str] = []

    for cmd, args in (
        (["host", "-t", "mx", domain], True),
        (["dig", "+short", "MX", domain], False),
    ):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            mx_hosts = []
            continue
        if res.returncode != 0:
            continue
        for line in res.stdout.splitlines():
            if "mail is handled by" in line:
                parts = line.split("mail is handled by")
                if len(parts) > 1:
                    tokens = parts[1].strip().split()
                    if tokens:
                        mx_hosts.append(tokens[-1].rstrip("."))
            elif args is False:
                tokens = line.strip().split()
                if len(tokens) >= 2:
                    mx_hosts.append(tokens[1].rstrip("."))
                elif len(tokens) == 1:
                    mx_hosts.append(tokens[0].rstrip("."))
        if mx_hosts:
            break

    primary_mx = mx_hosts[0] if mx_hosts else ""
    valid = bool(mx_hosts)

    if not valid:
        try:
            socket.gethostbyname(domain)
            valid = True
            primary_mx = f"A-record:{domain}"
        except socket.gaierror:
            valid = False

    provider = _mx_provider(" ".join(mx_hosts)) if mx_hosts else "Standard SMTP"
    detail = (
        f"MX: {primary_mx} ({provider})" if valid
        else f"No valid MX or A record found for {domain}"
    )

    return MxResult(
        domain=domain,
        valid=valid,
        mx_id=primary_mx,
        provider=provider,
        detail=detail,
        verified=valid,
    )


def preflight_recipient(email: str) -> PreflightResult:
    """Full recipient preflight: syntax + MX."""
    normalized = str(email or "").strip().lower()
    domain = ""
    if "@" in normalized:
        domain = normalized.split("@")[-1]

    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", normalized):
        return PreflightResult(
            recipient_domain=domain,
            mx=MxResult(domain=domain, valid=False, detail="Invalid email syntax", verified=False),
            audit=audit_copy("", ""),
            passed=False,
            errors=["Invalid recipient email syntax"],
        )

    mx = resolve_mx(domain)
    errors: list[str] = []
    passed = True
    if not mx.valid:
        passed = False
        errors.append(f"No deliverable MX/A record for {domain}: {mx.detail}")

    return PreflightResult(
        recipient_domain=domain,
        mx=mx,
        audit=audit_copy("", ""),
        passed=passed,
        errors=errors,
    )


def preflight_message(recipient_email: str, subject: str, body: str) -> PreflightResult:
    """Full message preflight: recipient MX + copy audit."""
    result = preflight_recipient(recipient_email)
    result.audit = audit_copy(subject, body)
    result.passed = result.mx.valid and result.audit["passed"]
    if not result.audit["passed"]:
        result.errors.extend(result.audit["flags"])
    return result


async def reacher_verification(email: str) -> dict:
    try:
        return await ReacherAdapter().verify(email)
    except ProviderError as exc:
        return {
            "collector": "reacher",
            "status": "not_configured" if exc.details.get("missing") else "unavailable",
            "verified": False,
            "consent_verified": False,
            "error_code": exc.code,
        }
