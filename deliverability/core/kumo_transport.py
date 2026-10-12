"""KumoMTA transport for the approved pipeline.

Sends a raw .eml through KumoMTA's SMTP submission listener (AUTH required in
production; an unauthenticated listener would be an open relay). KumoMTA then
applies DKIM signing, traffic shaping, and routing. The compliance gate in
pipeline.py still governs every send — this module only moves bytes.

The envelope MAIL FROM defaults to the configured ``from_addr`` and MUST match
the From domain of the message for DMARC/SPF alignment.
"""
from __future__ import annotations

import smtplib
import ssl
from typing import Dict, Optional

from . import profiles as profile_mod


class KumoTransportError(Exception):
    pass


def send_via_kumo(
    eml_bytes: bytes,
    recipient: str,
    kumo_cfg: Dict,
    sender: Optional[str] = None,
) -> None:
    host = kumo_cfg["host"]
    port = int(kumo_cfg.get("port", 587))
    user = kumo_cfg.get("user") or ""
    password = kumo_cfg.get("password", "")
    use_tls = bool(kumo_cfg.get("use_tls", port != 465))
    timeout = int(kumo_cfg.get("timeout", 30))
    from_addr = sender or kumo_cfg.get("from_addr", "") or profile_mod.envelope_sender(eml_bytes) or ""
    if not from_addr:
        raise KumoTransportError(
            "no envelope sender: set config kumo.from_addr or pass sender="
        )

    import email
    from email import policy
    try:
        msg = email.message_from_bytes(eml_bytes, policy=policy.SMTP)
        # KumoMTA rejects LF-only data (552.5.6.0); as_bytes() emits LF.
        clean_bytes = msg.as_bytes(policy=policy.SMTP)
        clean_bytes = clean_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    except Exception:
        clean_bytes = eml_bytes

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=timeout) as s:
                if user:
                    s.login(user, password)
                s.sendmail(from_addr, [recipient], clean_bytes)
        else:
            with smtplib.SMTP(host, port, timeout=timeout) as s:
                s.ehlo()
                if use_tls:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    s.starttls(context=ctx)
                    s.ehlo()
                if user:
                    s.login(user, password)
                s.sendmail(from_addr, [recipient], clean_bytes)
    except smtplib.SMTPAuthenticationError as e:
        raise KumoTransportError(f"KumoMTA AUTH failed for {user}: {e.smtp_error!r}") from e
    except smtplib.SMTPRecipientsRefused as e:
        raise KumoTransportError(f"KumoMTA refused recipient {recipient}: {e.recipients}") from e
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        raise KumoTransportError(f"KumoMTA send to {host}:{port} failed: {e}") from e

