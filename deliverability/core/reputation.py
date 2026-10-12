"""Reputation signals: Gmail Postmaster Tools + Outlook SNDS + blacklist.

These are OPTIONAL inputs to the circuit breaker. If credentials are absent the
functions return None/empty rather than failing the run. Gmail/Outlook require
OAuth app + API enablement (see EMAIL_SENDING_POLICY.md runbook). The MCP servers
gmail-postmaster-tools-mcp and outlook-snds-mcp can also populate these fields by
writing a JSON file the monitor reads.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

# Google OAuth token endpoint
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_POSTMASTER_API = (
    "https://gmailpostmastertools.googleapis.com/v1/domains/{domain}/trafficStats"
)


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str | None:
    body = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(_GOOGLE_TOKEN, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["access_token"]
    except Exception:
        return None


def fetch_gmail_postmaster(domain: str, creds: dict) -> dict | None:
    """Return {'spam_rate': %, 'ip_reputation': [], 'delivery_errors': []} or None."""
    token = _get_access_token(
        creds.get("client_id", ""), creds.get("client_secret", ""),
        creds.get("refresh_token", ""))
    if not token:
        return None
    url = _POSTMASTER_API.format(domain=domain) + "?startDate=2024-01-01&endDate=2024-12-31"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        # aggregate
        spam = [float(d.get("spammyRate", 0)) for d in data.get("trafficStats", [])]
        return {
            "spam_rate": (sum(spam) / len(spam) * 100) if spam else 0.0,
            "ip_reputation": [d.get("ipReputations") for d in data.get("trafficStats", [])],
            "delivery_errors": [d.get("deliveryErrors") for d in data.get("trafficStats", [])],
        }
    except Exception:
        return None


def fetch_outlook_snds(ip: str, key: str) -> dict | None:
    """Outlook.com SNDS: https://sendersupport.olc.protection.outlook.com/snds/"""
    if not key:
        return None
    url = f"https://sendersupport.olc.protection.outlook.com/snds/data.aspx?key={key}&ip={ip}"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            # CSV-ish; we only need the complaint/spam rate fields if present
            text = r.read().decode()
        return {"raw": text[:500]}
    except Exception:
        return None


def load_external_reputation_json(path: str) -> dict | None:
    """MCP servers (gmail-postmaster-tools-mcp / outlook-snds-mcp) can drop a JSON
    snapshot here; the monitor merges it into metrics."""
    if path and os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            return None
    return None


def blacklist_flag(ip: str, domain: str) -> bool:
    """Quick DNSBL check using dns_checks helper."""
    try:
        try:
            from . import dns_checks
        except ImportError:
            import dns_checks  # type: ignore
        checks = dns_checks.audit_blacklists(ip)
        return any(c.status == "FAIL" for c in checks)
    except Exception:
        return False
