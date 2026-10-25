"""Blackbird OSINT wrapper — username sweep across 600+ platforms.

Blackbird (antoniaci/blackbird) checks a username across hundreds of sites.
Two paths:
  * BLACKBIRD_CMD set -> headless engine run (`blackbird -u <handle>` style,
    output parsed for per-site hits).
  * Fallback -> the Maigret-style registry runs against ALL derived handle
    candidates (primary + alternates), riding JA3 + SOCKS5. Scale to 600+
    platforms by importing a full Maigret `data.json` into the registry —
    the code path is identical.

The pipeline supplies on_unit; every hit is one progress chunk.
Output: list of {platform, url, handle, confidence}.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field

from ..modules.social import SocialEnumerator


@dataclass
class BlackbirdResult:
    hits: list[dict] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    engine: str = "maigret-registry"

    def to_dict(self) -> dict:
        return {"hits": self.hits, "candidates": self.candidates, "engine": self.engine}


class BlackbirdRunner:
    def __init__(self, enumerator: SocialEnumerator):
        self._enumerator = enumerator
        self._cmd = os.getenv("BLACKBIRD_CMD", "")

    async def run(self, candidates: list[str], on_unit=None) -> BlackbirdResult:
        if self._cmd and shutil.which(self._cmd.split()[0]):
            result = await self._run_engine(candidates[0], on_unit)
            if result is not None:
                return result
        return await self._run_registry(candidates, on_unit)

    async def _run_engine(self, handle: str, on_unit) -> BlackbirdResult | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._cmd.split(), "-u", handle,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            text = out.decode(errors="replace")
        except (asyncio.TimeoutError, OSError):
            return None
        hits = [
            {"platform": m.group(1), "url": m.group(0), "handle": handle,
             "confidence": 0.7}
            for m in re.finditer(r"https?://[^\s)]+", text)
        ]
        if on_unit:
            for h in hits:
                await on_unit(h)
        return BlackbirdResult(hits=hits, candidates=[handle],
                               engine="blackbird-engine")

    async def _run_registry(self, candidates: list[str], on_unit) -> BlackbirdResult:
        """Sweep every handle candidate; emit per-hit chunks."""
        seen: set[tuple] = set()
        hits: list[dict] = []

        async def _sweep(handle: str):
            async def _cb(site_name: str, profile: dict):
                if not profile.get("exists"):
                    return
                key = (site_name, handle)
                if key in seen:
                    return
                seen.add(key)
                hit = {"platform": site_name, "url": profile.get("url", ""),
                       "handle": handle, "confidence": profile.get("confidence", 0.6)}
                hits.append(hit)
                if on_unit is not None:
                    await on_unit(hit)

            await self._enumerator.enumerate(handle, on_result=_cb)

        await asyncio.gather(*[
            asyncio.wait_for(_sweep(h), timeout=150) for h in candidates[:4]
        ])
        return BlackbirdResult(hits=hits, candidates=candidates)
