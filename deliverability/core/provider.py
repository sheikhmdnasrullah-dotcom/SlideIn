"""SlideIn Email Provider Transport Abstraction Layer.

Decouples the core email platform, campaign workers, and transactional engines
from any single MTA or delivery mechanism.

Supported Providers:
- DevSinkProvider: Direct delivery to local developer SMTP sinks (Mailpit, sink-mx)
- KumoMTAProvider: High-performance ESMTP delivery to KumoMTA with AUTH & TLS
- StandardSMTPProvider: Generic external relays (SendGrid, Resend, Mailgun, SES)
"""
from __future__ import annotations

import abc
import email
from email import policy
from email.message import EmailMessage
import os
import smtplib
import ssl
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class DeliveryResult:
    message_id: str
    status: str  # "sent", "accepted", "queued", "failed"
    provider: str
    recipient: str
    sender: str
    latency_seconds: float = 0.0
    error: Optional[str] = None
    raw_response: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in ("sent", "accepted", "queued")


class EmailProvider(abc.ABC):
    """Abstract base class for all SlideIn email transports."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. 'dev-sink', 'kumomta', 'smtp-relay')."""
        pass

    @abc.abstractmethod
    def send(
        self,
        msg: Union[bytes, EmailMessage],
        recipient: str,
        sender: str,
        **kwargs: Any,
    ) -> DeliveryResult:
        """Dispatches an email through this provider."""
        pass

    @abc.abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Checks connectivity and operational readiness of this transport."""
        pass


class DevSinkProvider(EmailProvider):
    """Local development sink provider for Mailpit / sink-mx.

    Accepts any email locally without external DNS, SPF, or domain verification.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 1025, timeout: int = 10):
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "dev-sink"

    def send(
        self,
        msg: Union[bytes, EmailMessage],
        recipient: str,
        sender: str,
        **kwargs: Any,
    ) -> DeliveryResult:
        t0 = time.time()
        eml_bytes = _ensure_bytes(msg)
        msg_id = _extract_message_id(eml_bytes)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                s.ehlo()
                s.sendmail(sender, [recipient], eml_bytes)
            latency = time.time() - t0
            return DeliveryResult(
                message_id=msg_id,
                status="sent",
                provider=self.name,
                recipient=recipient,
                sender=sender,
                latency_seconds=round(latency, 4),
                raw_response=f"Accepted by DevSink at {self.host}:{self.port}",
            )
        except Exception as e:
            latency = time.time() - t0
            return DeliveryResult(
                message_id=msg_id,
                status="failed",
                provider=self.name,
                recipient=recipient,
                sender=sender,
                latency_seconds=round(latency, 4),
                error=str(e),
            )

    def health_check(self) -> Dict[str, Any]:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                code, resp = s.ehlo()
                return {"healthy": True, "code": code, "response": resp.decode("utf-8", "ignore")}
        except Exception as e:
            return {"healthy": False, "error": str(e)}


class KumoMTAProvider(EmailProvider):
    """High-throughput enterprise transport routing through KumoMTA.

    Supports ESMTP AUTH, STARTTLS / SSL, and custom queue shaping headers.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2587,
        user: str = "outbound",
        password: str = "",
        use_tls: bool = True,
        insecure_tls: bool = True,
        timeout: int = 30,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password or os.environ.get("KUMO_AUTH_PASS", "local-dev-password")
        self.use_tls = use_tls
        self.insecure_tls = insecure_tls
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "kumomta"

    def send(
        self,
        msg: Union[bytes, EmailMessage],
        recipient: str,
        sender: str,
        **kwargs: Any,
    ) -> DeliveryResult:
        t0 = time.time()
        eml_bytes = _ensure_bytes(msg)
        msg_id = _extract_message_id(eml_bytes)

        # Ensure canonical CRLF line endings for KumoMTA compliance
        clean_bytes = eml_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")

        try:
            if self.port == 465:
                ctx = ssl.create_default_context()
                if self.insecure_tls:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=self.timeout) as s:
                    if self.user:
                        s.login(self.user, self.password)
                    s.sendmail(sender, [recipient], clean_bytes)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                    s.ehlo()
                    if self.use_tls:
                        ctx = ssl.create_default_context()
                        if self.insecure_tls:
                            ctx.check_hostname = False
                            ctx.verify_mode = ssl.CERT_NONE
                        try:
                            s.starttls(context=ctx)
                            s.ehlo()
                        except Exception as tls_err:
                            # If local Kumo is in plain mode, proceed if starttls not strictly enforced
                            pass
                    if self.user:
                        s.login(self.user, self.password)
                    s.sendmail(sender, [recipient], clean_bytes)

            latency = time.time() - t0
            return DeliveryResult(
                message_id=msg_id,
                status="accepted",
                provider=self.name,
                recipient=recipient,
                sender=sender,
                latency_seconds=round(latency, 4),
                raw_response=f"Accepted for queuing by KumoMTA at {self.host}:{self.port}",
            )
        except Exception as e:
            latency = time.time() - t0
            return DeliveryResult(
                message_id=msg_id,
                status="failed",
                provider=self.name,
                recipient=recipient,
                sender=sender,
                latency_seconds=round(latency, 4),
                error=str(e),
            )

    def health_check(self) -> Dict[str, Any]:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                code, resp = s.ehlo()
                return {"healthy": True, "code": code, "response": resp.decode("utf-8", "ignore")}
        except Exception as e:
            return {"healthy": False, "error": str(e)}


class StandardSMTPProvider(EmailProvider):
    """Standard authenticated SMTP relay (SendGrid, Resend, Mailgun, Amazon SES)."""

    def __init__(
        self,
        host: str,
        port: int = 587,
        user: str = "",
        password: str = "",
        use_tls: bool = True,
        timeout: int = 30,
        provider_name: str = "standard-smtp",
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.timeout = timeout
        self._name = provider_name

    @property
    def name(self) -> str:
        return self._name

    def send(
        self,
        msg: Union[bytes, EmailMessage],
        recipient: str,
        sender: str,
        **kwargs: Any,
    ) -> DeliveryResult:
        t0 = time.time()
        eml_bytes = _ensure_bytes(msg)
        msg_id = _extract_message_id(eml_bytes)

        try:
            if self.port == 465:
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=self.timeout) as s:
                    if self.user:
                        s.login(self.user, self.password)
                    s.sendmail(sender, [recipient], eml_bytes)
            else:
                with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                    s.ehlo()
                    if self.use_tls:
                        ctx = ssl.create_default_context()
                        s.starttls(context=ctx)
                        s.ehlo()
                    if self.user:
                        s.login(self.user, self.password)
                    s.sendmail(sender, [recipient], eml_bytes)

            latency = time.time() - t0
            return DeliveryResult(
                message_id=msg_id,
                status="sent",
                provider=self.name,
                recipient=recipient,
                sender=sender,
                latency_seconds=round(latency, 4),
            )
        except Exception as e:
            latency = time.time() - t0
            return DeliveryResult(
                message_id=msg_id,
                status="failed",
                provider=self.name,
                recipient=recipient,
                sender=sender,
                latency_seconds=round(latency, 4),
                error=str(e),
            )

    def health_check(self) -> Dict[str, Any]:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
                code, resp = s.ehlo()
                return {"healthy": True, "code": code, "response": resp.decode("utf-8", "ignore")}
        except Exception as e:
            return {"healthy": False, "error": str(e)}


class ProviderFactory:
    """Factory creating configured EmailProvider instances."""

    @staticmethod
    def get_provider(config: Dict[str, Any], transport: Optional[str] = None) -> EmailProvider:
        t = transport or config.get("transport", "kumo")

        if t == "dev-sink" or t == "mailpit":
            sink_cfg = config.get("mailpit", {})
            return DevSinkProvider(
                host=sink_cfg.get("host", "127.0.0.1"),
                port=int(sink_cfg.get("port", 1025)),
                timeout=int(sink_cfg.get("timeout", 10)),
            )

        if t == "kumo":
            kumo_cfg = config.get("kumo", {})
            return KumoMTAProvider(
                host=kumo_cfg.get("host", "127.0.0.1"),
                port=int(kumo_cfg.get("port", 2587)),
                user=kumo_cfg.get("user", "outbound"),
                password=kumo_cfg.get("password") or os.environ.get("KUMO_AUTH_PASS", "local-dev-password"),
                use_tls=bool(kumo_cfg.get("use_tls", True)),
                insecure_tls=bool(kumo_cfg.get("insecure_tls", True)),
                timeout=int(kumo_cfg.get("timeout", 30)),
            )

        if t == "sendgrid":
            sg = config.get("sendgrid", {})
            return StandardSMTPProvider(
                host=sg.get("smtp_host", "smtp.sendgrid.net"),
                port=int(sg.get("smtp_port", 587)),
                user="apikey",
                password=sg.get("api_key", ""),
                provider_name="sendgrid",
            )

        if t == "resend":
            res = config.get("resend", {})
            return StandardSMTPProvider(
                host=res.get("smtp_host", "smtp.resend.com"),
                port=int(res.get("smtp_port", 587)),
                user="resend",
                password=res.get("api_key", ""),
                provider_name="resend",
            )

        # Default fallback to standard smtp config
        smtp_cfg = config.get("smtp", {})
        return StandardSMTPProvider(
            host=smtp_cfg.get("host", "127.0.0.1"),
            port=int(smtp_cfg.get("port", 1025)),
            user=smtp_cfg.get("user", ""),
            password=smtp_cfg.get("password", ""),
            use_tls=bool(smtp_cfg.get("use_tls", False)),
            timeout=int(smtp_cfg.get("timeout", 30)),
            provider_name="smtp",
        )


def get_provider(transport: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> EmailProvider:
    """Convenience helper to get configured EmailProvider instance."""
    import json
    from pathlib import Path

    if config is None:
        cfg_path = Path(__file__).resolve().parent.parent / "config.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
        else:
            config = {}

    return ProviderFactory.get_provider(config=config, transport=transport)


def _ensure_bytes(msg: Union[bytes, EmailMessage]) -> bytes:
    if isinstance(msg, bytes):
        return msg
    return msg.as_bytes(policy=policy.SMTP)


def _extract_message_id(eml_bytes: bytes) -> str:
    try:
        parsed = email.message_from_bytes(eml_bytes, policy=policy.SMTP)
        return parsed.get("Message-ID", f"<{time.time()}@slidein.local>")
    except Exception:
        return f"<{time.time()}@slidein.local>"
