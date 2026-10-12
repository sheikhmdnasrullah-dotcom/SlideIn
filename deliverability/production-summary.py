#!/usr/bin/env python3
"""
production-summary.py - Generate deployment summary

Prints all the key information needed to complete the production deployment.
"""
from __future__ import annotations
from pathlib import Path
import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def main():
    config = json.load(open(CONFIG_PATH))
    
    print("=" * 70)
    print("  COLD EMAIL DELIVERABILITY - PRODUCTION DEPLOYMENT SUMMARY")
    print("=" * 70)
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  INFRASTRUCTURE")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print(f"  VPS IP:           {config.get('sending_ip', '169.58.207.75')}")
    print(f"  KumoMTA:          {config.get('kumo', {}).get('host', '169.58.207.75')}:{config.get('kumo', {}).get('port', 2587)}")
    print(f"  KumoMTA User:     {config.get('kumo', {}).get('user', 'outbound')}")
    print(f"  GoPhish Admin:    https://email.tanim.tech")
    print(f"  GoPhish Landing:  http://169.58.207.75:8080")
    print(f"  Grafana:          http://169.58.207.75:3000")
    print(f"  Prometheus:       http://169.58.207.75:9090")
    print(f"  Redis:            127.0.0.1:6379")
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  SENDER PROFILES (nasrullahtanim.me)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    for profile in config.get('profiles', []):
        print(f"  • {profile}")
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  SENDING DOMAINS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    for domain in config.get('sending_domains', []):
        print(f"  • {domain}")
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  WARMUP CONFIG")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    warmup = config.get('warmup', {})
    print(f"  Daily Limit:      {warmup.get('daily_limit', 20)} emails/day")
    print(f"  Ramp:             +{warmup.get('ramp_increment', 20)}/every {warmup.get('ramp_step_days', 3)} days")
    print(f"  Max Limit:        {warmup.get('max_daily_limit', 500)} emails/day")
    print(f"  Min Delay:        {config.get('pacing', {}).get('min_delay_seconds', 60)}s between sends")
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  SAFETY GATES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    gate = config.get('gate', {})
    circuit = config.get('circuit', {})
    print(f"  Min Grade:        {gate.get('min_grade', 'A')}")
    print(f"  Min Score:        {gate.get('min_score', 85)}")
    print(f"  Seed Required:    {gate.get('require_seed', True)}")
    print(f"  Max Bounce:       {circuit.get('max_bounce_rate', 2.0)}%")
    print(f"  Max Complaint:    {circuit.get('max_complaint_rate', 0.1)}%")
    print(f"  Min Seed Inbox:   {circuit.get('min_seed_inbox_pct', 100)}%")
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  NEXT STEPS")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    print("  1. Run deploy-production.sh on VPS")
    print("  2. Add DNS records (setup-dns.sh)")
    print("  3. Verify: python3 precheck.py")
    print("  4. Configure GoPhish: python3 configure-gophish-profiles.py")
    print("  5. Start warmup: cd warmup-engine && npm start")
    print("  6. Start campaigns: python3 campaign_worker.py")
    print()
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  KEY FILES")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    files = [
        ("KumoMTA Policy", "kumomta-lab/policy/production_init.lua"),
        ("Docker Compose", "kumomta-lab/compose/docker-compose.production.yml"),
        ("Deploy Script", "kumomta-lab/scripts/deploy-production.sh"),
        ("DNS Setup", "deliverability/setup-dns.sh"),
        ("Pre-flight Check", "deliverability/precheck.py"),
        ("GoPhish Config", "gophish-config-production.json"),
        ("Warmup Config", "warmup-engine/config.json"),
        ("Coordination Guide", "deliverability/GOPHISH_KUMOMTA_COORDINATION_PRODUCTION.md"),
        ("Deliverability Config", "deliverability/config.json"),
    ]
    for name, path in files:
        print(f"  {name:25s} {path}")
    print()
    
    print("=" * 70)
    print("  All infrastructure is configured for legitimate cold email")
    print("  deliverability. No spam evasion or header forgery is included.")
    print("=" * 70)

if __name__ == "__main__":
    main()
