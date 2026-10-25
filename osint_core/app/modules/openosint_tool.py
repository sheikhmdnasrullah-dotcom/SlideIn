"""OpenOSINT CLI bridge — one spawn per lookup, JSON-safe dict out.

Mirrors the proven slidein-api adapter (integrations/openosint.py): the
`openosint` binary is run as ``openosint --json <tool> <target>`` and its
stable envelope ``{tool, target, timestamp, results, error}`` is flattened
into plain text lines. `exposure` is the one exception — it prints a report
object ({domain, grade, score, checks, findings}) which we flatten here too.

Passive by default (dns, exposure, github). The noisy enumerators (email,
username) only run when ``allow_active=True`` or
``OPENOSINT_ALLOW_ACTIVE=1`` — mirroring the CLI's own --allow-active gate.

Return shape (always; failures degrade to error rows, never raise)::

    {"available": bool, "source": "openosint-cli",
     "lookups": [{"lookup": "dns", "target": "example.com", "ok": True,
                  "error": None, "lines": ["..."], "duration_ms": 421}, ...]}
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from typing import Sequence

from ..config import settings

DEFAULT_LOOKUPS: tuple[str, ...] = ("dns", "exposure", "github")

#: lookup -> (openosint subcommand, needs --allow-active, timeout seconds)
SPECS: dict[str, tuple[str, bool, float]] = {
    "dns": ("dns", False, 30.0),
    "exposure": ("exposure", False, 90.0),
    "github": ("github", False, 45.0),
    "email": ("email", True, 150.0),
    "username": ("username", True, 180.0),
}

MAX_FINDING_LINES = 20
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-_]"
)


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def targets_for(email: str = "", handle: str = "", domain: str = "",
                local_part: str = "") -> dict[str, str]:
    """Map lookup name -> target value; empty string means 'no target'."""
    return {
        "dns": domain or "",
        "exposure": domain or "",
        "github": handle or "",
        "email": email or "",
        "username": handle or local_part or "",
    }


def exposure_lines(payload: dict) -> list[str]:
    """Flatten the exposure report object into agent-friendly lines."""
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


async def _run_one(lookup: str, target: str, *, cli: str,
                   allow_active: bool) -> dict:
    tool, active, timeout = SPECS[lookup]
    started = time.monotonic()

    def row(lines: list[str] | None = None, error: str = "") -> dict:
        return {
            "lookup": lookup,
            "target": target,
            "ok": not error and bool(lines),
            "error": _strip_ansi(error) or None,
            "lines": [_strip_ansi(str(line)) for line in lines or []],
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    if active and not allow_active:
        return row(error=f"lookup {lookup!r} is active/noisy and allow_active is off")
    if not target.strip():
        return row(error=f"lookup {lookup!r} has no target for this lead")

    cmd = [cli, "--json"]
    if active:
        cmd.append("--allow-active")
    cmd += [tool, target]

    # Wrapped tools spawn siblings (sherlock, …) from PATH — keep the
    # CLI's own bin dir visible regardless of the caller's env.
    cli_dir = os.path.dirname(os.path.abspath(cli))
    env = {**os.environ, "PATH": f"{cli_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except FileNotFoundError:
        return row(
            error=f"openosint CLI not found at {cli!r}; set OPENOSINT_BIN"
        )
    except asyncio.TimeoutError:
        return row(error=f"{lookup} lookup timed out after {timeout:.0f}s")
    except OSError as exc:
        return row(error=f"failed to run openosint CLI: {exc}")

    stdout = (stdout_b or b"").decode("utf-8", "replace").strip()
    stderr = (stderr_b or b"").decode("utf-8", "replace")

    payload = None
    if stdout:
        try:
            payload = json.loads(stdout)
        except ValueError:
            payload = None

    if isinstance(payload, dict):
        tool_error = str(payload.get("error") or "").strip()
        if tool_error:
            return row(error=tool_error)
        if "results" in payload:
            lines = [str(line) for line in payload.get("results") or []]
            if lines:
                return row(lines=lines)
        elif "grade" in payload or "checks" in payload:
            lines = exposure_lines(payload)
            if lines:
                return row(lines=lines)
        return row(error=f"{lookup} returned no results (exit {proc.returncode})")

    if stderr.strip() or stdout:
        return row(error=(stderr.strip() or stdout)[-500:])
    return row(error=f"{lookup} CLI exited {proc.returncode} with no output")


async def run_openosint(
    email: str = "",
    handle: str = "",
    domain: str = "",
    *,
    lookups: Sequence[str] | None = None,
    allow_active: bool | None = None,
    cli: str | None = None,
) -> dict:
    """Run the selected lookups in parallel; never raises.

    Unknown lookup names are ignored (they surface as error rows) so a
    typo in config can never take the agent pipeline down.
    """
    selected = [name for name in (lookups or DEFAULT_LOOKUPS) if name in SPECS]
    effective = (
        settings.openosint_allow_active if allow_active is None else bool(allow_active)
    )
    bin_path = cli or settings.openosint_bin
    resolved = bin_path if os.path.isabs(bin_path) else shutil.which(bin_path)
    available = bool(resolved and os.path.exists(resolved))
    targets = targets_for(
        email=email, handle=handle, domain=domain,
        local_part=email.split("@", 1)[0] if email else "",
    )

    rows = list(
        await asyncio.gather(
            *(
                _run_one(name, targets.get(name, ""), cli=bin_path,
                         allow_active=effective)
                for name in selected
            )
        )
    ) if selected else []
    return {
        "available": available,
        "source": "openosint-cli",
        "lookups": rows,
    }


__all__ = ["DEFAULT_LOOKUPS", "run_openosint", "targets_for", "exposure_lines"]
