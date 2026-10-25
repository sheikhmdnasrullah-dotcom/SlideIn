"""Visitor identity resolution pipeline — async, timeout-bounded, dead-drop safe.

Chain (short-circuits on first success):
  COOKIE_STITCH   session token / ?he= marker merges a known visitor
  LOCAL_GEOIP     embedded MaxMind MMDB isolates the corporate network
  RETENTION_API   proxy-routed commercial fallback (residential/unstitched only)
  ANONYMOUS       terminal graceful state; traceback surfaced, never hangs

Every step broadcasts the CRM wire envelope and appends to the event ledger;
the final record is upserted into the DB ledger regardless of outcome.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import traceback

from .config import settings
from .db import new_visitor_id, upsert_visitor
from .events import CRMPublisher
from .fallback import RetentionFallback
from .geoip_resolver import GeoIPResolver
from .ledger import EventLedger
from .schemas import (
    CRMEnvelope,
    CRMDelta,
    CRMStatus,
    ResolutionTier,
    TrackPayload,
    VisitorRecord,
)


def _fingerprint_hash(fp: dict) -> str:
    stable = json.dumps(fp, sort_keys=True, default=str)
    return hashlib.sha256(stable.encode()).hexdigest()[:32]


class VisitorPipeline:
    def __init__(self, geoip: GeoIPResolver | None = None,
                 fallback: RetentionFallback | None = None):
        self._geoip = geoip or GeoIPResolver()
        self._fallback = fallback or RetentionFallback()
        self._ledger = EventLedger()

    async def resolve(self, payload: TrackPayload, *, task_id: str,
                      visitor_id: str | None = None,
                      site_domain: str = "") -> VisitorRecord:
        visitor_id = visitor_id or new_visitor_id()
        fp_hash = _fingerprint_hash(payload.context.fingerprint)
        page_url = (payload.context.page or {}).get("url", "")
        record = VisitorRecord(
            visitor_id=visitor_id,
            site_key=payload.site_key,
            site_domain=site_domain,
            ip=payload.context.ip,
            user_agent=payload.context.user_agent,
            fingerprint_hash=fp_hash,
            session_id=payload.session_id,
        )

        async def _emit(tier: ResolutionTier, status: CRMStatus,
                        delta: CRMDelta | None = None,
                        error: str | None = None) -> None:
            CRMPublisher.publish(CRMEnvelope(
                task_id=task_id, site_domain=site_domain,
                resolution_tier=tier, status=status,
                live_crm_delta=delta or CRMDelta(), error_logs=error,
                visitor_id=visitor_id,
            ))

        try:
            await asyncio.wait_for(
                self._run(payload, record, _emit, page_url),
                timeout=settings.pipeline_timeout,
            )
        except asyncio.TimeoutError:
            record.resolution_tier = ResolutionTier.ANONYMOUS.value
            record.status = CRMStatus.COMPLETED.value
            record.error_logs = f"pipeline timeout after {settings.pipeline_timeout}s"
            await _emit(ResolutionTier.ANONYMOUS, CRMStatus.COMPLETED,
                        error=record.error_logs)
        except Exception:
            record.resolution_tier = ResolutionTier.ANONYMOUS.value
            record.status = CRMStatus.COMPLETED.value
            record.error_logs = traceback.format_exc(limit=8)
            await _emit(ResolutionTier.ANONYMOUS, CRMStatus.COMPLETED,
                        error=record.error_logs)

        await upsert_visitor(record)
        return record

    # ------------------------------------------------------------------ #
    async def _run(self, payload, record, _emit, page_url) -> None:
        self._ledger.log(payload.site_key, "Visitor Intercepted",
                         description=f"hit from {payload.context.ip}",
                         tags={"fingerprint": record.fingerprint_hash})
        await _emit(ResolutionTier.ANONYMOUS, CRMStatus.TRACKING)

        # ---- 1. first-party session stitching (?he= / __sl_vid cookie)
        if payload.session_id or payload.query_marker_token:
            record.resolution_tier = ResolutionTier.COOKIE_STITCH.value
            stitched = CRMDelta(email=None, company_domain=None,
                                prospect_name=None, linkedin_url=None)
            await _emit(ResolutionTier.COOKIE_STITCH, CRMStatus.STITCHING,
                        delta=stitched)
            self._ledger.log(payload.site_key, "Session Stitched",
                             tags={"session": payload.session_id
                                   or payload.query_marker_token})
            record.status = CRMStatus.COMPLETED.value
            await _emit(ResolutionTier.COOKIE_STITCH, CRMStatus.COMPLETED,
                        delta=stitched)
            return

        # ---- 2. embedded MaxMind GeoIP corporate isolation
        geo = self._geoip.resolve(payload.context.ip or "")
        record.geo = {k: v for k, v in geo.raw.items() if v}
        if geo.city:
            record.geo["city"] = geo.city
        if geo.country:
            record.geo["country"] = geo.country
        if geo.is_corporate and geo.company_domain:
            record.company_domain = geo.company_domain
            record.resolution_tier = ResolutionTier.LOCAL_GEOIP.value
            record.status = CRMStatus.COMPLETED.value
            self._ledger.log(payload.site_key, "Corporate Domain Isolated",
                             description=geo.company_domain,
                             tags={"as": geo.company_name})
            await _emit(ResolutionTier.LOCAL_GEOIP, CRMStatus.COMPLETED,
                        delta=CRMDelta(company_domain=geo.company_domain))
            return

        # ---- 3. Retention.com fallback (only for unstitched + anonymous nets)
        await _emit(ResolutionTier.ANONYMOUS, CRMStatus.FALLBACK_TRIGGERED)
        self._ledger.log(payload.site_key, "Fallback Triggered",
                         description="unstitched residential hit — "
                                     "dispatching Retention.com wrapper",
                         tags={"ip": payload.context.ip})
        identity = await asyncio.wait_for(
            self._fallback.resolve(
                ip=payload.context.ip or "",
                fingerprint_hash=record.fingerprint_hash or "",
                page_url=page_url,
                site_domain=record.site_domain or payload.site_key,
            ),
            timeout=settings.fallback_timeout + 5,
        )
        if identity:
            record.resolution_tier = ResolutionTier.RETENTION_API.value
            record.status = CRMStatus.COMPLETED.value
            record.email = identity.get("email")
            record.first_name = identity.get("first_name")
            record.last_name = identity.get("last_name")
            record.linkedin_url = identity.get("linkedin_url")
            record.company_domain = identity.get("company_domain")
            self._ledger.log(payload.site_key, "Identity Resolved",
                             description=identity.get("email"),
                             tags={"tier": "RETENTION_API"})
            await _emit(ResolutionTier.RETENTION_API, CRMStatus.COMPLETED,
                        delta=CRMDelta(
                            email=record.email,
                            company_domain=record.company_domain,
                            prospect_name=" ".join(filter(None, [
                                record.first_name, record.last_name])) or None,
                            linkedin_url=record.linkedin_url,
                        ))
            return

        # ---- 4. graceful anonymous terminal state
        record.resolution_tier = ResolutionTier.ANONYMOUS.value
        record.status = CRMStatus.COMPLETED.value
        record.error_logs = ("no identity signal: unstitched session, "
                             "anonymous network, fallback empty/unavailable")
        await _emit(ResolutionTier.ANONYMOUS, CRMStatus.COMPLETED,
                    error=record.error_logs)
