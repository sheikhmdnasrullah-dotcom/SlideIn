"""Settings — env-driven, no extra deps."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _csv(name: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.getenv(name, "").split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    # storage / broker
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
    db_url: str = os.getenv("VISITOR_DB_URL", "sqlite+aiosqlite:///./visitor_core.db")

    # MaxMind embedded database (local file, zero external latency)
    mmdb_path: str = os.getenv("GEOIP_MMDB_PATH", "./GeoLite2-City.mmdb")

    # Retention.com commercial fallback layer
    retention_api_url: str | None = os.getenv("RETENTION_API_URL") or None
    retention_api_key: str | None = os.getenv("RETENTION_API_KEY") or None

    # optional real LogSnag mirror (internal ledger always runs)
    logsnag_token: str | None = os.getenv("LOGSNAG_TOKEN") or None
    logsnag_project: str = os.getenv("LOGSNAG_PROJECT", "slidein-visitor-core")

    # fallback egress: residential SOCKS5 pool (one identity per request)
    proxy_list: tuple = field(default_factory=lambda: _csv("VISITOR_PROXY_LIST"))
    fallback_timeout: float = float(os.getenv("VISITOR_FALLBACK_TIMEOUT", "15"))
    pipeline_timeout: float = float(os.getenv("VISITOR_PIPELINE_TIMEOUT", "120"))

    # first-party cookie used by the embed for session stitching
    visitor_cookie: str = os.getenv("VISITOR_COOKIE", "__sl_vid")
    query_marker: str = os.getenv("VISITOR_QUERY_MARKER", "he")  # ?he=<token>


settings = Settings()
