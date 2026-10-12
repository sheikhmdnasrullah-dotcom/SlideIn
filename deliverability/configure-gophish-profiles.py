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

API_BASE = "http://169.58.207.75:8333/api"
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
    return {"Content-Type": "application/json"}

def configure_smtp_profile(profile: dict) -> bool:
    """Configure a GoPhish sending profile to use KumoMTA."""
    data = {
        "name": profile["name"],
        "from": profile["from_name"],
        "email": profile["email"],
        "host": "169.58.207.75",
        "port": 2587,
        "username": "outbound",
        "password": os.environ.get("KUMO_AUTH_PASS", "local-dev-password"),
        "use_tls": True,
        "headers": {},
        "ignore_tls": False,
        "trusted": True,
        "default_reply_to": profile["reply_to"],
    }
    try:
        req = urllib.request.Request(
            f"{API_BASE}/smtp",
            data=json.dumps(data).encode(),
            headers=get_headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            result = json.loads(resp.read().decode())
            print(f"  [OK] {profile['email']}: Configured (ID: {result.get('id', 'N/A')})")
            return True
    except urllib.error.HTTPError as e:
        # Profile might already exist - try PUT
        if e.code == 409 or e.code == 400:
            print(f"  [SKIP] {profile['email']}: May already exist")
        else:
            print(f"  [ERR] {profile['email']}: HTTP {e.code}")
        return False
    except Exception as e:
        print(f"  [ERR] {profile['email']}: {e}")
        return False

def main():
    print("=" * 60)
    print("  GoPhish Profile Configuration")
    print("  SMTP Relay: KumoMTA (169.58.207.75:2587)")
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
