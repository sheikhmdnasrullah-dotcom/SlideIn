"""Domain & infrastructure auditing — Dnsrecon-equivalent.

Async DNS enumeration (dnspython asyncio backend) of A / AAAA / MX / TXT / NS /
SOA, plus full mail-authentication extraction:

  SPF   — v=spf1 record: all-qualifier, includes, mechanisms
  DKIM  — probes the common selectors used by Google Workspace, M365, SendGrid,
          Zendesk, etc.  (`s1`/`selector1` for M365, `google` for Workspace)
  DMARC — _dmarc TXT: p/sp/adkim/aspf/rua/ruf

Deliverability risk rules flag setups that will hurt *our* sends to this
domain (missing MX, strict DMARC on a spoof-checking target, weak ~all SPF...)
and posture signals useful for personalization (which SaaS they run).
"""
from __future__ import annotations

import dns.asyncresolver
import dns.resolver

from ..config import settings
from ..schemas import DNSRecords, DKIMRecord, DMARCRecord, MailAuth, SPFRecord

# Selector inventory worth probing (extend freely).
DKIM_SELECTORS = [
    "google",            # Google Workspace
    "selector1", "selector2",   # Microsoft 365
    "default", "mail", "dkim",  # generic panels / cPanel
    "s1", "s2",          # SendGrid, common ESPs
    "k1",                # Mailchimp / Mandrill
    "zendesk1", "zendesk2",
    "20230601", "20221208",  # rotating Yahoo/ESP selectors seen in the wild
]

_NXDOMAIN = (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers)


class DNSAuditor:
    def __init__(self):
        self._resolver = dns.asyncresolver.Resolver()
        self._resolver.timeout = settings.dns_timeout
        self._resolver.lifetime = settings.dns_lifetime

    @staticmethod
    def selector_count() -> int:
        return len(DKIM_SELECTORS)

    async def audit(self, domain: str, on_step=None) -> tuple[DNSRecords, MailAuth, list[str]]:
        domain = domain.strip(".")
        a, aaaa, mx, txt, ns, soa = await self._resolve_all(domain, on_step=on_step)

        spf = self._parse_spf(txt)
        dmarc = await self._parse_dmarc(domain)
        dkim = await self._probe_dkim(domain, on_step=on_step)

        risks = self._risk_rules(mx=mx, spf=spf, dkim=dkim, dmarc=dmarc, a=a)
        return (
            DNSRecords(a=a, aaaa=aaaa, mx=mx, txt=txt, ns=ns, soa=soa),
            MailAuth(spf=spf, dkim=dkim, dmarc=dmarc),
            risks,
        )

    # ------------------------------------------------------------------ #
    async def _resolve_all(self, domain: str, on_step=None):
        async def _q(rtype: str) -> list[str]:
            try:
                ans = await self._resolver.resolve(domain, rtype)
            except _NXDOMAIN:
                return []
            except dns.resolver.Timeout:
                return []
            out = []
            for r in ans:
                if rtype == "TXT":
                    out.append(b"".join(r.strings).decode("utf-8", "replace"))
                else:
                    out.append(r.to_text())
            if on_step is not None:
                await on_step(rtype, len(out))
            return out

        results = await __import__("asyncio").gather(
            _q("A"), _q("AAAA"), _q("MX"), _q("TXT"), _q("NS"), _q("SOA")
        )
        soa = results[5][0] if results[5] else None
        return results[0], results[1], results[2], results[3], results[4], soa

    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_spf(txt: list[str]) -> SPFRecord:
        record = next((t for t in txt if t.startswith("v=spf1")), None)
        if not record:
            return SPFRecord(present=False)
        tokens = record.split()
        includes = [t[8:] for t in tokens if t.startswith("include:")]
        mechanisms = [t for t in tokens if t.startswith(("ip4:", "ip6:", "a:", "mx:"))]
        all_tok = next((t for t in tokens if t.endswith("all")), None)
        qualifier = all_tok[0] if all_tok and all_tok[0] in "-~?+" else None
        return SPFRecord(
            present=True, record=record, all_qualifier=qualifier,
            includes=includes, mechanisms=mechanisms,
        )

    async def _parse_dmarc(self, domain: str) -> DMARCRecord:
        try:
            ans = await self._resolver.resolve(f"_dmarc.{domain}", "TXT")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
            return DMARCRecord(present=False)
        record = next(
            (b"".join(r.strings).decode("utf-8", "replace") for r in ans
             if b"".join(r.strings).decode("utf-8", "replace").startswith("v=DMARC1")),
            None,
        )
        if not record:
            return DMARCRecord(present=False)

        def _tag(name: str) -> str | None:
            for part in record.split(";"):
                k, _, v = part.strip().partition("=")
                if k.strip() == name:
                    return v.strip()
            return None

        return DMARCRecord(
            present=True,
            record=record,
            policy=_tag("p"),
            subdomain_policy=_tag("sp"),
            alignment_dkim=_tag("adkim"),
            alignment_spf=_tag("aspf"),
            aggregate_uris=(_tag("rua") or "").split(","),
            forensic_uris=(_tag("ruf") or "").split(","),
        )

    async def _probe_dkim(self, domain: str, on_step=None) -> list[DKIMRecord]:
        import asyncio

        async def _one(selector: str) -> DKIMRecord | None:
            try:
                ans = await self._resolver.resolve(
                    f"{selector}._domainkey.{domain}", "TXT"
                )
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout):
                if on_step is not None:
                    await on_step(f"DKIM:{selector}", 0)
                return None
            txt = b"".join(ans[0].strings).decode("utf-8", "replace")
            if on_step is not None:
                await on_step(f"DKIM:{selector}", 1)
            if "v=DKIM1" not in txt and "k=" not in txt:
                return None
            k = None
            for part in txt.split(";"):
                key, _, val = part.strip().partition("=")
                if key.strip() == "k":
                    k = val.strip()
            return DKIMRecord(selector=selector, record=txt[:200], key_type=k)

        found = await asyncio.gather(*[_one(s) for s in DKIM_SELECTORS])
        return [f for f in found if f is not None]

    # ------------------------------------------------------------------ #
    @staticmethod
    def _risk_rules(*, mx, spf, dkim, dmarc, a) -> list[str]:
        risks: list[str] = []
        if not a:
            risks.append("CRITICAL: domain has no A record — parked or dead domain")
        if not mx:
            risks.append("HIGH: no MX records — mail to this domain will hard-bounce")
        if not spf.present:
            risks.append("MEDIUM: no SPF record — permissive sender verification")
        elif spf.all_qualifier in ("~", None):
            risks.append("LOW: SPF is softfail (~all) or open — spoofing-tolerant")
        if not dkim:
            risks.append("LOW: no discoverable DKIM selector")
        if not dmarc.present:
            risks.append("MEDIUM: no DMARC policy")
        elif dmarc.policy in (None, "none"):
            risks.append("LOW: DMARC p=none — monitor-only, spoofable")
        return risks


def tech_hints_from(mx: list[str], txt: list[str], ns: list[str]) -> list[str]:
    """SaaS/CDN fingerprints from infra records — feeds personalization 'likely_stack'."""
    blob = " ".join(mx + txt + ns).lower()
    hints: list[str] = []
    fingerprints = {
        "google workspace": ("google.com", "googlemail.com"),
        "microsoft 365": ("protection.outlook.com", "mail.protection"),
        "zoho mail": ("zoho.com",),
        "cloudflare": ("cloudflare",),
        "aws": ("amazonaws.com", "awsdns"),
        "google cloud": ("googlehosted.com",),
        "sendgrid": ("sendgrid.net",),
        "mailchimp": ("mandrillapp", "mailchimp"),
        "zendesk": ("zendesk.com",),
        "salesforce": ("salesforce", "exacttarget"),
        "proofpoint": ("proofpoint", "pphosted"),
        "mimecast": ("mimecast",),
        "dkim rotated (esp)": ("k=rsa",),
    }
    for name, needles in fingerprints.items():
        if any(n in blob for n in needles):
            hints.append(name)
    return hints
