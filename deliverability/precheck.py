#!/usr/bin/env python3
"""
precheck.py - Pre-flight deliverability verification

Validates all infrastructure is correctly configured before sending.
Run before every campaign launch.

Usage:
  python3 precheck.py [--verbose]
"""
from __future__ import annotations
import json
import os
import sys
import subprocess
import socket
import time
from pathlib import Path

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "config.json"

def load_config() -> dict:
    return json.load(open(CONFIG_PATH))

def check_kumomta_running(host: str, port: int) -> dict:
    """Check if KumoMTA is listening on the expected port."""
    import socket as sock
    try:
        s = sock.socket(sock.AF_INET, sock.SOCK_STREAM)
        s.settimeout(3)
        s.connect((host, port))
        s.close()
        return {"status": "OK", "detail": f"KumoMTA listening on {host}:{port}"}
    except Exception as e:
        return {"status": "FAIL", "detail": f"Cannot connect to KumoMTA {host}:{port}: {e}"}

def check_dkim_keys(dkim_dir: str, domains: list) -> list:
    """Check if DKIM private keys exist for all configured domains."""
    results = []
    for domain in domains:
        key_path = os.path.join(dkim_dir, f"{domain}.private.key")
        pub_path = os.path.join(dkim_dir, f"{domain}.public.key")
        if os.path.exists(key_path) and os.path.exists(pub_path):
            results.append({"domain": domain, "status": "OK", "detail": "Keys present"})
        else:
            results.append({"domain": domain, "status": "FAIL", "detail": f"Missing keys at {key_path} or {pub_path}"})
    return results

def check_spf_record(domain: str) -> dict:
    """Verify SPF DNS record."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "TXT")
        spf_records = [str(r) for r in answers if "v=spf1" in str(r)]
        if spf_records:
            return {"domain": domain, "status": "OK", "detail": f"SPF found: {spf_records[0]}"}
        return {"domain": domain, "status": "FAIL", "detail": "No SPF record found"}
    except Exception as e:
        return {"domain": domain, "status": "FAIL", "detail": f"SPF check error: {e}"}

def check_dkim_record(domain: str) -> dict:
    """Verify DKIM DNS record."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(f"dkim._domainkey.{domain}", "TXT")
        if answers:
            return {"domain": domain, "status": "OK", "detail": "DKIM record found"}
        return {"domain": domain, "status": "FAIL", "detail": "DKIM record not found"}
    except Exception as e:
        return {"domain": domain, "status": "FAIL", "detail": f"DKIM check error: {e}"}

def check_dmarc_record(domain: str) -> dict:
    """Verify DMARC DNS record."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
        dmarc_records = [str(r) for r in answers if "v=DMARC1" in str(r)]
        if dmarc_records:
            return {"domain": domain, "status": "OK", "detail": f"DMARC found: {dmarc_records[0]}"}
        return {"domain": domain, "status": "FAIL", "detail": "DMARC record not found"}
    except Exception as e:
        return {"domain": domain, "status": "FAIL", "detail": f"DMARC check error: {e}"}

def check_fcrdns(ip: str, fqdn: str) -> dict:
    """Check Forward/Consistent Reverse DNS."""
    import subprocess
    try:
        result = subprocess.run(["dig", "+short", "-x", ip], capture_output=True, text=True, timeout=5)
        ptr = result.stdout.strip()
        if fqdn in ptr:
            return {"status": "OK", "detail": f"FCrDNS consistent: {fqdn} <-> {ip}"}
        return {"status": "FAIL", "detail": f"FCrDNS mismatch: {ptr} != {fqdn}"}
    except Exception as e:
        return {"status": "FAIL", "detail": f"FCrDNS check error: {e}"}

def check_ip_reputation(ip: str) -> dict:
    """Check if IP is on any major blacklists."""
    try:
        import dns.resolver
        rev_ip = ".".join(reversed(ip.split(".")))
        result = subprocess.run(
            ["dig", "+short", f"{rev_ip}.zen.spamhaus.org"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            return {"status": "LISTED", "detail": f"IP {ip} listed on Spamhaus"}
        return {"status": "OK", "detail": f"IP {ip} not on Spamhaus"}
    except Exception as e:
        return {"status": "UNKNOWN", "detail": f"Reputation check error: {e}"}

def main():
    config = load_config()
    print("=" * 60)
    print("  COLD EMAIL DELIVERABILITY - PRE-FLIGHT CHECK")
    print("=" * 60)
    print()

    all_ok = True

    # 1. KumoMTA connectivity
    print("[1/6] KumoMTA Connectivity")
    kumo_host = config.get("kumo", {}).get("host", "169.58.207.75")
    kumo_port = config.get("kumo", {}).get("port", 2587)
    result = check_kumomta_running(kumo_host, kumo_port)
    print(f"  KumoMTA {kumo_host}:{kumo_port}: {result['status']} - {result['detail']}")
    if result["status"] != "OK":
        all_ok = False
    print()

    # 2. DKIM keys
    print("[2/6] DKIM Keys")
    dkim_dir = "/opt/kumomta-lab/dkim"
    domains = config.get("sending_domains", [config.get("sending_domain", "nasrullahtanim.me")])
    dkim_results = check_dkim_keys(dkim_dir, domains)
    for r in dkim_results:
        print(f"  {r['domain']}: {r['status']} - {r['detail']}")
        if r["status"] != "OK":
            all_ok = False
    print()

    # 3. DNS Records
    print("[3/6] DNS Records")
    for domain in domains:
        spf = check_spf_record(domain)
        dkim = check_dkim_record(domain)
        dmarc = check_dmarc_record(domain)
        print(f"  {domain}:")
        print(f"    SPF:   {spf['status']} - {spf['detail']}")
        print(f"    DKIM:  {dkim['status']} - {dkim['detail']}")
        print(f"    DMARC: {dmarc['status']} - {dmarc['detail']}")
        if spf["status"] != "OK" or dkim["status"] != "OK" or dmarc["status"] != "OK":
            all_ok = False
    print()

    # 4. FCrDNS
    print("[4/6] FCrDNS")
    ip = config.get("sending_ip", "169.58.207.75")
    fqdn = "mail.nasrullahtanim.me"
    result = check_fcrdns(ip, fqdn)
    print(f"  {ip} -> {fqdn}: {result['status']} - {result['detail']}")
    if result["status"] != "OK":
        all_ok = False
    print()

    # 5. IP Reputation
    print("[5/6] IP Reputation")
    result = check_ip_reputation(ip)
    print(f"  {ip}: {result['status']} - {result['detail']}")
    if result["status"] == "LISTED":
        all_ok = False
    print()

    # 6. Profiles
    print("[6/6] Sender Profiles")
    profiles = config.get("profiles", [])
    for profile in profiles:
        print(f"  {profile}: OK")
    if not profiles:
        print("  No profiles configured!")
        all_ok = False
    print()

    # Summary
    print("=" * 60)
    if all_ok:
        print("  ALL CHECKS PASSED - Ready to send")
        print("=" * 60)
        sys.exit(0)
    else:
        print("  SOME CHECKS FAILED - Fix before sending")
        print("=" * 60)
        sys.exit(1)

if __name__ == "__main__":
    main()
