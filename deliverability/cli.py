#!/usr/bin/env python3
"""Deliverability CLI — single entry point for all email-safety operations.

Usage:
  python3 cli.py validate-dns [domain] [ip]
  python3 cli.py analyze <file.eml> [happydeliver_url]
  python3 cli.py seed-test <file.eml>
  python3 cli.py gate-check <file.eml>
  python3 cli.py placement-risk <file.eml>
  python3 cli.py monitor
  python3 cli.py status
  python3 cli.py pause [reason]
  python3 cli.py resume
  python3 cli.py send <file.eml> <recipient> [sender]
  python3 cli.py next-profile          # next approved sender (round-robin)
  # --- lab / experimental containment (hard recipient allowlist) ---
  python3 cli.py lab-status             # show lab mode + allowlist
  python3 cli.py lab-enable             # enable lab mode (fail-closed until allowlist set)
  python3 cli.py lab-disable            # disable lab mode (normal behavior)
  python3 cli.py lab-add <email>        # add recipient to allowlist
  python3 cli.py lab-remove <email>     # remove recipient from allowlist
  python3 cli.py lab-list               # list allowlist
  python3 cli.py init           # write config.example.json if missing
  python3 cli.py suppress <email> [reason]
  python3 cli.py unsuppress <email>
  python3 cli.py suppressed
  python3 cli.py parse-bounce <file>
  python3 cli.py warmup-status
  python3 cli.py precheck
  python3 cli.py send-log [limit]
  # --- transactional email ---
  python3 cli.py tx-send --to <email> --subject <subject> --text <text> --html <html> [--from-addr <addr>] [--from-name <name>]
  python3 cli.py tx-notification --to <email> --title <title> --message <msg> [--action-url <url>] [--action-text <text>]
  python3 cli.py tx-confirmation --to <email> --title <title> --message <msg> --url <url> [--code <code>]
  python3 cli.py tx-receipt --to <email> --id <id> --amount <amount> --items <json>
  python3 cli.py tx-alert --to <email> --type <type> --title <title> --message <msg> [--severity <level>] [--action-url <url>]
  python3 cli.py tx-optimize --to <email> --subject <subject> --text <text> --html <html>
  python3 cli.py tx-stats [--domain <domain>] [--days <days>]
  python3 cli.py tx-events [--limit <limit>]
  python3 cli.py delivery-stats [--domain <domain>] [--days <days>]
  python3 cli.py delivery-events [--limit <limit>]
  python3 cli.py show-key [workspace]     # print workspace API key (once, keep secret)
  python3 cli.py rotate-key [workspace]   # replace key; old key stops working

All safety decisions flow through EMAIL_SENDING_POLICY.md. Do not bypass.
"""
from __future__ import annotations

import email
from email import policy
from datetime import datetime
import json
import os
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from core import state as st
from core import dns_checks
from core import analyzer
from core import seed_tester
from core import gate as gate_mod
from core import circuit_breaker as cb_mod
from core import pipeline as pipe
from core import monitor as mon
from core import reputation as rep
from core import profiles as profile_mod
from core.repository import SlideInRepository

CONFIG_PATH = os.path.join(HERE, "config.json")
STATE_PATH = os.path.join(HERE, "deliverability_state.db")


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        print("config.json missing — run `python3 cli.py init`", file=sys.stderr)
        sys.exit(2)
    return json.load(open(CONFIG_PATH))


def build_objects(cfg: dict):
    store = st.Store(STATE_PATH)
    gate = gate_mod.Gate(store, gate_mod.GateConfig(
        min_grade=cfg.get("gate", {}).get("min_grade", "B"),
        validity_window_hours=cfg.get("gate", {}).get("validity_window_hours", 24),
        require_seed=cfg.get("gate", {}).get("require_seed", False),
    ))
    breaker = cb_mod.CircuitBreaker(store, cb_mod.BreakerConfig(
        min_seed_inbox_pct=cfg.get("circuit", {}).get("min_seed_inbox_pct", 100),
        max_bounce_rate=cfg.get("circuit", {}).get("max_bounce_rate", 2.0),
        max_complaint_rate=cfg.get("circuit", {}).get("max_complaint_rate", 0.1),
        min_analyzer_grade=cfg.get("circuit", {}).get("min_analyzer_grade", "B"),
    ))
    return store, gate, breaker


def analyzer_fn(eml_bytes):
    url = load_config().get("happydeliver_url")
    return analyzer.analyze(eml_bytes, url)


def seed_runner_factory(cfg):
    raw_accounts = cfg.get("seed_accounts", [])
    accounts = [seed_tester.SeedAccount.from_dict(a) for a in raw_accounts if isinstance(a, dict)]
    smtp = cfg.get("kumo", {}) if cfg.get("transport") == "kumo" else cfg.get("smtp", {})

    def runner(eml_bytes):
        if not accounts:
            return []
        return seed_tester.run_seed_test(
            smtp, accounts, eml_bytes,
            inter_send_delay=cfg.get("seed_test", {}).get("inter_send_delay_seconds", 10),
        )
    return runner


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    cfg = load_config() if os.path.exists(CONFIG_PATH) else {}
    store, gate, breaker = build_objects(cfg)

    if cmd == "init":
        if not os.path.exists(CONFIG_PATH):
            import shutil
            shutil.copy(os.path.join(HERE, "config.example.json"), CONFIG_PATH)
            print(f"Wrote {CONFIG_PATH} from example. Fill in secrets.")
        else:
            print("config.json already exists.")
        return

    if cmd == "show-key":
        repo = SlideInRepository(STATE_PATH)
        ws = repo.get_workspace(argv[2] if len(argv) > 2 else "default")
        if ws is None:
            print("unknown workspace", file=sys.stderr)
            return
        print(ws.api_key)
        return

    if cmd == "rotate-key":
        repo = SlideInRepository(STATE_PATH)
        try:
            new_key = repo.rotate_workspace_key(argv[2] if len(argv) > 2 else "default")
        except KeyError as e:
            print(e, file=sys.stderr)
            return
        print(new_key)
        print("Old key is now invalid. Update SLIDEIN_API_KEY and clients.",
              file=sys.stderr)
        return

    if cmd == "validate-dns":
        domain = argv[2] if len(argv) > 2 else cfg.get("sending_domain", "tanim.tech")
        ip = argv[3] if len(argv) > 3 else cfg.get("sending_ip")
        subs = cfg.get("sending_subdomains", [])
        rep = dns_checks.audit_domain(domain, ip, cfg.get("dkim_selectors"), subs)
        for c in rep.checks:
            print(f"{c.status:5} {c.name}: {c.detail}")
        bl = dns_checks.audit_blacklists(ip) if ip else []
        for c in bl:
            print(f"{c.status:5} {c.name}: {c.detail}")
        print("\nISSUES:", "; ".join(rep.issues) or "none")
        return

    if cmd == "analyze":
        eml = open(argv[2], "rb").read()
        url = argv[3] if len(argv) > 3 else cfg.get("happydeliver_url")
        a = analyzer.analyze(eml, url)
        print(json.dumps(a.to_dict(), indent=2, default=str))
        return

    if cmd == "seed-test":
        eml = open(argv[2], "rb").read()
        runner = seed_runner_factory(cfg)
        results = runner(eml)
        for r in results:
            print(f"{r.provider.upper():10} {r.folder:12} {'PASS' if r.passed else 'FAIL'}")
        print("OVERALL:", "PASS" if seed_tester.overall_pass(results) else "FAIL")
        store.record_seed_results(f"cli-{int(time.time())}", [r.to_dict() for r in results])
        return

    if cmd == "gate-check":
        eml = open(argv[2], "rb").read()
        runner = seed_runner_factory(cfg)
        decision = gate.evaluate(eml, analyzer_fn, runner)
        print(json.dumps(decision, indent=2, default=str))
        print("\nGATE:", "APPROVED" if decision["approved"] else "BLOCKED")
        return

    if cmd == "monitor":
        runner = seed_runner_factory(cfg)
        tick = mon.run_tick(
            {**cfg, "_current_eml": None}, store, gate, breaker, runner,
            analyzer_fn,
            dns_audit_fn=lambda c: dns_checks.audit_domain(
                c.get("sending_domain", "tanim.tech"), c.get("sending_ip"),
                c.get("dkim_selectors"), c.get("sending_subdomains", [])).issues,
            reputation_fn=lambda c: rep.load_external_reputation_json(
                c.get("reputation_json_path", "")),
        )
        print(json.dumps(tick, indent=2, default=str))
        return

    if cmd == "status":
        c = store.get_circuit()
        camp = store.latest_campaign("cold-outreach")
        g = store.latest_gate_decision()
        print("CIRCUIT:", c["status"], "-", c["reason"])
        print("CAMPAIGN:", (camp or {}).get("status"), "-", (camp or {}).get("paused_reason"))
        print("LAST GATE:", (g or {}).get("approved"), (g or {}).get("analyzer_grade"),
              (g or {}).get("reason"))
        return

    if cmd == "pause":
        reason = argv[2] if len(argv) > 2 else "manual pause"
        breaker._trip(reason, {})  # type: ignore
        print("PAUSED:", reason)
        return

    if cmd == "resume":
        ok = breaker.resume_after_validation(True, {})
        print("RESUMED" if ok else "RESUME DENIED (validation required)")
        return

    if cmd == "send":
        eml = open(argv[2], "rb").read()
        recipient = argv[3]
        sender = argv[4] if len(argv) > 4 else None
        try:
            res = pipe.send_via_pipeline(
                recipient, eml, config=cfg, store=store, gate=gate, breaker=breaker,
                sender=sender)
            print(res)
        except pipe.BlockedSend as e:
            print("BLOCKED:", e)
            sys.exit(1)
        return

    if cmd == "next-profile":
        # Round-robin helper for batching: prints the next approved sender to
        # render the .eml From/Reply-To with. Never sends anything.
        chosen = profile_mod.rotate_sender(cfg, store)
        if not chosen:
            print("NO PROFILES CONFIGURED (set config.json -> profiles)", file=sys.stderr)
            sys.exit(2)
        print(chosen)
        return

    if cmd == "suppress":
        recipient = argv[2] if len(argv) > 2 else ""
        reason = argv[3] if len(argv) > 3 else "manual"
        if not recipient:
            print("Usage: suppress <recipient> [reason]", file=sys.stderr)
            sys.exit(2)
        store.suppress(recipient, reason)
        print(f"Suppressed: {recipient} ({reason})")
        return

    if cmd == "unsuppress":
        recipient = argv[2] if len(argv) > 2 else ""
        if not recipient:
            print("Usage: unsuppress <recipient>", file=sys.stderr)
            sys.exit(2)
        store.unsuppress(recipient)
        print(f"Unsuppressed: {recipient}")
        return

    if cmd == "suppressed":
        recips = store.suppressed_recipients()
        for r in recips:
            print(r)
        return

    if cmd == "parse-bounce":
        path = argv[2] if len(argv) > 2 else ""
        if not path:
            print("Usage: parse-bounce <bounce.eml>", file=sys.stderr)
            sys.exit(2)
        data = open(path, "rb").read()
        from core import bounce_parser
        res = bounce_parser.parse_bounce(data)
        print(json.dumps({
            "recipient": res.recipient,
            "status": res.status,
            "dsn_code": res.dsn_code,
            "diagnostic": res.diagnostic,
            "should_suppress": bounce_parser.should_suppress(res),
        }, indent=2))
        return

    if cmd == "warmup-status":
        domain = cfg.get("sending_domain", "nasrullahtanim.me")
        from core import warmup
        w = warmup.WarmupTracker(store.conn)
        for d in cfg.get("sending_domains", [domain]):
            w.initialize_domain(d)
            print(json.dumps(w.status(d), indent=2))
        return

    if cmd == "send-log":
        limit = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 20
        events = store.recent_send_events(limit=limit)
        for e in events:
            print(json.dumps(e, default=str))
        return

    if cmd == "precheck":
        domain = cfg.get("sending_domain", "nasrullahtanim.me")
        ip = cfg.get("sending_ip")
        result = {"domain": domain, "ip": ip, "checks": {}}

        dns_audit = dns_checks.audit_domain(domain, ip, cfg.get("dkim_selectors"), cfg.get("sending_subdomains", []))
        result["checks"]["dns"] = {
            "issues": dns_audit.issues,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in dns_audit.checks],
        }

        if ip:
            bl = dns_checks.audit_blacklists(ip)
            result["checks"]["blacklist"] = [{"name": c.name, "status": c.status, "detail": c.detail} for c in bl]

        from core import warmup
        w = warmup.WarmupTracker(store.conn)
        for d in cfg.get("sending_domains", [domain]):
            w.initialize_domain(d)
            result["checks"].setdefault("warmup", {})[d] = w.status(d)

        result["checks"]["circuit"] = {
            "status": store.get_circuit()["status"],
            "reason": store.get_circuit()["reason"],
        }

        result["checks"]["suppression"] = {
            "count": len(store.suppressed_recipients()),
            "recipients": store.suppressed_recipients()[:10],
        }

        print(json.dumps(result, indent=2, default=str))
        return

    if cmd == "preflight-check":
        path = argv[2] if len(argv) > 2 else ""
        if not path:
            print("Usage: preflight-check <file.eml>", file=sys.stderr)
            sys.exit(2)
        from preflight_verifier import check_seed_placement_and_fetch_headers, send_via_kumomta
        data = open(path, "rb").read()
        parsed = email.message_from_bytes(data, policy=policy.default)
        msg_id = parsed.get("Message-ID", f"<{uuid.uuid4().hex}@nasrullahtanim.me>")
        from_addr = parsed.get("From", "hello@nasrullahtanim.me")
        if "<" in from_addr:
            from_addr = from_addr.split("<")[-1].rstrip(">")
        
        seeds = [s for s in cfg.get("seed_accounts", []) if not s.get("password", "").startswith("FILL_IN")]
        if not seeds:
            print("❌ Error: No configured seed accounts found.", file=sys.stderr)
            sys.exit(1)
        seed = seeds[0]
        print(f"🚀 Sending preflight test to {seed['email']}...")
        send_via_kumomta(cfg, from_addr, seed["email"], data)
        folder, raw_source, headers = check_seed_placement_and_fetch_headers(seed, msg_id)
        print(f"📬 Result: [{folder}]")
        if headers:
            print("Auth Results:", headers.get("Authentication-Results"))
        return

    # --- Transactional Email Commands ---
    if cmd == "tx-send":
        import argparse
        parser = argparse.ArgumentParser(description="Send transactional email")
        parser.add_argument("--to", required=True)
        parser.add_argument("--subject", required=True)
        parser.add_argument("--text", required=True)
        parser.add_argument("--html", required=True)
        parser.add_argument("--from-addr", default="")
        parser.add_argument("--from-name", default="")
        parser.add_argument("--reply-to", default="")
        args = parser.parse_args(argv[2:])
        
        from core.transactional import TransactionalEmail, build_transactional_eml, optimize_content_for_deliverability
        
        from_addr = args.from_addr or cfg.get("profiles", ["hello@nasrullahtanim.me"])[0]
        from_name = args.from_name or from_addr.split("@")[0].title()
        
        # Optimize content
        subject, body_text, body_html, warnings = optimize_content_for_deliverability(
            args.subject, args.text, args.html, from_addr.split("@")[1] if "@" in from_addr else ""
        )
        for w in warnings:
            print(f"Warning: {w}")
        
        # Build email
        tx_email = TransactionalEmail(
            to_addr=args.to,
            from_name=from_name,
            from_addr=from_addr,
            reply_to=args.reply_to or from_addr,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
        )
        
        eml_bytes = build_transactional_eml(tx_email)
        
        # Analyze
        a = analyzer.analyze(eml_bytes, cfg.get("happydeliver_url"))
        print(f"Grade: {a.grade} (score: {a.score})")
        for f in a.findings:
            print(f"  - {f}")
        
        # Send via pipeline
        try:
            result = pipe.send_via_pipeline(
                args.to, eml_bytes, config=cfg, store=store, gate=gate, breaker=breaker
            )
            print(f"Sent: {result}")
        except pipe.BlockedSend as e:
            print(f"BLOCKED: {e}")
            sys.exit(1)
        return
    
    if cmd == "tx-notification":
        import argparse
        parser = argparse.ArgumentParser(description="Send notification email")
        parser.add_argument("--to", required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--message", required=True)
        parser.add_argument("--action-url", default="")
        parser.add_argument("--action-text", default="View Details")
        parser.add_argument("--from-addr", default="")
        parser.add_argument("--from-name", default="")
        args = parser.parse_args(argv[2:])
        
        from core.transactional import build_notification_email, build_transactional_eml, optimize_content_for_deliverability
        
        from_addr = args.from_addr or cfg.get("profiles", ["hello@nasrullahtanim.me"])[0]
        from_name = args.from_name or from_addr.split("@")[0].title()
        
        tx_email = build_notification_email(
            to_addr=args.to,
            from_name=from_name,
            from_addr=from_addr,
            title=args.title,
            message=args.message,
            action_url=args.action_url,
            action_text=args.action_text,
        )
        
        # Optimize
        tx_email.subject, tx_email.body_text, tx_email.body_html, warnings = optimize_content_for_deliverability(
            tx_email.subject, tx_email.body_text, tx_email.body_html, from_addr.split("@")[1] if "@" in from_addr else ""
        )
        for w in warnings:
            print(f"Warning: {w}")
        
        eml_bytes = build_transactional_eml(tx_email)
        
        # Analyze
        a = analyzer.analyze(eml_bytes, cfg.get("happydeliver_url"))
        print(f"Grade: {a.grade} (score: {a.score})")
        
        # Send
        try:
            result = pipe.send_via_pipeline(
                args.to, eml_bytes, config=cfg, store=store, gate=gate, breaker=breaker
            )
            print(f"Sent: {result}")
        except pipe.BlockedSend as e:
            print(f"BLOCKED: {e}")
            sys.exit(1)
        return
    
    if cmd == "tx-confirmation":
        import argparse
        parser = argparse.ArgumentParser(description="Send confirmation email")
        parser.add_argument("--to", required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--message", required=True)
        parser.add_argument("--url", required=True)
        parser.add_argument("--code", default="")
        parser.add_argument("--expiry", type=int, default=30)
        parser.add_argument("--from-addr", default="")
        parser.add_argument("--from-name", default="")
        args = parser.parse_args(argv[2:])
        
        from core.transactional import build_confirmation_email, build_transactional_eml, optimize_content_for_deliverability
        
        from_addr = args.from_addr or cfg.get("profiles", ["hello@nasrullahtanim.me"])[0]
        from_name = args.from_name or from_addr.split("@")[0].title()
        
        tx_email = build_confirmation_email(
            to_addr=args.to,
            from_name=from_name,
            from_addr=from_addr,
            title=args.title,
            message=args.message,
            confirmation_url=args.url,
            code=args.code,
            expiry_minutes=args.expiry,
        )
        
        # Optimize
        tx_email.subject, tx_email.body_text, tx_email.body_html, warnings = optimize_content_for_deliverability(
            tx_email.subject, tx_email.body_text, tx_email.body_html, from_addr.split("@")[1] if "@" in from_addr else ""
        )
        for w in warnings:
            print(f"Warning: {w}")
        
        eml_bytes = build_transactional_eml(tx_email)
        
        # Analyze
        a = analyzer.analyze(eml_bytes, cfg.get("happydeliver_url"))
        print(f"Grade: {a.grade} (score: {a.score})")
        
        # Send
        try:
            result = pipe.send_via_pipeline(
                args.to, eml_bytes, config=cfg, store=store, gate=gate, breaker=breaker
            )
            print(f"Sent: {result}")
        except pipe.BlockedSend as e:
            print(f"BLOCKED: {e}")
            sys.exit(1)
        return
    
    if cmd == "tx-receipt":
        import argparse
        parser = argparse.ArgumentParser(description="Send receipt email")
        parser.add_argument("--to", required=True)
        parser.add_argument("--id", required=True)
        parser.add_argument("--amount", required=True)
        parser.add_argument("--items", required=True, help="JSON array of items")
        parser.add_argument("--footer", default="")
        parser.add_argument("--from-addr", default="")
        parser.add_argument("--from-name", default="")
        args = parser.parse_args(argv[2:])
        
        from core.transactional import build_receipt_email, build_transactional_eml, optimize_content_for_deliverability
        
        from_addr = args.from_addr or cfg.get("profiles", ["hello@nasrullahtanim.me"])[0]
        from_name = args.from_name or from_addr.split("@")[0].title()
        
        items = json.loads(args.items)
        
        tx_email = build_receipt_email(
            to_addr=args.to,
            from_name=from_name,
            from_addr=from_addr,
            receipt_id=args.id,
            amount=args.amount,
            items=items,
            footer_text=args.footer,
        )
        
        # Optimize
        tx_email.subject, tx_email.body_text, tx_email.body_html, warnings = optimize_content_for_deliverability(
            tx_email.subject, tx_email.body_text, tx_email.body_html, from_addr.split("@")[1] if "@" in from_addr else ""
        )
        for w in warnings:
            print(f"Warning: {w}")
        
        eml_bytes = build_transactional_eml(tx_email)
        
        # Analyze
        a = analyzer.analyze(eml_bytes, cfg.get("happydeliver_url"))
        print(f"Grade: {a.grade} (score: {a.score})")
        
        # Send
        try:
            result = pipe.send_via_pipeline(
                args.to, eml_bytes, config=cfg, store=store, gate=gate, breaker=breaker
            )
            print(f"Sent: {result}")
        except pipe.BlockedSend as e:
            print(f"BLOCKED: {e}")
            sys.exit(1)
        return
    
    if cmd == "tx-alert":
        import argparse
        parser = argparse.ArgumentParser(description="Send alert email")
        parser.add_argument("--to", required=True)
        parser.add_argument("--type", required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--message", required=True)
        parser.add_argument("--severity", default="info", choices=["critical", "warning", "info"])
        parser.add_argument("--action-url", default="")
        parser.add_argument("--from-addr", default="")
        parser.add_argument("--from-name", default="")
        args = parser.parse_args(argv[2:])
        
        from core.transactional import build_alert_email, build_transactional_eml, optimize_content_for_deliverability
        
        from_addr = args.from_addr or cfg.get("profiles", ["hello@nasrullahtanim.me"])[0]
        from_name = args.from_name or from_addr.split("@")[0].title()
        
        tx_email = build_alert_email(
            to_addr=args.to,
            from_name=from_name,
            from_addr=from_addr,
            alert_type=args.type,
            title=args.title,
            message=args.message,
            severity=args.severity,
            action_url=args.action_url,
        )
        
        # Optimize
        tx_email.subject, tx_email.body_text, tx_email.body_html, warnings = optimize_content_for_deliverability(
            tx_email.subject, tx_email.body_text, tx_email.body_html, from_addr.split("@")[1] if "@" in from_addr else ""
        )
        for w in warnings:
            print(f"Warning: {w}")
        
        eml_bytes = build_transactional_eml(tx_email)
        
        # Analyze
        a = analyzer.analyze(eml_bytes, cfg.get("happydeliver_url"))
        print(f"Grade: {a.grade} (score: {a.score})")
        
        # Send
        try:
            result = pipe.send_via_pipeline(
                args.to, eml_bytes, config=cfg, store=store, gate=gate, breaker=breaker
            )
            print(f"Sent: {result}")
        except pipe.BlockedSend as e:
            print(f"BLOCKED: {e}")
            sys.exit(1)
        return
    
    if cmd == "tx-optimize":
        import argparse
        parser = argparse.ArgumentParser(description="Optimize email content for deliverability")
        parser.add_argument("--to", required=True)
        parser.add_argument("--subject", required=True)
        parser.add_argument("--text", required=True)
        parser.add_argument("--html", required=True)
        args = parser.parse_args(argv[2:])
        
        from core.transactional import optimize_content_for_deliverability
        
        from_domain = cfg.get("sending_domain", "nasrullahtanim.me")
        subject, body_text, body_html, warnings = optimize_content_for_deliverability(
            args.subject, args.text, args.html, from_domain
        )
        
        print("=== Optimized Content ===")
        print(f"Subject: {subject}")
        print(f"\nPlain Text:\n{body_text}")
        print(f"\nHTML:\n{body_html}")
        if warnings:
            print(f"\nWarnings:")
            for w in warnings:
                print(f"  - {w}")
        return
    
    if cmd == "tx-stats":
        import argparse
        parser = argparse.ArgumentParser(description="View transactional email statistics")
        parser.add_argument("--domain", default="")
        parser.add_argument("--days", type=int, default=30)
        args = parser.parse_args(argv[2:])
        
        from core.webhook import WebhookProcessor
        
        processor = WebhookProcessor(os.path.join(HERE, "deliverability_state.db"))
        stats = processor.get_stats(args.domain, args.days)
        processor.close()
        
        print(json.dumps(stats, indent=2, default=str))
        return
    
    if cmd == "tx-events":
        import argparse
        parser = argparse.ArgumentParser(description="View recent transactional email events")
        parser.add_argument("--limit", type=int, default=100)
        args = parser.parse_args(argv[2:])
        
        from core.webhook import WebhookProcessor
        
        processor = WebhookProcessor(os.path.join(HERE, "deliverability_state.db"))
        events = processor.get_recent_events(args.limit)
        processor.close()
        
        for e in events:
            print(json.dumps(e, default=str))
        return
    
    if cmd == "delivery-stats":
        import argparse
        parser = argparse.ArgumentParser(description="View delivery statistics")
        parser.add_argument("--domain", default="")
        parser.add_argument("--days", type=int, default=30)
        args = parser.parse_args(argv[2:])
        
        from core.webhook import WebhookProcessor
        
        processor = WebhookProcessor(os.path.join(HERE, "deliverability_state.db"))
        stats = processor.get_stats(args.domain, args.days)
        processor.close()
        
        print(f"Domain: {args.domain or 'all'}")
        print(f"Period: {args.days} days")
        print(f"\nTotal Sent: {stats['total_sent']}")
        print(f"Total Delivered: {stats['total_delivered']}")
        print(f"Total Bounces: {stats['total_bounces']}")
        print(f"Total Complaints: {stats['total_complaints']}")
        print(f"\nDelivery Rate: {stats['delivery_rate']:.1%}")
        print(f"Bounce Rate: {stats['bounce_rate']:.1%}")
        print(f"Complaint Rate: {stats['complaint_rate']:.2%}")
        print(f"Open Rate: {stats['open_rate']:.1%}")
        print(f"Click Rate: {stats['click_rate']:.1%}")
        return
    
    if cmd == "delivery-events":
        import argparse
        parser = argparse.ArgumentParser(description="View recent delivery events")
        parser.add_argument("--limit", type=int, default=100)
        args = parser.parse_args(argv[2:])
        
        from core.webhook import WebhookProcessor
        
        processor = WebhookProcessor(os.path.join(HERE, "deliverability_state.db"))
        events = processor.get_recent_events(args.limit)
        processor.close()
        
        for e in events:
            ts = datetime.fromtimestamp(e["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"{ts} [{e['event_type']}] {e['recipient']} - {e['status']}")
        return

    print(__doc__)


if __name__ == "__main__":
    main(sys.argv)

