"""Bomkesh-OSINT wrapper — structural registrations & public footprint data.

Bomkesh aggregates per-target footprint reports. Two paths:
  * BOMKESH_CMD set -> headless engine run for the email/handle, JSON parsed.
  * Fallback -> structural footprint assembled from the channels we already
    own: Holehe-style email registrations, gravatar-linked accounts, social
    profile hits, and breach sources — normalized into footprint slots.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field


@dataclass
class BomkeshResult:
    email_registrations: list[dict] = field(default_factory=list)
    handle_footprint: list[dict] = field(default_factory=list)
    exposure_sources: list[str] = field(default_factory=list)
    summary: str = ""
    engine: str = "builtin-aggregator"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class BomkeshRunner:
    def __init__(self):
        self._cmd = os.getenv("BOMKESH_CMD", "")

    async def run(self, *, email: str, handle: str, holehe_hits: list[dict],
                  footprint_profiles: list[dict], breach_names: list[str],
                  on_unit=None) -> BomkeshResult:
        if self._cmd and shutil.which(self._cmd.split()[0]):
            result = await self._run_engine(email, handle)
            if result is not None:
                if on_unit:
                    await on_unit({"engine": "bomkesh", "slots": 3})
                return result
        return self._run_builtin(email, handle, holehe_hits, footprint_profiles,
                                 breach_names, on_unit)

    async def _run_engine(self, email: str, handle: str) -> BomkeshResult | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._cmd.split(), "--email", email, "--handle", handle, "--json",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=150)
            data = json.loads(out.decode())
        except (asyncio.TimeoutError, OSError, ValueError):
            return None
        return BomkeshResult(
            email_registrations=data.get("email_registrations", []),
            handle_footprint=data.get("handle_footprint", []),
            exposure_sources=data.get("exposure_sources", []),
            summary=data.get("summary", ""),
            engine="bomkesh-engine",
        )

    def _run_builtin(self, email, handle, holehe_hits, footprint_profiles,
                     breach_names, on_unit) -> BomkeshResult:
        regs = [h for h in holehe_hits if h.get("registered")]
        handles = [
            {"platform": p.get("platform"), "url": p.get("url")}
            for p in footprint_profiles if p.get("exists")
        ]
        total = len(regs) + len(handles) + len(breach_names)
        if on_unit:
            for slot in ({"registrations": len(regs)},
                         {"handle_footprint": len(handles)},
                         {"exposure_sources": len(breach_names)}):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(on_unit(slot))
                except RuntimeError:
                    pass
        return BomkeshResult(
            email_registrations=regs,
            handle_footprint=handles,
            exposure_sources=breach_names,
            summary=f"{total} public footprint slots across registrations, "
                    f"handle presence, and breach corpora",
        )
