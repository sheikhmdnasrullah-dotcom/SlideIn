#!/usr/bin/env python3
"""
configure-gophish-profiles.py - Configure GoPhish sending profiles via API

Configures all 9 sender profiles in GoPhish to use KumoMTA as the SMTP relay.
Each profile authenticates as 'outbound' and sends as a different address.
tanim.social / tanim.tech mailboxes stay on Zoho (MX + zmail DKIM untouched);
these profiles only add the VPS as an additional authorized sender (SPF
include + dkim-selector signing). Idempotent: reruns report 409 as done.
"""
from __future__ import annotations
import json
import sys
import os
import time
import urllib.request
import urllib.error
import urllib.parse

API_BASE = os.environ.get("GOPHISH_API_URL", "http://127.0.0.1:8333/api")
KUMO_SMTP_HOST = os.environ.get("KUMO_SMTP_HOST", "127.0.0.1")
KUMO_SMTP_PORT = int(os.environ.get("KUMO_SMTP_PORT", "2587"))
TIMEOUT = 10

PROFILES = [
    {
        "name": "hello@nasrullahtanim.me",
        "email": "hello@nasrullahtanim.me",
        "from_name": "Nasrullah Tanim",
        "reply_to": "hello@nasrullahtanim.me",
    },
    {
        "name": "talk@nasrullahtanim.me",
        "email": "talk@nasrullahtanim.me",
        "from_name": "Nasrullah Tanim",
        "reply_to": "talk@nasrullahtanim.me",
    },
    {
        "name": "connect@nasrullahtanim.me",
        "email": "connect@nasrullahtanim.me",
        "from_name": "Nasrullah Tanim",
        "reply_to": "connect@nasrullahtanim.me",
    },
    {
        "name": "hello@tanim.social",
        "email": "hello@tanim.social",
        "from_name": "Nasrullah Tanim",
        "reply_to": "hello@tanim.social",
    },
    {
        "name": "talk@tanim.social",
        "email": "talk@tanim.social",
        "from_name": "Nasrullah Tanim",
        "reply_to": "talk@tanim.social",
    },
    {
        "name": "connect@tanim.social",
        "email": "connect@tanim.social",
        "from_name": "Nasrullah Tanim",
        "reply_to": "connect@tanim.social",
    },
    {
        "name": "hello@tanim.tech",
        "email": "hello@tanim.tech",
        "from_name": "Nasrullah Tanim",
        "reply_to": "hello@tanim.tech",
    },
    {
        "name": "talk@tanim.tech",
        "email": "talk@tanim.tech",
        "from_name": "Nasrullah Tanim",
        "reply_to": "talk@tanim.tech",
    },
    {
        "name": "connect@tanim.tech",
        "email": "connect@tanim.tech",
        "from_name": "Nasrullah Tanim",
        "reply_to": "connect@tanim.tech",
    },
]

def get_headers():
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("GOPHISH_API_KEY", "")
    if api_key:
        headers["Authorization"] = api_key
    return headers

def configure_smtp_profile(profile: dict) -> bool:
    """Configure a GoPhish sending profile to use KumoMTA."""
    # Field names must match models/smtp.go exactly: from_address is a bare
    # email, host carries host:port, headers is a list. KumoMTA presents a
    # self-signed cert on the loopback relay, hence ignore_cert_errors.
    data = {
        "name": profile["name"],
        "from_address": profile["email"],
        "host": f"{KUMO_SMTP_HOST}:{KUMO_SMTP_PORT}",
        "username": "outbound",
        "password": os.environ["KUMO_AUTH_PASS"],
        "ignore_cert_errors": True,
        "headers": [],
    }
    try:
        req = urllib.request.Request(
            f"{API_BASE}/smtp/",
            data=json.dumps(data).encode(),
            headers=get_headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode())
            print(f"  [OK] {profile['email']}: Configured (ID: {result.get('id', 'N/A')})")
            return True
    except urllib.error.HTTPError as e:
        if e.code == 409:
            # Name already in use: idempotent reruns treat this as success.
            print(f"  [OK] {profile['email']}: Already configured")
            return True
        if e.code == 400:
            print(f"  [SKIP] {profile['email']}: Rejected (check fields)")
        else:
            print(f"  [ERR] {profile['email']}: HTTP {e.code}")
        return False
    except Exception as e:
        print(f"  [ERR] {profile['email']}: {e}")
        return False

def load_profiles() -> list:
    """Profile list: PROFILES_JSON env (installer) overrides the builtin list."""
    override = os.environ.get("PROFILES_JSON", "")
    if override:
        profiles = json.loads(override)
        assert isinstance(profiles, list) and profiles, "PROFILES_JSON must be a non-empty list"
        for p in profiles:
            assert p.get("name") and p.get("email"), f"profile needs name+email: {p}"
            p.setdefault("from_name", "")
            p.setdefault("reply_to", p["email"])
        return profiles
    return PROFILES


def main():
    profiles = load_profiles()
    if not os.environ.get("GOPHISH_API_KEY"):
        print("ERROR: GOPHISH_API_KEY is not set (refusing unauthenticated API calls).")
        print("Read it from the GoPhish host: cat /root/gophish/api_key.txt")
        sys.exit(2)
    if not os.environ.get("KUMO_AUTH_PASS"):
        print("ERROR: KUMO_AUTH_PASS is not set (refusing to configure a broken relay password).")
        sys.exit(2)
    print("=" * 60)
    print("  GoPhish Profile Configuration")
    print(f"  API: {API_BASE}")
    print(f"  SMTP Relay: KumoMTA ({KUMO_SMTP_HOST}:{KUMO_SMTP_PORT})")
    print("=" * 60)
    print()

    success = 0
    for profile in profiles:
        if configure_smtp_profile(profile):
            success += 1
        time.sleep(0.5)

    print()
    print(f"Configured {success}/{len(profiles)} profiles")

    if success == len(profiles):
        print("\nAll profiles ready. GoPhish is now sending via KumoMTA.")
        print("Profiles:")
        for p in profiles:
            print(f"  - {p['email']} (as {p['from_name']})")
    else:
        print("\nSome profiles failed. Check GoPhish admin panel manually.")
        sys.exit(1)

if __name__ == "__main__":
    main()
