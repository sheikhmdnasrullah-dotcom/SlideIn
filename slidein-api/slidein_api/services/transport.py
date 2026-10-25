"""Sending transports.

The default is `dry_run`: it records the full dispatch and delivery
lifecycle without putting bytes on the wire. Real sending requires an
explicit transport choice plus credentials, per the repository's
live-sending policy.
"""

from __future__ import annotations

import os
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
    """Selects the transport from configuration. Defaults to dry_run.

    Precedence: explicit config (request payload) > environment >
    dry_run. The env path is what the Autopilot send step and any caller
    that passes ``transport_config={}`` uses:

    ============================  ==================================================
    ``SLIDEIN_TRANSPORT``         ``dry_run`` (default), ``smtp`` or ``kumo``.
    ``SLIDEIN_SMTP_HOST/PORT/USER/PASS``  SMTP credentials. For ``kumo`` these
                                  fall back to ``KUMO_HOST`` / ``KUMO_SMTP_PORT`` /
                                  ``KUMO_AUTH_USER`` / ``KUMO_AUTH_PASS`` and then
                                  to the local KumoMTA submission endpoint
                                  (127.0.0.1:2587, user ``outbound``).
    ``SLIDEIN_SMTP_TLS``          ``0`` disables STARTTLS (default on).
    ============================  ==================================================
    """

    def __init__(self, config: dict | None = None) -> None:
        self.config = dict(config or {})

    def _merged(self) -> dict:
        return {**env_transport_config(), **self.config}

    def resolve(self) -> BaseTransport:
        merged = self._merged()
        kind = (merged.get("transport") or "dry_run").lower()
        if kind == "dry_run":
            return DryRunTransport()
        if kind in ("smtp", "kumo"):
            return SMTPTransport(
                host=str(merged.get("smtp_host") or "127.0.0.1"),
                port=int(merged.get("smtp_port") or 587),
                username=str(merged.get("smtp_username") or ""),
                password=str(merged.get("smtp_password") or ""),
                use_tls=bool(merged.get("smtp_use_tls", True)),
            )
        raise ConfigError(
            f"Unknown transport {kind!r}",
            code="provider_unavailable",
            recovery_action="retry_stage",
        )


def env_transport_config() -> dict:
    """Transport settings from the environment (empty when unconfigured)."""
    kind = os.getenv("SLIDEIN_TRANSPORT", "").strip().lower()
    if not kind:
        return {}
    is_kumo = kind == "kumo"
    cfg: dict = {"transport": kind}
    host = os.getenv("SLIDEIN_SMTP_HOST", "").strip() or (
        os.getenv("KUMO_HOST", "").strip() or ("127.0.0.1" if is_kumo else "")
    )
    port = os.getenv("SLIDEIN_SMTP_PORT", "").strip() or (
        os.getenv("KUMO_SMTP_PORT", "").strip() or ("2587" if is_kumo else "587")
    )
    username = os.getenv("SLIDEIN_SMTP_USER", "").strip() or (
        os.getenv("KUMO_AUTH_USER", "").strip() or ("outbound" if is_kumo else "")
    )
    password = os.getenv("SLIDEIN_SMTP_PASS", "").strip() or os.getenv(
        "KUMO_AUTH_PASS", ""
    ).strip()
    if host:
        cfg["smtp_host"] = host
    if port:
        cfg["smtp_port"] = int(port)
    if username:
        cfg["smtp_username"] = username
    if password:
        cfg["smtp_password"] = password
    cfg["smtp_use_tls"] = os.getenv("SLIDEIN_SMTP_TLS", "1").lower() not in (
        "0", "false", "no", "off",
    )
    return cfg


TRANSPORTS = {"dry_run": DryRunTransport, "smtp": SMTPTransport, "kumo": SMTPTransport}


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
