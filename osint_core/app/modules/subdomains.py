"""Passive subdomain discovery — Subfinder-equivalent.

Aggregates subdomains from multiple passive sources (no packets sent to the
target — everything comes from CT logs and aggregator caches), then resolves
A/AAAA for each. An optional local `subfinder` binary adds one more source and
is skipped gracefully when absent.

Sources:
  crt.sh        Certificate Transparency log search (most exhaustive, free)
  bufferover    DNS aggregator cache
  hackertarget  hostsearch API
  subfinder     local binary, passive mode, if SUBFINDER_BIN is on PATH
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess

from ..config import settings
from ..core.http import HttpProbe, ProbeError
from ..schemas import Subdomain


async def _from_crtsh(domain: str, probe: HttpProbe) -> set[str]:
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    try:
        resp = await probe.get(url)
        import json

        rows = json.loads(resp.text)
        return {row["name_value"] for row in rows}
    except (ProbeError, ValueError):
        return set()


async def _from_bufferover(domain: str, probe: HttpProbe) -> set[str]:
    url = f"https://api.bufferover.run/v1/dns?q=.{domain}"
    try:
        resp = await probe.get(url)
        import json

        data = json.loads(resp.text)
        out = set()
        for row in data.get("Results") or []:
            _, _, host = row.partition(",")
            if host:
                out.add(host.strip())
        return out
    except (ProbeError, ValueError):
        return set()


async def _from_hackertarget(domain: str, probe: HttpProbe) -> set[str]:
    url = f"https://api.hackertarget.com/hostsearch/?q={domain}"
    try:
        resp = await probe.get(url)
        if "error" in resp.text.lower():
            return set()
        return {line.split(",")[0].strip() for line in resp.text.splitlines() if line.strip()}
    except ProbeError:
        return set()


async def _from_subfinder(domain: str) -> set[str]:
    binary = settings.subfinder_bin
    if not binary or not shutil.which(binary):
        return set()
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, "-d", domain, "-silent", "-timeout", "15",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        return {line.strip().lower() for line in out.decode().splitlines() if line.strip()}
    except (asyncio.TimeoutError, OSError):
        return set()


def _normalize(raw: set[str], domain: str) -> list[str]:
    subs: set[str] = set()
    suffix = "." + domain
    for item in raw:
        for host in item.splitlines():
            host = host.strip().lower().lstrip("*.").rstrip(".")
            if host == domain or host.endswith(suffix):
                subs.add(host)
    return sorted(subs)


async def discover_subdomains(domain: str, probe: HttpProbe, on_host=None) -> tuple[list[Subdomain], list[str]]:
    """Returns resolved subdomains + list of sources that contributed."""
    sources_used: list[str] = []
    tasks = {
        "crt.sh": _from_crtsh(domain, probe),
        "bufferover": _from_bufferover(domain, probe),
        "hackertarget": _from_hackertarget(domain, probe),
        "subfinder": _from_subfinder(domain),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    merged: set[str] = set()
    for name, result in zip(tasks.keys(), results):
        if isinstance(result, set) and result:
            sources_used.append(name)
            merged |= result

    hosts = _normalize(merged, domain)
    resolved = await _resolve_all(hosts, on_host=on_host)
    return resolved, sources_used


_ENV_HINTS = {
    "staging": "staging", "stage": "staging", "stg": "staging", "uat": "staging",
    "dev": "development", "development": "development", "test": "testing",
    "qa": "testing", "demo": "demo", "beta": "beta", "alpha": "beta",
    "admin": "admin", "dashboard": "admin", "console": "admin", "portal": "admin",
    "api": "api", "app": "app", "mail": "mail", "webmail": "mail",
    "vpn": "vpn", "git": "code", "gitlab": "code", "github": "code",
    "jenkins": "ci", "ci": "ci", "grafana": "monitoring", "kibana": "monitoring",
    "status": "status", "help": "support", "support": "support",
}


def _env_hint(host: str) -> str | None:
    return _ENV_HINTS.get(host.split(".")[0])


async def _resolve_all(hosts: list[str], on_host=None) -> list[Subdomain]:
    import dns.asyncresolver
    import dns.resolver

    resolver = dns.asyncresolver.Resolver()
    resolver.timeout = settings.dns_timeout
    resolver.lifetime = settings.dns_lifetime
    sem = asyncio.Semaphore(settings.subdomain_concurrency)

    async def _one(host: str) -> Subdomain | None:
        async with sem:
            try:
                a_ans = await resolver.resolve(host, "A")
                a = [r.to_text() for r in a_ans]
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
                a = []
            try:
                aaaa_ans = await resolver.resolve(host, "AAAA")
                aaaa = [r.to_text() for r in aaaa_ans]
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
                aaaa = []
            if not a and not aaaa:
                if on_host is not None:
                    await on_host({"host": host, "resolved": False})
                return None  # unresolvable CT-log ghost — drop it
            sub = Subdomain(host=host, a=a, aaaa=aaaa, environment_hint=_env_hint(host))
            if on_host is not None:
                await on_host(sub.model_dump())
            return sub

    results = await asyncio.gather(*[_one(h) for h in hosts])
    return [r for r in results if r is not None]
