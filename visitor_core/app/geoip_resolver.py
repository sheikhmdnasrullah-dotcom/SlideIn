"""Module A — MaxMind GeoIP2 embedded resolver.

Local `geoip2.database.Reader` against a GeoLite2-City/Company MMDB — zero
external API calls, sub-millisecond lookups. Degrades to None when the MMDB
file is absent or the IP is private/unmapped, letting the pipeline fall
through to the Retention.com layer.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from .config import settings


@dataclass
class GeoResult:
    ip: str
    company_domain: str | None = None
    company_name: str | None = None
    city: str | None = None
    country: str | None = None
    is_corporate: bool = False
    is_anonymous_network: bool = False     # VPN/hosting provider or unmapped
    raw: dict = field(default_factory=dict)


# Hosting/VPN AS-name fragments — treated as anonymous networks even when the
# DB has no explicit traits flag.
_ANONYMOUS_FRAGS = (
    "amazon", "google llc", "microsoft corporation", "cloudflare", "akamai",
    "ovh", "digitalocean", "hetzner", "m247", "t-mobile", "at&t", "comcast",
    "verizon", "vodafone", "orange", "telefonica", "deutsche telekom",
    "spectrum", "charter", "jio", "reliance", "bt-", "british telecom",
)


class GeoIPResolver:
    def __init__(self, mmdb_path: str | None = None):
        self._path = mmdb_path or settings.mmdb_path
        self._reader = None
        self._open()

    def _open(self) -> None:
        try:
            import geoip2.database

            self._reader = geoip2.database.Reader(self._path)
        except Exception:
            # Missing package, missing/corrupt MMDB — resolver degrades to
            # "anonymous network" and the pipeline falls through to fallback.
            self._reader = None

    @property
    def available(self) -> bool:
        return self._reader is not None

    def resolve(self, ip: str) -> GeoResult:
        result = GeoResult(ip=ip, is_anonymous_network=True)
        try:
            addr = ipaddress.ip_address(ip)
            if addr.is_private or addr.is_loopback or addr.is_multicast:
                return result
        except ValueError:
            return result
        if not self._reader:
            return result

        try:
            city = self._reader.city(ip)
        except Exception:
            return result

        result.city = city.city.name
        result.country = city.country.iso_code
        org = (city.traits.autonomous_system_organization or "").lower()
        result.raw = {
            "asn": city.traits.autonomous_system_number,
            "org": city.traits.autonomous_system_organization,
        }
        if org and not any(f in org for f in _ANONYMOUS_FRAGS):
            result.is_corporate = True
            result.is_anonymous_network = False
            result.company_name = city.traits.autonomous_system_organization
            # Best-effort corporate domain footprint from the AS org name.
            tokens = [t for t in org.replace(",", " ").split()
                      if "." not in t and len(t) > 2 and t.isalpha()]
            if tokens:
                result.company_domain = tokens[0] + ".com"
        return result


def is_anonymous_ip(ip: str) -> bool:
    """Cheap pre-check so we never even open the reader for junk IPs."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_multicast or addr.is_reserved
    except ValueError:
        return True
