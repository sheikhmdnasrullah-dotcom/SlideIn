"""Google Workspace IMAP retrieval and MIME normalization."""

from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import re
from typing import Mapping


def _header(value: str) -> str:
    return str(email.header.make_header(email.header.decode_header(value or "")))


def parse_mime_message(raw: bytes) -> dict[str, str]:
    message = email.message_from_bytes(raw)
    plain: list[str] = []
    html: list[str] = []
    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        try:
            content = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            text = content.decode(charset, "replace")
        except (LookupError, UnicodeError):
            continue
        if part.get_content_type() == "text/plain":
            plain.append(text)
        elif part.get_content_type() == "text/html":
            html.append(text)
    body = "\n".join(plain).strip()
    if not body and html:
        body = re.sub(r"<[^>]+>", " ", "\n".join(html))
        body = " ".join(body.split())
    sender = email.utils.parseaddr(_header(message.get("From", "")))[1].lower()
    external_id = _header(message.get("Message-ID", "")).strip().strip("<>").strip()
    return {
        "external_id": external_id,
        "sender_email": sender,
        "subject": _header(message.get("Subject", ""))[:512],
        "body": body,
        "in_reply_to": _header(message.get("In-Reply-To", "")).strip().strip("<>").strip(),
        "thread_id": _header(message.get("References", "")).strip().split(" ")[-1].strip("<>").strip(),
    }


class GoogleImapClient:
    def __init__(self, config: Mapping[str, object], password: str) -> None:
        self.config = config
        self.password = password

    def fetch_unseen(self) -> list[dict[str, str]]:
        host = str(self.config["imap_host"])
        port = int(self.config.get("imap_port") or 993)
        username = str(self.config["username"])
        client = imaplib.IMAP4_SSL(host, port, timeout=30)
        try:
            client.login(username, self.password)
            status, _ = client.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("Google IMAP inbox selection failed")
            status, payload = client.search(None, "UNSEEN")
            if status != "OK":
                raise RuntimeError("Google IMAP search failed")
            messages = []
            for identifier in (payload[0].split() if payload and payload[0] else [])[-50:]:
                status, fetched = client.fetch(identifier, "(BODY.PEEK[])")
                if status != "OK" or not fetched:
                    continue
                raw = next((item[1] for item in fetched if isinstance(item, tuple)), b"")
                if raw:
                    messages.append(parse_mime_message(raw))
            return messages
        finally:
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass


__all__ = ["GoogleImapClient", "parse_mime_message"]
