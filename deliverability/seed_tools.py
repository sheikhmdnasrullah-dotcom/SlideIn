#!/usr/bin/env python3
"""SMTP submission and seed-mailbox placement helpers.

Shared by the seed tests and the Ghost ink tooling. Extracted from a one-off
campaign script so reusable code does not live next to recipient data.
"""
import email
import email.utils
import imaplib
import smtplib
import ssl
import time
from email import policy
from email.message import EmailMessage
from pathlib import Path
import sys

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from preflight_verifier import load_config  # noqa: E402,F401  (re-exported)


def send_smtp(config: dict, from_addr: str, to_addr: str, msg_bytes: bytes, max_retries: int = 3) -> bool:
    kumo = config.get("kumo", {})
    host = kumo.get("host", "127.0.0.1")
    port = int(kumo.get("port", 2587))
    user = kumo.get("user", "outbound")
    password = kumo.get("password") or os.environ.get("KUMO_AUTH_PASS", "local-dev-password")

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            server = smtplib.SMTP(host=host, port=port, timeout=25)
            server.ehlo()
            if server.has_extn("STARTTLS"):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                server.starttls(context=ctx)
                server.ehlo()
            if user and password:
                server.login(user, password)
            msg = email.message_from_bytes(msg_bytes, policy=policy.default)
            data = msg.as_bytes(policy=policy.SMTP)
            server.sendmail(from_addr, [to_addr], data)
            server.quit()
            return True
        except Exception as exc:
            last_exc = exc
            print(f"⚠️ SMTP connection attempt {attempt}/{max_retries} failed: {exc}. Retrying in 4s...", flush=True)
            time.sleep(4)
    raise last_exc


def check_seed_placement(account: dict, target_msg_id: str, timeout: int = 40) -> tuple[str, dict]:
    ctx = ssl.create_default_context()
    clean_mid = target_msg_id.strip("<>").strip()
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            imap = imaplib.IMAP4_SSL(account["host"], account.get("port", 993), ssl_context=ctx, timeout=12)
            imap.login(account["email"], account["password"])

            # Check Spam
            try:
                imap.select("[Gmail]/Spam")
                _, data = imap.search(None, "HEADER", "Message-ID", clean_mid)
                if data and data[0]:
                    uid = data[0].split()[0]
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    parsed = email.message_from_bytes(msg_data[0][1], policy=policy.default)
                    imap.logout()
                    return "SPAM", dict(parsed.items())
            except Exception:
                pass

            # Check INBOX
            imap.select("INBOX")
            _, data = imap.search(None, "HEADER", "Message-ID", clean_mid)
            if data and data[0]:
                uid = data[0].split()[0]
                folder = "INBOX"
                try:
                    _, labels = imap.fetch(uid, "(X-GM-LABELS)")
                    lab = labels[0].decode(errors="ignore") if labels else ""
                    if "CATEGORY_PROMOTIONS" in lab:
                        folder = "PROMOTIONS"
                except Exception:
                    pass
                _, msg_data = imap.fetch(uid, "(RFC822)")
                parsed = email.message_from_bytes(msg_data[0][1], policy=policy.default)
                imap.logout()
                return folder, dict(parsed.items())

            imap.logout()
        except Exception:
            pass

        time.sleep(4)

    return "UNKNOWN", {}


