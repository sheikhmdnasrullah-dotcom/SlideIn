"""Approved sender profiles + even rotation for the deliverability pipeline.

Every outbound identity MUST be enumerated in ``config.json`` before it can be
used. This module never sends anything: it only resolves, validates, and rotates
sender identity so that a batch never blasts a single mailbox. It is the code
half of the "rotate evenly across profiles" rule in EMAIL_SENDING_POLICY.md.

All From/Reply-To/envelope addresses used in production MUST belong to one of
the configured sending domains, otherwise DMARC alignment fails and placement
collapses.
"""
from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from typing import List, Optional

_MAILBOX_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+$")


def approved_profiles(cfg: dict) -> List[str]:
    """Flatten config profiles into a de-duplicated list of bare addresses.

    Accepts either a list of strings (``"hello@domain.tld"``) or a list of
    dicts with an ``email``/``address`` key (richer per-profile config).
    """
    raw = cfg.get("profiles") or cfg.get("approved_senders") or []
    out: List[str] = []
    for item in raw:
        addr = ""
        if isinstance(item, dict):
            addr = item.get("email") or item.get("address") or ""
        else:
            addr = str(item)
        addr = addr.strip()
        if addr and _MAILBOX_RE.match(addr) and addr.lower() not in [a.lower() for a in out]:
            out.append(addr)
    return out


def approved_domains(cfg: dict) -> List[str]:
    doms = cfg.get("sending_domains") or [cfg.get("sending_domain", "")] or []
    out: List[str] = []
    for d in doms:
        d = str(d or "").strip().lower().lstrip(".")
        if d and d not in out:
            out.append(d)
    return out


def sender_domain(sender: str) -> str:
    return sender.rsplit("@", 1)[1].lower() if "@" in sender else ""


def is_approved_sender(cfg: dict, sender: str) -> bool:
    """True when ``sender`` is inside the configured profile + domain allowlist.

    If no profiles are configured, falls back to the sending-domain allowlist
    so existing configs keep working.
    """
    if not sender:
        return False
    profiles = approved_profiles(cfg)
    domains = approved_domains(cfg)
    if profiles and sender.lower() not in [p.lower() for p in profiles]:
        return False
    if domains and sender_domain(sender) not in domains:
        return False
    return True


def extract_from_value(eml_bytes: bytes) -> Optional[str]:
    """Raw ``From`` header value (may include a display name)."""
    try:
        msg = BytesParser(policy=policy.default).parsebytes(eml_bytes)
    except Exception:
        return None
    return msg["From"]


def envelope_sender(eml_bytes: bytes, sender: Optional[str] = None) -> Optional[str]:
    """Bare envelope MAIL FROM address.

    Priority: explicit ``sender`` argument > ``From`` header parsed to its bare
    address (display names stripped). Returns None when unresolvable.
    """
    if sender and "@" in sender:
        return sender.strip()
    raw = extract_from_value(eml_bytes) or ""
    addrs = getaddresses([raw])
    if addrs and addrs[0][1]:
        return addrs[0][1].strip()
    return None


def rotate_sender(cfg: dict, store, domain: Optional[str] = None) -> Optional[str]:
    """Round-robin next profile for ``domain`` (persisted in the state store).

    ``store`` may be None (then rotation is simply the first profile); with a
    store, last-used per domain is tracked so consecutive calls rotate evenly.
    """
    profiles = approved_profiles(cfg)
    if not profiles:
        return None
    if domain is None:
        domain = sender_domain(profiles[0])
    pool = [p for p in profiles if sender_domain(p) == domain] or profiles

    last = None
    if store is not None:
        last = store.get_last_sender(domain)
    if last is not None:
        try:
            idx = (pool.index(last) + 1) % len(pool)
        except ValueError:
            idx = 0
    else:
        idx = 0
    chosen = pool[idx]
    if store is not None:
        store.record_sender_used(domain, chosen)
    return chosen
