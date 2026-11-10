"""Heavy OSINT enrichment tools — specs, execution, and output parsers.

Every tool here is a real command-line program run against the prospect's
domain / email / username. Parsers are deliberately defensive: OSINT tools
change output formats between versions, so a parser that finds nothing
returns empty results instead of raising, and the orchestrator records the
tool as "ran, no findings".

Tool order mirrors the approved stack order: map the perimeter (subfinder,
dnsrecon), extract contacts (theHarvester), code footprint (GitHub CLI),
then the person (holehe, maigret), with Spiderfoot as the deep pass.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EnrichmentToolSpec:
    tool_id: str
    argv: tuple[str, ...]           # placeholders: {domain} {email} {username} {name} {company} {out}
    timeout_seconds: int
    capabilities: tuple[str, ...]
    deep_only: bool = False
    env_extra: dict[str, str] = field(default_factory=dict)


TOOL_SPECS: tuple[EnrichmentToolSpec, ...] = (
    EnrichmentToolSpec(
        "subfinder", ("subfinder", "-silent", "-d", "{domain}"), 60,
        ("subdomain_discovery",),
    ),
    EnrichmentToolSpec(
        "dnsrecon", ("dnsrecon", "-d", "{domain}", "-t", "std", "--threads", "4"), 90,
        ("dns_research",),
    ),
    EnrichmentToolSpec(
        "theharvester",
        ("theHarvester", "-d", "{domain}", "-b", "bing,duckduckgo,rapiddns,otx",
         "-f", "{out}"), 180,
        ("contact_extraction", "subdomain_discovery"),
    ),
    EnrichmentToolSpec(
        "github_cli",
        ("gh", "search", "repos", "{company}", "--limit", "10",
         "--json", "fullName,url,description,stargazersCount,updatedAt"), 45,
        ("code_footprint",),
    ),
    EnrichmentToolSpec(
        "holehe", ("holehe", "{email}", "--only-used", "--no-color"), 240,
        ("account_enumeration",),
    ),
    EnrichmentToolSpec(
        "maigret", ("maigret", "{username}", "--print-found", "--json", "{out}",
                    "--timeout", "12", "--retries", "0"), 300,
        ("username_enumeration",),
        deep_only=False,
    ),
    EnrichmentToolSpec(
        "spiderfoot",
        ("docker", "run", "--rm", os.environ.get("SPIDERFOOT_IMAGE", "spiderfoot"),
         "-s", "{domain}", "-m",
         "sfp_dnsresolve,sfp_email,sfp_socialmedia,sfp_accounts,sfp_webframework",
         "-q", "-o", "json"), 420,
        ("contact_extraction", "account_enumeration", "username_enumeration"),
        deep_only=True,
    ),
)


def run_tool(spec: EnrichmentToolSpec, *, target: dict[str, str]) -> dict[str, Any]:
    """Run one tool and return {"ok", "stdout", "stderr", "parsed", "timed_out"}.

    Never raises: a missing binary, a non-zero exit, or a parse failure is
    reported in-band so the caller can record it per tool.
    """
    with tempfile.TemporaryDirectory(prefix="slidein-enrich-") as tmp:
        out_base = os.path.join(tmp, "out")
        argv = [a.format(out=out_base, **{k: v for k, v in target.items()}) for a in spec.argv]
        env = dict(os.environ)
        env.update(spec.env_extra)
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=spec.timeout_seconds,
                env=env,
            )
        except FileNotFoundError:
            return {"ok": False, "error": "command_not_found", "argv0": argv[0]}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout", "parsed": {}}
        parsed = parse_output(spec.tool_id, proc.stdout or "", tmp, out_base)
        ok = proc.returncode == 0 or bool(parsed)
        return {
            "ok": ok,
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-1000:],
            "parsed": parsed,
        }


# ---------------------------------------------------------------------------
# Parsers — one per tool, all defensive.
# ---------------------------------------------------------------------------

def parse_subfinder(stdout: str) -> dict[str, list[str]]:
    hosts = sorted({line.strip().lower() for line in stdout.splitlines()
                    if "." in line and " " not in line.strip() and line.strip()})
    return {"subdomains": hosts}


_DNS_RE = re.compile(r"\[(MX|SPF|TXT|SOA|A|NS)\]\s+(.+)", re.I)


def parse_dnsrecon(stdout: str) -> dict[str, list[str]]:
    records: list[str] = []
    for line in stdout.splitlines():
        m = _DNS_RE.search(line)
        if m:
            records.append(f"{m.group(1).upper()} {m.group(2).strip()}")
    return {"records": records[:100]}


def parse_theharvester(stdout: str, tmp: str, out_base: str) -> dict[str, Any]:
    # -f writes <out>.json (and .xml) in newer versions; fall back to stdout.
    for candidate in (out_base + ".json", os.path.join(tmp, "out.json")):
        if os.path.exists(candidate):
            try:
                data = json.load(open(candidate))
                return _harvester_payload(data)
            except (ValueError, OSError):
                continue
    return _harvester_payload({})


def _harvester_payload(data: dict) -> dict[str, list[str]]:
    def as_list(key: str) -> list[str]:
        value = data.get(key) or []
        return [str(v) for v in value][:100]

    return {
        "emails": as_list("emails"),
        "hosts": as_list("hosts"),
        "linkedin_people": as_list("linkedin_people"),
        "twitter_people": as_list("twitter_people"),
        "interesting_urls": as_list("interesting_urls"),
    }


def parse_gh(stdout: str) -> dict[str, list[dict[str, Any]]]:
    try:
        data = json.loads(stdout or "[]")
    except ValueError:
        return {"repos": []}
    repos = []
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        repos.append({
            "full_name": str(row.get("fullName") or ""),
            "url": str(row.get("url") or ""),
            "description": str(row.get("description") or "")[:200],
            "stars": int(row.get("stargazersCount") or 0),
        })
    return {"repos": repos[:25]}


_HOLEHE_OK = re.compile(r"^\[\+]\s*(\S+)", re.M)


def parse_holehe(stdout: str) -> dict[str, list[str]]:
    sites = sorted({m.group(1).lower() for m in _HOLEHE_OK.finditer(stdout or "")})
    return {"accounts": sites}


def parse_maigret(stdout: str, tmp: str, out_base: str) -> dict[str, list[dict[str, str]]]:
    path = out_base + ".json"
    if not os.path.exists(path):
        m = re.search(r"Saving report to\s+(\S+\.json)", stdout or "")
        if m and os.path.exists(m.group(1)):
            path = m.group(1)
    if not os.path.exists(path):
        return {"profiles": []}
    try:
        data = json.load(open(path))
    except (ValueError, OSError):
        return {"profiles": []}
    found: list[dict[str, str]] = []
    urls = data.get("urls") if isinstance(data, dict) else None
    if isinstance(urls, list):
        for item in urls:
            if not isinstance(item, dict):
                continue
            status = item.get("status") or {}
            ok = bool(status.get("ok")) or int(status.get("http_status") or 0) == 200
            if ok and item.get("url"):
                found.append({
                    "url": str(item["url"]),
                    "site": str(item.get("site") or item.get("name") or ""),
                })
    return {"profiles": found[:100]}


def parse_spiderfoot(stdout: str) -> dict[str, Any]:
    try:
        rows = json.loads(stdout or "[]")
    except ValueError:
        return {}
    emails: set[str] = set()
    socials: set[str] = set()
    accounts: set[str] = set()
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, list) or len(row) < 3:
                continue
            _module, type_, value = str(row[0]), str(row[1]).upper(), str(row[2])
            if "EMAIL" in type_ and "@" in value:
                emails.add(value.strip().lower())
            elif "SOCIAL" in type_:
                socials.add(value.strip())
            elif "ACCOUNT" in type_ or "USERNAME" in type_:
                accounts.add(value.strip())
    return {
        "emails": sorted(emails)[:50],
        "socials": sorted(socials)[:50],
        "accounts": sorted(accounts)[:50],
    }


def parse_output(tool_id: str, stdout: str, tmp: str, out_base: str) -> dict[str, Any]:
    if tool_id == "subfinder":
        return parse_subfinder(stdout)
    if tool_id == "dnsrecon":
        return parse_dnsrecon(stdout)
    if tool_id == "theharvester":
        return parse_theharvester(stdout, tmp, out_base)
    if tool_id == "github_cli":
        return parse_gh(stdout)
    if tool_id == "holehe":
        return parse_holehe(stdout)
    if tool_id == "maigret":
        return parse_maigret(stdout, tmp, out_base)
    if tool_id == "spiderfoot":
        return parse_spiderfoot(stdout)
    return {}


__all__ = ["EnrichmentToolSpec", "TOOL_SPECS", "run_tool"]
