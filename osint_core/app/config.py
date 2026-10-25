"""Central settings. Everything overridable via environment variables.

No pydantic-settings dependency: plain frozen dataclass populated at import time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Identifies us to API endpoints that require it (SEC EDGAR, HIBP).
    "SlideinVenture-osint-core/0.1 (B2B enrichment; contact: ops@slidein.example)",
]


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    # --- infrastructure -----------------------------------------------------
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    celery_broker_url: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    celery_result_backend: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

    # --- proxy pipeline -------------------------------------------------------
    # Comma-separated socks5://user:pass@host:port entries, or a file with one per line.
    proxy_list: tuple = field(default_factory=lambda: tuple(_csv("OSINT_PROXY_LIST")))
    proxy_file: str | None = os.getenv("OSINT_PROXY_FILE") or None
    proxy_enabled: bool = os.getenv("OSINT_PROXY_ENABLED", "1") == "1"
    # Per-proxy exponential cooldown base (seconds) after a transport failure.
    proxy_cooldown_base: float = float(os.getenv("OSINT_PROXY_COOLDOWN_BASE", "30"))

    # --- HTTP probe -----------------------------------------------------------
    request_timeout: float = float(os.getenv("OSINT_REQUEST_TIMEOUT", "12"))
    connect_timeout: float = float(os.getenv("OSINT_CONNECT_TIMEOUT", "6"))
    max_retries: int = int(os.getenv("OSINT_MAX_RETRIES", "3"))
    backoff_base: float = float(os.getenv("OSINT_BACKOFF_BASE", "1.5"))
    user_agents: tuple = field(default_factory=lambda: tuple(DEFAULT_USER_AGENTS))

    # --- concurrency ----------------------------------------------------------
    platform_concurrency: int = int(os.getenv("OSINT_PLATFORM_CONCURRENCY", "32"))
    subdomain_concurrency: int = int(os.getenv("OSINT_SUBDOMAIN_CONCURRENCY", "48"))
    dns_timeout: float = float(os.getenv("OSINT_DNS_TIMEOUT", "5"))
    dns_lifetime: float = float(os.getenv("OSINT_DNS_LIFETIME", "10"))

    # --- external adapters ----------------------------------------------------
    hibp_api_key: str | None = os.getenv("HIBP_API_KEY") or None
    # Optional subfinder binary for one extra passive source; module degrades gracefully.
    subfinder_bin: str | None = os.getenv("SUBFINDER_BIN", "subfinder") or None
    # Number of platforms checked per lead by default (registry can hold thousands).
    default_site_count: int = int(os.getenv("OSINT_DEFAULT_SITE_COUNT", "60"))

    # --- OpenOSINT CLI bridge (app/modules/openosint_tool.py) -----------------
    # Binary path; default resolves via PATH. Lookups degrade to error rows
    # when missing — never fails the pipeline.
    openosint_bin: str = os.getenv("OPENOSINT_BIN", "openosint") or "openosint"
    # 1 permits the noisy email/username enumerators without per-call opt-in.
    openosint_allow_active: bool = os.getenv("OPENOSINT_ALLOW_ACTIVE", "0") == "1"

    # --- JA3 / curl_cffi --------------------------------------------------------
    curl_impersonate: str = os.getenv("CURL_IMPERSONATE", "chrome124")

    # --- workers --------------------------------------------------------------
    lead_soft_time_limit: int = int(os.getenv("OSINT_LEAD_SOFT_TIME_LIMIT", "300"))
    lead_hard_time_limit: int = int(os.getenv("OSINT_LEAD_HARD_TIME_LIMIT", "360"))


def _load_proxy_file(path: str) -> tuple[str, ...]:
    with open(path, "r", encoding="utf-8") as fh:
        return tuple(
            line.strip()
            for line in fh
            if line.strip() and not line.startswith("#")
        )


def load_settings() -> Settings:
    s = Settings()
    if s.proxy_file:
        object.__setattr__(s, "proxy_list", _load_proxy_file(s.proxy_file))
    return s


settings = load_settings()
