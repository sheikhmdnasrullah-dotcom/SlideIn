#!/usr/bin/env python3
"""
configure-gophish-profiles.py - Configure GoPhish sending profiles via API

Configures all 3 sender profiles in GoPhish to use KumoMTA as the SMTP relay.
Each profile authenticates as 'outbound' and sends as a different nasrullahtanim.me address.
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

def main():
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
    for profile in PROFILES:
        if configure_smtp_profile(profile):
            success += 1
        time.sleep(0.5)

    print()
    print(f"Configured {success}/{len(PROFILES)} profiles")
    
    if success == len(PROFILES):
        print("\nAll profiles ready. GoPhish is now sending via KumoMTA.")
        print("Profiles:")
        for p in PROFILES:
            print(f"  - {p['email']} (as {p['from_name']})")
    else:
        print("\nSome profiles failed. Check GoPhish admin panel manually.")
        sys.exit(1)

if __name__ == "__main__":
    main()
