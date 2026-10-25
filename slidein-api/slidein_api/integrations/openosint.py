"""OpenOSINT adapter — runs the `openosint` CLI as a subprocess.

OpenOSINT (https://github.com/OpenOSINT/OpenOSINT) exposes every direct
tool behind `--json` with one stable schema::

    {"tool": ..., "target": ..., "timestamp": ..., "results": [line, ...], "error": null}

so this adapter only has to spawn the binary, parse stdout and hand back
:class:`LookupResult` rows. No vendor SDK, no network code — the CLI owns
its own keys, rate limits and tool policy.

Two entry styles:

* :meth:`OpenOSINTAdapter.run_lookups` (async) — what the services call;
  every lookup is its own subprocess run in a worker thread so one slow
  tool never blocks the others.
* :meth:`OpenOSINTAdapter.enrich` — the sync :class:`EnrichmentAdapter`
  interface for domain/company enrichment.

Configuration (env, all optional):

=====================  ====================================================
``OPENOSINT_CLI``      Path to the binary. Default ``openosint`` (PATH).
``OPENOSINT_WORKDIR``  Working directory for the CLI (where its ``.env``
                       lives). Default: inherit.
``OPENOSINT_ALLOW_ACTIVE``  ``1`` to permit noisy/active lookups
                       (email/username enumeration) without an explicit
                       per-request opt-in.
=====================  ====================================================

Active lookups (``email``, ``username``) probe third-party sign-up flows
from your IP and may notify the account owner; they only run when
``allow_active`` says so, mirroring the CLI's own ``--allow-active`` gate.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..errors import ValidationError
from .adapters import AdapterStatus, ConnectionInfo, EnrichmentAdapter

#: Env fallbacks — read at call time so tests and callers can override.
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str) -> bool:
    return _env(name).lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class LookupSpec:
    """One supported lookup: how to invoke it and how to file its evidence."""

    tool: str  #: `openosint` subcommand (dns, exposure, github, …)
    active: bool  #: needs the CLI's --allow-active flag
    timeout: float  #: seconds before the subprocess is killed
    evidence_type: str  #: EvidenceItem.evidence_type this lookup produces
    confidence: float  #: claim confidence when the tool succeeds
    description: str


LOOKUP_SPECS: dict[str, LookupSpec] = {
    "dns": LookupSpec(
        tool="dns",
        active=False,
        timeout=30.0,
        evidence_type="dns_record",
        confidence=1.0,
        description="DNS records with SPF/DMARC/DKIM email-security analysis.",
    ),
    "exposure": LookupSpec(
        tool="exposure",
        active=False,
        timeout=90.0,
        evidence_type="security_posture",
        confidence=0.9,
        description="External exposure report (A-F grade) for the domain.",
    ),
    "github": LookupSpec(
        tool="github",
        active=False,
        timeout=45.0,
        evidence_type="social_profile",
        confidence=1.0,
        description="GitHub profile, repositories and commit-email discovery.",
    ),
    "email": LookupSpec(
        tool="email",
        active=True,
        timeout=150.0,
        evidence_type="account_footprint",
        confidence=0.8,
        description="Account enumeration for an email address (holehe).",
    ),
    "username": LookupSpec(
        tool="username",
        active=True,
        timeout=180.0,
        evidence_type="social_profile",
        confidence=0.75,
        description="Username enumeration across sites (sherlock).",
    ),
}

#: Passive lookups run when the caller does not pick.
DEFAULT_LOOKUPS: tuple[str, ...] = ("dns", "exposure", "github")

#: Active lookups only ever run on explicit opt-in.
ACTIVE_LOOKUPS: frozenset[str] = frozenset(
    name for name, spec in LOOKUP_SPECS.items() if spec.active
)

#: Claim text cap — evidence rows feed an LLM context, not an archive.
MAX_CLAIM_CHARS = 6000

#: Cap on exposure finding lines folded into one claim.
MAX_FINDING_LINES = 20

#: CSI/OSC escape sequences some wrapped tools emit (holehe repaints the
#: terminal before printing its table).
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-_]")


def _strip_ansi(text: str) -> str:
    """Remove terminal escape sequences so claims stay clean text."""
    return _ANSI_RE.sub("", text)


def _exposure_lines(payload: dict) -> list[str]:
    """Flatten the `openosint --json exposure` report object into lines.

    Unlike the other tools, `exposure` prints a report document
    ({domain, grade, score, checks, findings, ...}) instead of the
    standard ``{tool, target, results, error}`` envelope.
    """
    domain = str(payload.get("domain") or "unknown")
    grade = str(payload.get("grade") or "?")
    summary = f"[exposure] {domain} grade {grade}"
    if payload.get("score") is not None:
        summary += f" score {payload['score']}"
    if payload.get("score_is_partial"):
        summary += " (partial)"
    lines = [summary]

    checks = payload.get("checks") or {}
    for name, info in checks.items():
        if isinstance(info, dict):
            status = info.get("status") or "?"
            reason = info.get("reason")
            suffix = f" ({reason})" if reason else ""
            lines.append(f"[exposure] check {name}: {status}{suffix}")

    findings = payload.get("findings") or []
    for finding in findings[:MAX_FINDING_LINES]:
        if isinstance(finding, dict):
            severity = finding.get("severity") or "info"
            title = finding.get("title") or finding.get("id") or ""
            lines.append(f"[exposure] {severity}: {title}")
    return lines


@dataclass
class LookupResult:
    """Outcome of one `openosint --json <tool> <target>` invocation."""

    lookup: str
    tool: str
    target: str
    lines: list[str] = field(default_factory=list)
    error: str = ""
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.lines)

    def summary(self) -> dict:
        return {
            "lookup": self.lookup,
            "tool": self.tool,
            "target": self.target,
            "ok": self.ok,
            "error": self.error or None,
            "lines": len(self.lines),
            "duration_ms": self.duration_ms,
        }


class OpenOSINTAdapter(EnrichmentAdapter):
    """Subprocess bridge to the OpenOSINT CLI."""

    name = "openosint"

    def __init__(
        self,
        *,
        cli: str | None = None,
        workdir: str | None = None,
        allow_active: bool | None = None,
    ) -> None:
        self.cli = cli or _env("OPENOSINT_CLI", "openosint")
        self.workdir = workdir if workdir is not None else _env("OPENOSINT_WORKDIR") or None
        self.allow_active = allow_active if allow_active is not None else _env_bool(
            "OPENOSINT_ALLOW_ACTIVE"
        )

    # ------------------------------------------------------------------
    # Sync core (thread-safe; the async surface runs these in workers)
    # ------------------------------------------------------------------

    def _run_one(self, lookup: str, target: str, allow_active: bool) -> LookupResult:
        spec = LOOKUP_SPECS[lookup]
        started = time.monotonic()

        def done(lines: list[str] | None = None, error: str = "") -> LookupResult:
            return LookupResult(
                lookup=lookup,
                tool=spec.tool,
                target=target,
                lines=lines or [],
                error=error,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        if spec.active and not allow_active:
            return done(
                error=(
                    f"lookup {lookup!r} is active/noisy and allow_active is off; "
                    "pass allow_active=true to run it"
                )
            )
        if not str(target or "").strip():
            return done(error=f"lookup {lookup!r} has no target for this prospect")

        cmd = [self.cli, "--json"]
        if spec.active:
            cmd.append("--allow-active")
        cmd += [spec.tool, str(target)]

        # Wrapped tools spawn siblings (sherlock, …) from PATH — make sure
        # the CLI's own bin dir is visible regardless of the caller's env.
        cli_dir = os.path.dirname(os.path.abspath(self.cli))
        env = {**os.environ, "PATH": f"{cli_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=spec.timeout,
                cwd=self.workdir or None,
                env=env,
            )
        except FileNotFoundError:
            return done(
                error=(
                    f"openosint CLI not found at {self.cli!r}; set OPENOSINT_CLI "
                    "to the binary path"
                )
            )
        except subprocess.TimeoutExpired:
            return done(error=f"{lookup} lookup timed out after {spec.timeout:.0f}s")
        except OSError as exc:  # pragma: no cover - exotic spawn failures
            return done(error=f"failed to run openosint CLI: {exc}")

        return self._parse(lookup, target, proc, started)

    @staticmethod
    def _parse(
        lookup: str,
        target: str,
        proc: subprocess.CompletedProcess,
        started: float,
    ) -> LookupResult:
        spec = LOOKUP_SPECS[lookup]

        def done(lines: list[str] | None = None, error: str = "") -> LookupResult:
            return LookupResult(
                lookup=lookup,
                tool=spec.tool,
                target=target,
                lines=[_strip_ansi(str(line)) for line in lines or []],
                error=_strip_ansi(error),
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        payload: Any = None
        stdout = (proc.stdout or "").strip()
        if stdout:
            try:
                payload = json.loads(stdout)
            except ValueError:
                payload = None

        if isinstance(payload, dict):
            tool_error = str(payload.get("error") or "").strip()
            if tool_error:
                return done(error=tool_error)
            if "results" in payload:
                lines = [str(line) for line in payload.get("results") or []]
                if lines:
                    return done(lines=lines)
            elif "grade" in payload or "checks" in payload:
                lines = _exposure_lines(payload)
                if lines:
                    return done(lines=lines)
            return done(
                error=f"{lookup} returned no results (exit {proc.returncode})"
            )

        if stdout or proc.stderr:
            tail = (proc.stderr or stdout).strip()
            return done(error=tail[-500:])
        return done(error=f"{lookup} CLI exited {proc.returncode} with no output")

    # ------------------------------------------------------------------
    # Async surface used by the services
    # ------------------------------------------------------------------

    async def run_lookups(
        self,
        targets: Mapping[str, str],
        lookups: Sequence[str] | None = None,
        *,
        allow_active: bool | None = None,
    ) -> list[LookupResult]:
        """Run each lookup in its own subprocess, in parallel.

        ``targets`` maps a lookup name to the value to run it against
        (domain for dns/exposure, query for github, address for email, …).
        Lookups without a target still return a result row — with an error
        — so callers can report exactly what was and was not attempted.
        """
        selected = list(lookups) if lookups else list(DEFAULT_LOOKUPS)
        unknown = [name for name in selected if name not in LOOKUP_SPECS]
        if unknown:
            raise ValidationError(
                f"Unknown OpenOSINT lookup(s): {', '.join(sorted(unknown))}",
                code="prospect_invalid",
                details={"allowed": sorted(LOOKUP_SPECS)},
                recovery_action="fix_prospect_record",
            )
        effective = self.allow_active if allow_active is None else bool(allow_active)

        tasks = [
            asyncio.to_thread(self._run_one, name, str(targets.get(name, "")), effective)
            for name in selected
        ]
        return list(await asyncio.gather(*tasks)) if tasks else []

    # ------------------------------------------------------------------
    # EnrichmentAdapter ABC
    # ------------------------------------------------------------------

    def enrich(self, *, domain: str = "", company: str = "") -> dict:
        """Passive enrichment for a domain/company (sync, thread-friendly)."""
        targets: dict[str, str] = {}
        if domain:
            targets["dns"] = domain
            targets["exposure"] = domain
        if company:
            targets["github"] = company
        if not targets:
            raise ValidationError(
                "OpenOSINT enrichment needs a domain or a company name",
                code="prospect_invalid",
                recovery_action="fix_prospect_record",
            )
        results = [self._run_one(name, value, allow_active=False) for name, value in targets.items()]
        return {
            "adapter": self.name,
            "lookups": [r.summary() for r in results],
            "succeeded": [r.lookup for r in results if r.ok],
            "failed": [r.lookup for r in results if not r.ok],
        }

    def health(self) -> ConnectionInfo:
        """Is the CLI reachable? Never throws — health checks degrade."""
        executable = self.cli if os.path.isabs(self.cli) else shutil.which(self.cli)
        if not executable or not os.path.exists(executable):
            return ConnectionInfo(
                adapter=self.name,
                status=AdapterStatus.DISCONNECTED,
                detail=f"openosint CLI not found at {self.cli!r} (set OPENOSINT_CLI)",
            )
        try:
            proc = subprocess.run(
                [self.cli, "--help"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=self.workdir or None,
            )
        except subprocess.TimeoutExpired:
            return ConnectionInfo(
                adapter=self.name, status=AdapterStatus.FAILING, detail="CLI --help timed out"
            )
        except OSError as exc:
            return ConnectionInfo(
                adapter=self.name, status=AdapterStatus.FAILING, detail=str(exc)
            )
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0 and "openosint" in output.lower():
            return ConnectionInfo(
                adapter=self.name,
                status=AdapterStatus.CONNECTED,
                detail=f"cli={executable}",
            )
        return ConnectionInfo(
            adapter=self.name,
            status=AdapterStatus.FAILING,
            detail=f"CLI --help exited {proc.returncode}",
        )


__all__ = [
    "ACTIVE_LOOKUPS",
    "DEFAULT_LOOKUPS",
    "LOOKUP_SPECS",
    "LookupResult",
    "LookupSpec",
    "OpenOSINTAdapter",
    "MAX_CLAIM_CHARS",
]
