"""DNS / authentication / blacklist audit for sending domains.

Shells out to `dig` (present on macOS and Linux). Returns a structured report with
per-record PASS/FAIL/WARN and a list of issues. This is the automated version of
the manual audit performed during the project kickoff.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Optional


def _dig(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["dig", "+short", *args], capture_output=True, text=True, timeout=15
        )
        return out.stdout.strip()
    except Exception as e:  # pragma: no cover
        return f"__error__{e}"


def _txt(domain: str) -> str:
    return _dig(["txt", domain])


def _first_spf(txt: str) -> str:
    for line in txt.splitlines():
        line = line.strip().strip('"')
        if line.lower().startswith("v=spf1"):
            return line
    return ""


@dataclass
class Check:
    name: str
    status: str  # PASS / FAIL / WARN / INFO
    detail: str


@dataclass
class AuditReport:
    domain: str
    checks: list[Check] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def add(self, name, status, detail):
        self.checks.append(Check(name, status, detail))
        if status in ("FAIL", "WARN"):
            self.issues.append(f"[{status}] {name}: {detail}")


def audit_domain(domain: str, sending_ip: Optional[str] = None,
                 dkim_selectors: Optional[list[str]] = None,
                 subdomains: Optional[list[str]] = None) -> AuditReport:
    rep = AuditReport(domain=domain)

    # SPF
    spf = _first_spf(_txt(domain))
    if spf:
        qualifier = "pass" if "-all" in spf or "~all" in spf else "softfail/none"
        rep.add("SPF", "PASS" if ("-all" in spf or "~all" in spf) else "WARN",
                spf)
        if "v=spf1" in spf and "all" not in spf.split("v=spf1")[-1]:
            rep.add("SPF-hardfail", "WARN", "SPF does not end in an 'all' mechanism")
    else:
        rep.add("SPF", "FAIL", "No SPF record found")

    # DMARC
    dmarc = _txt(f"_dmarc.{domain}")
    if dmarc:
        policy = "none"
        for tok in dmarc.split(";"):
            if "p=" in tok:
                policy = tok.split("p=")[1].strip().strip('"')
        rep.add("DMARC", "PASS", f"policy={policy}")
        if policy == "none":
            rep.add("DMARC-enforcement", "WARN",
                    "p=none (no enforcement; move to quarantine/reject after warmup)")
    else:
        rep.add("DMARC", "FAIL", "No DMARC record")

    # DKIM (try provided selectors, then common fallbacks)
    selectors = dkim_selectors or [
        "default", "k1", "s1", "s2", "mxa", "mxb", "selector1", "selector2",
        "google", "zoho", "mail", "zb",
    ]
    found = []
    for s in selectors:
        rec = _txt(f"{s}._domainkey.{domain}")
        if rec and "v=DKIM1" in rec:
            found.append(s)
    if found:
        rep.add("DKIM", "PASS", f"selectors present: {', '.join(found)}")
    else:
        rep.add("DKIM", "FAIL",
                f"No DKIM records found for selectors: {', '.join(selectors[:6])}...")

    # BIMI / MTA-STS / TLS-RPT (advisory)
    bimi = _txt(f"default._bimi.{domain}")
    rep.add("BIMI", "PASS" if bimi else "INFO",
            bimi[:60] if bimi else "not published (optional but recommended)")
    mta = _txt(f"_mta-sts.{domain}")
    rep.add("MTA-STS", "PASS" if mta else "INFO",
            mta[:40] if mta else "not published (optional)")
    tlsrpt = _txt(f"_smtp._tls.{domain}")
    rep.add("TLS-RPT", "PASS" if tlsrpt else "INFO",
            tlsrpt[:40] if tlsrpt else "not published (optional)")

    # Subdomains (e.g. email.tanim.tech) — must also have SPF/DMARC if used for sending
    for sub in (subdomains or []):
        s_spf = _first_spf(_txt(sub))
        s_dm = _txt(f"_dmarc.{sub}")
        if not s_spf:
            rep.add(f"SPF[{sub}]", "WARN", "subdomain has no SPF (ok if not a sending domain)")
        if not s_dm:
            rep.add(f"DMARC[{sub}]", "WARN", "subdomain has no DMARC (ok if not a sending domain)")

    # Reverse DNS for the sending IP
    if sending_ip:
        ptr = _dig(["-x", sending_ip])
        if ptr:
            rep.add("PTR", "PASS", ptr)
        else:
            rep.add("PTR", "WARN",
                    f"No PTR/FCrDNS for sending IP {sending_ip} "
                    f"(critical only if this IP sends mail directly)")

    return rep


def audit_blacklists(ip: str) -> list[Check]:
    """Check a sending IP against a few public DNSBLs."""
    bls = {
        "zen.spamhaus.org": "Spamhaus ZEN",
        "bl.spamcop.net": "SpamCop",
        "dnsbl.sorbs.net": "SORBS",
        "b.barracudacentral.org": "Barracuda",
    }
    out = []
    for zone, name in bls.items():
        rev = ".".join(reversed(ip.split(".")))
        res = _dig(["a", f"{rev}.{zone}"])
        if res and res.startswith("__error__"):
            # Lookup failure is NOT evidence of being clean. WARN lets the
            # pipeline fail closed instead of silently passing (fail-open).
            out.append(Check(f"DNSBL:{name}", "WARN", f"lookup failed: {res}"))
        elif res:
            out.append(Check(f"DNSBL:{name}", "FAIL", f"listed ({res})"))
        else:
            # Negative DNSBL answer (no A record) == not listed.
            out.append(Check(f"DNSBL:{name}", "PASS", "not listed"))
    return out


if __name__ == "__main__":
    import sys
    dom = sys.argv[1] if len(sys.argv) > 1 else "tanim.tech"
    ip = sys.argv[2] if len(sys.argv) > 2 else None
    r = audit_domain(dom, ip)
    for c in r.checks:
        print(f"{c.status:5} {c.name}: {c.detail}")
    print("\nISSUES:")
    print("\n".join(r.issues) or "  none")
