#!/usr/bin/env python3
"""
monitor_placement.py - Periodic inbox-placement monitor across seed accounts.

For each configured seed it runs the deliverability rules gate, sends the
approved template via KumoMTA, then checks whether it landed INBOX or SPAM.
Prints a table + writes deliverability/.placement_log.csv.

Use to watch reputation over time (run 1-2x/day, not constantly). Sends to
YOUR OWN seed inboxes only.

Usage:
  python3 deliverability/monitor_placement.py --profile hello@nasrullahtanim.me
  python3 deliverability/monitor_placement.py --profile hello@nasrullahtanim.me --limit 3
"""
import sys, os, json, csv, time, argparse, email
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import inbox_pipeline as P
import rules_engine

LOG = os.path.join(os.path.dirname(__file__), ".placement_log.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="hello@nasrullahtanim.me")
    ap.add_argument("--template", default=os.path.join(os.path.dirname(__file__), "sample/approved_template.eml"))
    ap.add_argument("--unsub-mailto", default="unsubscribe@nasrullahtanim.me")
    ap.add_argument("--wait", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0, help="max seeds to test (0=all)")
    ap.add_argument("--force", action="store_true", help="send even if a rule FAILs")
    ap.add_argument("--transport", choices=["kumo", "sendgrid", "resend"], default="kumo",
                    help="transport to send through")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "config.json")))
    seeds = cfg["seed_accounts"]
    if args.limit:
        seeds = seeds[:args.limit]

    subject, plain, html = P.render_template(args.template, "seed@placeholder", args.unsub_mailto)
    domain = args.profile.split("@", 1)[1]
    msg = P.assurance.build_message(args.profile, "seed@placeholder", subject, plain, html, None, args.unsub_mailto)
    msg_str = msg.as_string()

    print("=== Rules Gate ===")
    results = rules_engine.run_all(msg, plain, html, args.profile, domain, eml_text=msg_str)
    fails = rules_engine.print_report(results)
    if fails and not args.force:
        print("ABORT: gate FAILED. Fix rules or use --force.")
        sys.exit(3)

    print(f"\n=== Placement monitor: {len(seeds)} seeds, profile {args.profile} ===")
    rows = []
    for s in seeds:
        to = s["email"]
        try:
            if args.transport == "sendgrid":
                sg_key = cfg.get("sendgrid", {}).get("api_key")
                _, sent_str = P.send_via_sendgrid(args.profile, to, msg_str, sg_key)
            elif args.transport == "resend":
                rs_key = cfg.get("resend", {}).get("api_key")
                _, sent_str = P.send_via_resend(args.profile, to, msg_str, rs_key)
            else:
                _, sent_str = P.send_via_kumo(args.profile, to, msg_str)
            place = P.verify_seed(s, msg["Message-ID"], wait=args.wait)
        except Exception as e:
            place = f"ERR:{e}"
        rows.append((to, place))
        print(f"  {to:35} -> {place}")
        time.sleep(2)

    inbox = sum(1 for _, p in rows if p == "INBOX")
    spam = sum(1 for _, p in rows if p == "SPAM")
    print(f"\n  INBOX {inbox}  SPAM {spam}  other {len(rows)-inbox-spam}")

    with open(LOG, "a", newline="") as f:
        w = csv.writer(f)
        if os.path.getsize(LOG) == 0:
            w.writerow(["ts", "profile", "seed", "placement"])
        for to, place in rows:
            w.writerow([time.strftime("%Y-%m-%d %H:%M"), args.profile, to, place])
    print(f"  logged -> {LOG}")


if __name__ == "__main__":
    main()
