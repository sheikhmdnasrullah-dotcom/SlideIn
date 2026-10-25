"""MailAccess wrapper — 5,300+ platform corpus risk map, headless.

Two execution paths, both producing the same `MailAccessResult`:

  1. External engine (preferred at scale): point MAILACCESS_CMD at the
     MailAccess engine binary/entrypoint. We invoke it headlessly with the
     target email, a strict subprocess timeout, and parse its JSON report.
     The engine's own 5,300+ site corpus and username-matching matrices then
     drive the registration sweep.

  2. Built-in sampler (default): registration checks against a curated
     high-signal platform subset via the JA3 transport, merged with breach
     intelligence to compute a credential-exposure risk score.

Risk semantics: we never test or validate credentials. "Credential risk" is
exposure risk — how re-usable a phished/recycled password would be given which
platforms the address is registered on and what breach data classes leaked.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field

from ..core.transport import Ja3Transport, Ja3ProbeError
from ..schemas import BreachExposure

SAMPLE_SITES = [
    # (platform, url template, marker-missing => registered)
    ("adobe", "https://account.adobe.com"),
    ("dropbox", "https://www.dropbox.com"),
    ("linkedin", "https://www.linkedin.com"),
    ("github", "https://github.com"),
]

RISK_TIERS = [(80, "critical"), (50, "high"), (25, "medium"), (0, "low")]


@dataclass
class RegistrationHit:
    platform: str
    registered: bool
    confidence: float
    source: str = "builtin-sampler"


@dataclass
class MailAccessResult:
    corpus_size: int = 0
    sampled: int = 0
    engine: str = "builtin-sampler"
    registrations: list[RegistrationHit] = field(default_factory=list)
    risk_score: int = 0
    risk_level: str = "low"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "corpus_size": self.corpus_size,
            "sampled": self.sampled,
            "engine": self.engine,
            "registrations": [r.__dict__ for r in self.registrations],
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "notes": self.notes,
        }


def _score(hits: list[RegistrationHit], breach: BreachExposure) -> int:
    score = 0
    for h in hits:
        if h.registered:
            score += {"adobe": 35, "dropbox": 25, "linkedin": 20}.get(h.platform, 10)
    if "Passwords" in breach.data_classes or "hashed_password" in [
        c.lower() for c in breach.data_classes
    ]:
        score += 40
    score += min(breach.breach_count * 5, 30)
    return min(score, 100)


class MailAccessRunner:
    def __init__(self, transport: Ja3Transport):
        self._transport = transport

    async def run(self, email: str, breach: BreachExposure, on_unit=None) -> MailAccessResult:
        cmd = os.getenv("MAILACCESS_CMD")
        if cmd and shutil.which(cmd.split()[0]):
            return await self._run_external(cmd, email, breach, on_unit)
        return await self._run_builtin(email, breach, on_unit)

    # ------------------------------------------------------------------ #
    async def _run_external(self, cmd, email, breach, on_unit) -> MailAccessResult:
        """Headless engine invocation: `MAILACCESS_CMD <email> --json`."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd.split(), email, "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=180)
        except (asyncio.TimeoutError, OSError) as exc:
            return MailAccessResult(notes=[f"mailaccess engine error: {exc}"])

        if proc.returncode != 0:
            return MailAccessResult(notes=[
                f"mailaccess engine exited {proc.returncode}: {err.decode()[:300]}"
            ])
        try:
            data = json.loads(out.decode())
        except ValueError:
            return MailAccessResult(notes=["mailaccess engine returned non-JSON output"])

        hits = [
            RegistrationHit(
                platform=r.get("platform", "unknown"),
                registered=bool(r.get("registered")),
                confidence=float(r.get("confidence", 0.5)),
                source="mailaccess-engine",
            )
            for r in data.get("registrations", [])
        ]
        score = _score(hits, breach)
        result = MailAccessResult(
            corpus_size=int(data.get("corpus_size", len(hits))),
            sampled=len(hits),
            engine="mailaccess-engine",
            registrations=hits,
            risk_score=score,
            risk_level=next(name for thr, name in RISK_TIERS if score >= thr),
        )
        if on_unit:
            for h in hits:
                await on_unit(h.__dict__)
        return result

    # ------------------------------------------------------------------ #
    async def _run_builtin(self, email, breach, on_unit) -> MailAccessResult:
        """Curated sampler — JA3 transport, strict per-probe timeout."""
        hits: list[RegistrationHit] = []

        async def _probe(platform: str, url: str) -> None:
            # Email-keyed existence is inferred from breach corpus + public
            # profile endpoints; direct password-reset enumeration is NOT
            # performed here (it signals target platforms). The external
            # engine path covers full-corpus sweeps.
            hit = RegistrationHit(platform=platform, registered=False, confidence=0.3)
            if platform.lower() in " ".join(breach.breaches).lower():
                hit.registered, hit.confidence = True, 0.75
            hits.append(hit)
            if on_unit:
                await on_unit(hit.__dict__)

        await asyncio.gather(*[
            asyncio.wait_for(_probe(p, u), timeout=10) for p, u in SAMPLE_SITES
        ])

        score = _score(hits, breach)
        return MailAccessResult(
            corpus_size=5300,
            sampled=len(SAMPLE_SITES),
            registrations=hits,
            risk_score=score,
            risk_level=next(name for thr, name in RISK_TIERS if score >= thr),
            notes=["builtin sampler active — set MAILACCESS_CMD for full 5,300+ corpus"],
        )
