"""Holehe wrapper — email-keyed account existence engine.

Holehe's real engine enumerates registration status across ~120 platforms via
password-reset endpoints. We do not reimplement that signalling behaviour
here; instead this wrapper runs the actual `holehe` package headlessly when it
is installed (HOLEHE_CMD or on PATH) and otherwise degrades to the
email-keyed public probes we already own (gravatar-linked accounts).

Output contract: list of {site, registered, confidence}.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil

from ..schemas import SocialFootprint

DEFAULT_SITES_TOTAL = 120


class HoleheRunner:
    def __init__(self):
        self._cmd = os.getenv("HOLEHE_CMD", "holehe")

    @staticmethod
    def total_units() -> int:
        return DEFAULT_SITES_TOTAL

    async def run(self, email: str, footprint: SocialFootprint, on_unit=None) -> list[dict]:
        if shutil.which(self._cmd.split()[0]):
            return await self._run_engine(email, on_unit)
        return await self._from_gravatar(email, footprint, on_unit)

    async def _run_engine(self, email: str, on_unit) -> list[dict]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._cmd.split(), email, "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=150)
        except (asyncio.TimeoutError, OSError):
            return []
        try:
            rows = json.loads(out.decode())
        except ValueError:
            return []
        hits = [
            {"site": r.get("name") or r.get("site"), "registered": bool(r.get("exists")),
             "confidence": 0.8}
            for r in rows
        ]
        if on_unit:
            for h in hits:
                await on_unit(h)
        return hits

    async def _from_gravatar(self, email: str, footprint: SocialFootprint, on_unit) -> list[dict]:
        """Fallback: email-keyed accounts surfaced by the gravatar profile."""
        hits = [
            {"site": a.get("platform"), "registered": True, "confidence": 0.9}
            for a in ((footprint.gravatar or {}).get("linked_accounts") or [])
            if a.get("platform")
        ]
        if on_unit:
            for h in hits:
                await on_unit(h)
        return hits
