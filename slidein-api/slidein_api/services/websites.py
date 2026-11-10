"""Website connections and consented first-party lead capture."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from sqlalchemy import select, update

from ..errors import SlideinError, ValidationError
from ..ids import new_id
from ..models import EvidenceItem, VerificationStatus, WebsiteConnection, WebsiteEvent
from .discovery import DiscoveryService, normalize_domain

_ALLOWED_EVENTS = {"page_view", "form_submit", "identify"}
_PROVIDERS = {"native", "snowplow", "rudderstack"}


def website_domain(value: str) -> str:
    raw = value.strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValidationError(
            "Website connection requires a public HTTPS domain",
            code="website_invalid",
            recovery_action="fix_website_connection",
        )
    domain = normalize_domain(parsed.hostname or "")
    if not domain or "." not in domain or domain.endswith((".local", ".internal", ".localhost")):
        raise ValidationError(
            "Website connection requires a public HTTPS domain",
            code="website_invalid",
            recovery_action="fix_website_connection",
        )
    return domain


def _validate_page_url(value: str, domain: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == domain or host.endswith(f".{domain}")):
        raise ValidationError(
            "Event page URL does not belong to the connected website",
            code="website_origin_mismatch",
            recovery_action="fix_website_connection",
        )
    return value[:1024]


class WebsiteService:
    def __init__(self, session) -> None:
        self.session = session

    async def connect(self, tenant_id: str, *, domain: str, provider: str = "native") -> tuple[WebsiteConnection, bool]:
        normalized = website_domain(domain)
        if provider not in _PROVIDERS:
            raise ValidationError(
                "Unsupported website event provider",
                code="website_invalid",
                details={"allowed": sorted(_PROVIDERS)},
                recovery_action="fix_website_connection",
            )
        existing = (
            await self.session.execute(
                select(WebsiteConnection).where(
                    WebsiteConnection.tenant_id == tenant_id,
                    WebsiteConnection.domain == normalized,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        row = WebsiteConnection(
            id=new_id("website"), tenant_id=tenant_id, domain=normalized,
            site_key=f"site_{secrets.token_urlsafe(24)}", provider=provider,
        )
        self.session.add(row)
        await self.session.flush()
        return row, True

    async def list(self, tenant_id: str) -> list[WebsiteConnection]:
        return list((
            await self.session.execute(
                select(WebsiteConnection)
                .where(WebsiteConnection.tenant_id == tenant_id)
                .order_by(WebsiteConnection.created_at.desc())
            )
        ).scalars().all())

    async def capture(self, site_key: str, payload: dict) -> dict:
        website = (
            await self.session.execute(
                select(WebsiteConnection).where(WebsiteConnection.site_key == site_key)
            )
        ).scalar_one_or_none()
        if website is None:
            raise SlideinError("Website connection not found", code="not_found", recovery_action="fix_website_connection")
        if payload.get("consent") is not True:
            raise ValidationError(
                "Explicit analytics and lead-capture consent is required",
                code="consent_required",
                recovery_action="request_consent",
            )
        event_type = str(payload.get("event_type") or "")
        if event_type not in _ALLOWED_EVENTS:
            raise ValidationError(
                "Unsupported website event",
                code="event_invalid",
                details={"allowed": sorted(_ALLOWED_EVENTS)},
                recovery_action="fix_event_payload",
            )
        page_url = _validate_page_url(str(payload.get("page_url") or ""), website.domain)
        event_id = str(payload.get("event_id") or "").strip()
        session_id = str(payload.get("session_id") or "").strip()
        if not event_id or not session_id or len(event_id) > 128 or len(session_id) > 128:
            raise ValidationError(
                "event_id and session_id are required within 128 characters",
                code="event_invalid",
                recovery_action="fix_event_payload",
            )
        duplicate = (
            await self.session.execute(
                select(WebsiteEvent).where(
                    WebsiteEvent.website_id == website.id,
                    WebsiteEvent.external_event_id == event_id,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            return {"accepted": True, "duplicate": True, "lead_created": False, "prospect_id": duplicate.prospect_id}

        email = str(payload.get("email") or "").strip()
        if event_type in {"form_submit", "identify"} and not email:
            raise ValidationError(
                "An explicitly submitted email is required to identify a lead",
                code="email_required",
                recovery_action="submit_email",
            )
        prospect = None
        created = False
        if email:
            prospect, created = await DiscoveryService(self.session).create_website_lead(
                website.tenant_id,
                email=email,
                first_name=str(payload.get("first_name") or ""),
                last_name=str(payload.get("last_name") or ""),
                company_name=str(payload.get("company_name") or ""),
                source_ref=website.id,
                page_url=page_url,
            )
            await self.session.execute(
                update(WebsiteEvent)
                .where(
                    WebsiteEvent.tenant_id == website.tenant_id,
                    WebsiteEvent.website_id == website.id,
                    WebsiteEvent.session_id == session_id,
                    WebsiteEvent.prospect_id.is_(None),
                )
                .values(prospect_id=prospect.id)
            )
            if created:
                self.session.add(EvidenceItem(
                    id=new_id("evidence"), tenant_id=website.tenant_id, prospect_id=prospect.id,
                    evidence_type="consented_website_identification",
                    claim_text="Visitor explicitly submitted their email through the connected website.",
                    source_url=page_url, source_name=website.domain, confidence=1.0,
                    verification_status=VerificationStatus.VERIFIED.value,
                    collector="website_form", retrieved_by="website_consent",
                ))
        event = WebsiteEvent(
            id=new_id("website_event"), tenant_id=website.tenant_id, website_id=website.id,
            external_event_id=event_id, session_id=session_id, event_type=event_type,
            page_url=page_url, prospect_id=prospect.id if prospect else None,
        )
        self.session.add(event)
        website.status = "active"
        await self.session.flush()
        return {
            "accepted": True, "duplicate": False, "lead_created": created,
            "prospect_id": prospect.id if prospect else None,
            "identity_source": "explicit_form" if prospect else None,
        }


__all__ = ["WebsiteService", "website_domain"]
