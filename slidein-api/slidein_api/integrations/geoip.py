"""Local MaxMind GeoIP2 network-context reader.

GeoIP/ASN data describes a network, not a person or confirmed employer. This
adapter never returns an inferred company domain and never performs network IO.
A licensed MMDB file must be supplied separately; it is not committed to git.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Any


class GeoIP2Resolver:
    name = "maxmind_geoip2"

    def __init__(self, mmdb_path: str | None = None, reader: Any | None = None) -> None:
        self.mmdb_path = mmdb_path or os.getenv("GEOIP_MMDB_PATH", "").strip()
        self._reader = reader
        self._owns_reader = reader is None

    def _open(self):
        if self._reader is not None:
            return self._reader
        if not self.mmdb_path or not Path(self.mmdb_path).is_file():
            return None
        import geoip2.database

        self._reader = geoip2.database.Reader(self.mmdb_path)
        return self._reader

    @property
    def available(self) -> bool:
        return self._open() is not None

    def resolve(self, ip: str) -> dict:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return {"status": "invalid_ip", "identity_resolved": False}
        if not address.is_global:
            return {"status": "non_public_ip", "identity_resolved": False}
        reader = self._open()
        if reader is None:
            return {
                "status": "database_unavailable",
                "missing": [] if self.mmdb_path else ["GEOIP_MMDB_PATH"],
                "identity_resolved": False,
            }
        try:
            result = reader.city(str(address))
        except Exception as exc:
            return {
                "status": "not_found",
                "error_type": type(exc).__name__,
                "identity_resolved": False,
            }
        return {
            "status": "network_context",
            "country": result.country.iso_code,
            "city": result.city.name,
            "asn": result.traits.autonomous_system_number,
            "network_name": result.traits.autonomous_system_organization,
            "company_domain": None,
            "identity_resolved": False,
            "source": self.name,
        }

    def close(self) -> None:
        if self._owns_reader and self._reader is not None:
            self._reader.close()
        self._reader = None


__all__ = ["GeoIP2Resolver"]
