"""Noimosiny adapter — programmatic credential-risk indexing queries.

Noimosiny (soxoj/noimosiny-checker) correlates email/handle exposure across
breach corpora and paste indexes into a normalized risk index.

Paths:
  * NOIMOSINY_CMD set -> headless engine run, JSON report parsed.
  * Fallback -> risk index computed deterministically from the breach
    side-channel + MailAccess risk map (same 0..100 scale).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field

from ..schemas import BreachExposure


@dataclass
class NoimosinyResult:
    risk_index: int = 0
    level: str = "low"
    findings: list[str] = field(default_factory=list)
    engine: str = "builtin-index"

    def to_dict(self) -> dict:
        return {"risk_index": self.risk_index, "level": self.level,
                "findings": self.findings, "engine": self.engine}


_LEVELS = [(75, "critical"), (50, "high"), (25, "medium"), (0, "low")]


class NoimosinyAdapter:
    def __init__(self):
        self._cmd = os.getenv("NOIMOSINY_CMD", "")

    async def run(self, email: str, handle: str, breach: BreachExposure,
                  mailaccess: dict | None = None, on_unit=None) -> NoimosinyResult:
        if self._cmd and shutil.which(self._cmd.split()[0]):
            result = await self._run_engine(email, handle)
            if result is not None:
                if on_unit:
                    await on_unit({"risk_index": result.risk_index})
                return result
        return self._run_builtin(email, handle, breach, mailaccess, on_unit)

    async def _run_engine(self, email: str, handle: str) -> NoimosinyResult | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._cmd.split(), "--email", email, "--username", handle, "--json",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=150)
            data = json.loads(out.decode())
        except (asyncio.TimeoutError, OSError, ValueError):
            return None
        score = int(data.get("risk_index", 0))
        return NoimosinyResult(
            risk_index=score,
            level=next(n for t, n in _LEVELS if score >= t),
            findings=data.get("findings", []),
            engine="noimosiny-engine",
        )

    def _run_builtin(self, email, handle, breach, mailaccess, on_unit) -> NoimosinyResult:
        findings: list[str] = []
        score = 0
        if breach.breach_count:
            score += min(breach.breach_count * 8, 40)
            findings.append(f"present in {breach.breach_count} breach corpus(es)")
        sensitive = {"Passwords", "Password hints", "Private messages"} & set(breach.data_classes)
        if sensitive:
            score += 30
            findings.append("credential-class data classes exposed: " + ", ".join(sorted(sensitive)))
        if mailaccess:
            score = max(score, int(mailaccess.get("risk_score", 0)))
            findings.extend(mailaccess.get("notes", []))
        score = min(score, 100)
        if on_unit:
            try:
                asyncio.get_running_loop().create_task(on_unit({"risk_index": score}))
            except RuntimeError:
                pass
        return NoimosinyResult(
            risk_index=score,
            level=next(n for t, n in _LEVELS if score >= t),
            findings=findings or ["no elevated exposure signals"],
        )
