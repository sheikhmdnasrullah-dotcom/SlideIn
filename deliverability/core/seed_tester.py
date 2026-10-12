"""Seed-based INBOX-PLACEMENT tester (the real placement test).

We send the EXACT production email to seed inboxes we control (Gmail, Outlook,
Yahoo, iCloud) using the SAME relay as production, then read each seed inbox back
over IMAP and detect which folder the message landed in:
  INBOX (primary) | PROMOTIONS | SPAM/JUNK | UNKNOWN.

This is the self-hosted equivalent of a commercial seed-network placement test and
requires NO paid contract. It is the core of the pre-send gate (gate.py).

Production backend: IMAPSeedReader (real IMAP). For tests: MockSeedReader.
"""
from __future__ import annotations

import email
import imaplib
import smtplib
import socket
import ssl
import time
import uuid
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses
from typing import Callable, Optional


@dataclass
class SeedAccount:
    provider: str            # "gmail" | "outlook" | "yahoo" | "icloud"
    email: str
    host: str
    port: int = 993
    password: str = ""
    inbox_folder: str = "INBOX"
    spam_folder: str = "Junk"
    use_x_gm_labels: bool = False   # Gmail exposes Promotions as a label
    extra_folders: list = field(default_factory=list)  # e.g. "[Gmail]/Spam"

    @classmethod
    def from_dict(cls, d: dict) -> "SeedAccount":
        return cls(
            provider=d["provider"], email=d["email"], host=d.get("host", ""),
            port=d.get("port", 993), password=d.get("password", ""),
            inbox_folder=d.get("inbox_folder", "INBOX"),
            spam_folder=d.get("spam_folder", "Junk"),
            use_x_gm_labels=d.get("use_x_gm_labels", d["provider"] == "gmail"),
            extra_folders=d.get("extra_folders", []),
        )


@dataclass
class SeedResult:
    provider: str
    folder: str          # INBOX | PROMOTIONS | SPAM | JUNK | UNKNOWN
    message_id: str
    passed: bool

    def to_dict(self) -> dict:
        return {"provider": self.provider, "folder": self.folder,
                "message_id": self.message_id, "passed": self.passed}


# ---------------------------------------------------------------------------
# Backend abstraction: classify where a message with `message_id` landed.
# ---------------------------------------------------------------------------
class SeedReader:
    def classify(self, account: SeedAccount, message_id: str, timeout: float = 120) -> str:
        raise NotImplementedError


class MockSeedReader(SeedReader):
    """Returns predetermined folders for tests. behavior: {provider: folder}."""
    def __init__(self, behavior: dict):
        self.behavior = behavior

    def classify(self, account: SeedAccount, message_id: str, timeout: float = 120) -> str:
        return self.behavior.get(account.provider, "UNKNOWN")


class IMAPSeedReader(SeedReader):
    def classify(self, account: SeedAccount, message_id: str, timeout: float = 120) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                folder = self._try_classify(account, message_id)
                if folder != "UNKNOWN":
                    return folder
            except (imaplib.IMAP4.error, socket.timeout, OSError) as e:
                # transient; retry until timeout
                last_err = e
            time.sleep(10)
        return "UNKNOWN"

    def _try_classify(self, account: SeedAccount, message_id: str) -> str:
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(account.host, account.port, ssl_context=ctx) as imap:
            imap.login(account.email, account.password)
            mid = message_id.strip().strip("<>")

            # Check spam/junk first
            spam_folders = [account.spam_folder] + account.extra_folders
            for f in spam_folders:
                try:
                    imap.select(f)
                    _, data = imap.search(None, "HEADER", "Message-ID", mid)
                    if data and data[0]:
                        return "SPAM"
                except imaplib.IMAP4.error:
                    continue

            # Check inbox (and Gmail promotions label)
            imap.select(account.inbox_folder)
            _, data = imap.search(None, "HEADER", "Message-ID", mid)
            if data and data[0]:
                uid = data[0].split()[0]
                if account.use_x_gm_labels:
                    try:
                        _, labels = imap.fetch(uid, "(X-GM-LABELS)")
                        lab = labels[0].decode(errors="ignore") if labels else ""
                        if "CATEGORY_PROMOTIONS" in lab:
                            return "PROMOTIONS"
                        if "CATEGORY_SPAM" in lab:
                            return "SPAM"
                    except Exception:
                        pass
                return "INBOX"
            return "UNKNOWN"


# ---------------------------------------------------------------------------
# Sending the exact production email to each seed account
# ---------------------------------------------------------------------------
def _rewrite_for_seed(eml_bytes: bytes, seed_email: str) -> tuple[bytes, str]:
    """Keep everything identical except To and a unique Message-ID per seed."""
    msg = email.message_from_bytes(eml_bytes, policy=policy.default)
    if msg.get("To"):
        msg.replace_header("To", seed_email)
    else:
        msg["To"] = seed_email
    
    from_header = msg.get("From", "")
    domain = "nasrullahtanim.me"
    if "@" in from_header:
        domain = from_header.split("@")[-1].rstrip(">").strip()
    
    new_mid = f"<{uuid.uuid4().hex}@{domain}>"
    if msg.get("Message-ID"):
        msg.replace_header("Message-ID", new_mid)
    else:
        msg["Message-ID"] = new_mid
    return _to_crlf(msg.as_bytes()), new_mid


def _to_crlf(data: bytes) -> bytes:
    """Normalize to CRLF line endings.

    email.message.as_bytes() emits LF-only bodies, and smtplib in recent CPython
    versions no longer guarantees CRLF conversion for bytes input. KumoMTA's
    submission listener rejects LF data with 552.5.6.0, so normalize explicitly.
    Safe for headers, base64 and quoted-printable bodies (a soft-break ``=\\r\\n``
    stays valid; there are no raw LFs inside encoded lines).
    """
    return data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")


def _connect_and_send(smtp_cfg: dict, from_addr: str, recipient: str,
                      data: bytes) -> None:
    """Send one message over SMTP, honouring the transport's TLS flavour.

    Supports the three setups this project uses:
      * port 465        -> implicit TLS (SMTP_SSL)
      * use_tls=True    -> STARTTLS (e.g. smtp.mailgun.org:587)
      * use_tls=False   -> plaintext submission (e.g. KumoMTA on localhost)
    """
    host = smtp_cfg["host"]
    port = int(smtp_cfg.get("port", 465))
    user = smtp_cfg.get("user", "")
    password = smtp_cfg.get("password", "")
    use_tls = bool(smtp_cfg.get("use_tls", port != 465))
    timeout = smtp_cfg.get("timeout", 30)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout) as s:
            if user:
                s.login(user, password)
            s.sendmail(from_addr, [recipient], data)
        return
    with smtplib.SMTP(host, port, timeout=timeout) as s:
        s.ehlo()
        if use_tls:
            ctx = ssl.create_default_context()
            # Self-signed listener support (KumoMTA lab/VPS deployments use a
            # local CA or self-signed cert on the submission port). Matches the
            # behavior in core/kumo_transport.py; AUTH still required.
            if smtp_cfg.get("insecure_tls", False):
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            s.starttls(context=ctx)
            s.ehlo()
        if user:
            s.login(user, password)
        s.sendmail(from_addr, [recipient], data)


def send_test_email(smtp_cfg: dict, eml_bytes: bytes, account: SeedAccount) -> str:
    """Send the (rewritten) email to one seed account; return its Message-ID."""
    data, mid = _rewrite_for_seed(eml_bytes, account.email)
    msg = email.message_from_bytes(data, policy=policy.default)
    from_raw = msg.get("From") or ""
    addrs = getaddresses([from_raw])
    from_addr = addrs[0][1].strip() if addrs and addrs[0][1] else from_raw.strip()
    _connect_and_send(smtp_cfg, from_addr, account.email, data)
    return mid


def run_seed_test(smtp_cfg: dict, seed_accounts: list[SeedAccount],
                  eml_bytes: bytes, reader: Optional[SeedReader] = None,
                  timeout: float = 180, inter_send_delay: float = 10.0) -> list[SeedResult]:
    """Send to all seeds and classify each. Returns SeedResult list."""
    reader = reader or IMAPSeedReader()
    results: list[SeedResult] = []
    for i, acc in enumerate(seed_accounts):
        try:
            mid = send_test_email(smtp_cfg, eml_bytes, acc)
        except Exception as e:
            results.append(SeedResult(acc.provider, "UNKNOWN", "", False))
            continue
        folder = reader.classify(acc, mid, timeout=timeout)
        passed = folder == "INBOX"
        results.append(SeedResult(acc.provider, folder, mid, passed))
        if i + 1 < len(seed_accounts):
            time.sleep(inter_send_delay)
    return results


def overall_pass(results: list[SeedResult]) -> bool:
    return bool(results) and all(r.passed for r in results)


if __name__ == "__main__":
    import sys, json
    print("seed_tester is a library; use cli.py seed-test", file=sys.stderr)
