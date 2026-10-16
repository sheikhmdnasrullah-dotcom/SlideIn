"""Adapter interfaces and dry-run implementations.

Real vendor adapters (SMTP, Gmail, CRM, calendar, enrichment) implement
these same interfaces per deployment. Dry-run variants record intent
without touching any external system.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field


class AdapterStatus(str, enum.Enum):
    CONNECTED = "connected"
    EXPIRED = "expired"
    FAILING = "failing"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ConnectionInfo:
    adapter: str
    status: AdapterStatus
    detail: str = ""
    secret_ref: str = ""  # name of the secret, never its value

    def summary(self) -> dict:
        return {
            "adapter": self.adapter,
            "status": self.status.value,
            "detail": self.detail,
            "secret_ref": self.secret_ref,
        }


class MailTransport(abc.ABC):
    """Send one message. Implementations must be tenant-scoped by the caller."""

    name = "mail"

    @abc.abstractmethod
    def dispatch(
        self, *, sender: str, recipient: str, subject: str, body: str,
        headers: dict | None = None,
    ) -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def health(self) -> ConnectionInfo:
        raise NotImplementedError


class CrmAdapter(abc.ABC):
    name = "crm"

    @abc.abstractmethod
    def upsert_contact(self, *, external_id: str, fields: dict) -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def log_activity(self, *, external_id: str, note: str) -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def health(self) -> ConnectionInfo:
        raise NotImplementedError


class CalendarAdapter(abc.ABC):
    name = "calendar"

    @abc.abstractmethod
    def booking_url(self) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def create_event(
        self, *, title: str, start_iso: str, end_iso: str, attendees: list[str],
    ) -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def health(self) -> ConnectionInfo:
        raise NotImplementedError


class EnrichmentAdapter(abc.ABC):
    name = "enrichment"

    @abc.abstractmethod
    def enrich(self, *, domain: str = "", company: str = "") -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def health(self) -> ConnectionInfo:
        raise NotImplementedError


class MessagingAdapter(abc.ABC):
    name = "messaging"

    @abc.abstractmethod
    def send_message(self, *, channel: str, to: str, text: str) -> dict:
        raise NotImplementedError

    @abc.abstractmethod
    def health(self) -> ConnectionInfo:
        raise NotImplementedError


@dataclass
class DryRunMailTransport(MailTransport):
    sent: list[dict] = field(default_factory=list)

    def dispatch(
        self, *, sender: str, recipient: str, subject: str, body: str,
        headers: dict | None = None,
    ) -> dict:
        record = {
            "ok": True, "provider": "slidein.dry_run",
            "sender": sender, "recipient": recipient, "subject": subject,
        }
        self.sent.append(record)
        return dict(record)

    def health(self) -> ConnectionInfo:
        return ConnectionInfo(
            adapter=self.name, status=AdapterStatus.DISCONNECTED,
            detail="dry-run: nothing is sent",
        )


@dataclass
class DryRunCrmAdapter(CrmAdapter):
    contacts: dict = field(default_factory=dict)

    def upsert_contact(self, *, external_id: str, fields: dict) -> dict:
        self.contacts[external_id] = dict(fields)
        return {"ok": True, "external_id": external_id, "dry_run": True}

    def log_activity(self, *, external_id: str, note: str) -> dict:
        return {"ok": True, "external_id": external_id, "dry_run": True}

    def health(self) -> ConnectionInfo:
        return ConnectionInfo(adapter=self.name, status=AdapterStatus.UNKNOWN,
                              detail="no CRM connected")


@dataclass
class DryRunCalendarAdapter(CalendarAdapter):
    configured_url: str = ""

    def booking_url(self) -> str:
        return self.configured_url

    def create_event(
        self, *, title: str, start_iso: str, end_iso: str, attendees: list[str],
    ) -> dict:
        if not self.configured_url:
            return {"ok": False, "error": "no booking provider configured"}
        return {"ok": True, "dry_run": True, "url": self.configured_url}

    def health(self) -> ConnectionInfo:
        if self.configured_url:
            return ConnectionInfo(adapter=self.name,
                                  status=AdapterStatus.CONNECTED,
                                  detail="booking link configured")
        return ConnectionInfo(adapter=self.name,
                              status=AdapterStatus.DISCONNECTED,
                              detail="no booking provider selected")


@dataclass
class DryRunEnrichmentAdapter(EnrichmentAdapter):
    def enrich(self, *, domain: str = "", company: str = "") -> dict:
        return {"ok": True, "dry_run": True, "domain": domain,
                "company": company, "signals": []}

    def health(self) -> ConnectionInfo:
        return ConnectionInfo(adapter=self.name, status=AdapterStatus.UNKNOWN,
                              detail="no enrichment provider connected")


@dataclass
class DryRunMessagingAdapter(MessagingAdapter):
    def send_message(self, *, channel: str, to: str, text: str) -> dict:
        return {"ok": True, "dry_run": True, "channel": channel, "to": to}

    def health(self) -> ConnectionInfo:
        return ConnectionInfo(adapter=self.name, status=AdapterStatus.UNKNOWN,
                              detail="no messaging channel connected")
