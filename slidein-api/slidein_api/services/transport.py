"""Sending transports.

The default is `dry_run`: it records the full dispatch and delivery
lifecycle without putting bytes on the wire. Real sending requires an
explicit transport choice plus credentials, per the repository's
live-sending policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ConfigError
from ..ids import new_id


@dataclass
class DispatchResult:
    ok: bool
    message_id: str = ""
    provider: str = ""
    detail: str = ""
    error_code: str = ""
    retryable: bool = True


class BaseTransport:
    name = "base"
    provider = "base"

    def dispatch(
        self, *, sender: str, recipient: str, subject: str, body: str,
        headers: dict | None = None,
    ) -> DispatchResult:  # pragma: no cover - interface
        raise NotImplementedError


class DryRunTransport(BaseTransport):
    """Records a dispatch without contacting any mail server."""

    name = "dry_run"
    provider = "slidein.dry_run"

    def dispatch(
        self, *, sender: str, recipient: str, subject: str, body: str,
        headers: dict | None = None,
    ) -> DispatchResult:
        return DispatchResult(
            ok=True,
            message_id=f"<{new_id('sent')}@dry-run.slidein.local>",
            provider=self.provider,
            detail="dry_run transport accepted the message (nothing was sent)",
        )


class SMTPTransport(BaseTransport):
    """Real SMTP dispatch through the tenant's sending identity."""

    name = "smtp"
    provider = "smtp"

    def __init__(self, *, host: str, port: int, username: str = "", password: str = "",
                 use_tls: bool = True) -> None:
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def dispatch(
        self, *, sender: str, recipient: str, subject: str, body: str,
        headers: dict | None = None,
    ) -> DispatchResult:
        import smtplib
        from email.message import EmailMessage

        message = EmailMessage()
        message["From"] = sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        for key, value in (headers or {}).items():
            message[key] = value

        try:
            if self.use_tls:
                client = smtplib.SMTP_SSL(self.host, self.port, timeout=20)
            else:
                client = smtplib.SMTP(self.host, self.port, timeout=20)
            with client:
                if not self.use_tls:
                    client.starttls()
                if self.username:
                    client.login(self.username, self.password)
                client.send_message(message)
        except Exception as exc:  # noqa: BLE001 - any transport failure is reported
            return DispatchResult(
                ok=False,
                detail=f"{type(exc).__name__}: {exc}",
                error_code="provider_unavailable",
                retryable=True,
            )
        return DispatchResult(
            ok=True,
            message_id=message["Message-ID"] or f"<{new_id('sent')}@smtp>",
            provider=self.provider,
            detail=f"accepted by {self.host}:{self.port}",
        )


class TransportRegistry:
    """Selects the transport from configuration. Defaults to dry_run."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = dict(config or {})

    def resolve(self) -> BaseTransport:
        kind = (self.config.get("transport") or "dry_run").lower()
        if kind == "dry_run":
            return DryRunTransport()
        if kind == "smtp":
            return SMTPTransport(
                host=str(self.config.get("smtp_host", "127.0.0.1")),
                port=int(self.config.get("smtp_port", 587)),
                username=str(self.config.get("smtp_username", "")),
                password=str(self.config.get("smtp_password", "")),
                use_tls=bool(self.config.get("smtp_use_tls", True)),
            )
        raise ConfigError(
            f"Unknown transport {kind!r}",
            code="provider_unavailable",
            recovery_action="retry_stage",
        )


TRANSPORTS = {"dry_run": DryRunTransport, "smtp": SMTPTransport}


def get_transport(config: dict | None = None) -> BaseTransport:
    return TransportRegistry(config).resolve()


__all__ = [
    "TRANSPORTS",
    "BaseTransport",
    "DispatchResult",
    "DryRunTransport",
    "SMTPTransport",
    "TransportRegistry",
    "get_transport",
]
