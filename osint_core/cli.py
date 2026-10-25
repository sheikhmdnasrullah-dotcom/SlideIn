#!/usr/bin/env python3
"""osint_core founder CLI — full control from the terminal, no dashboard needed.

Examples:
  python -m osint_core.cli enrich jane.doe@acme.com --sync
  python -m osint_core.cli bulk leads.txt --name "Series B fintech"
  python -m osint_core.cli watch <job_id>                # live event stream
  python -m osint_core.cli watch jane.doe@acme.com --lead
  python -m osint_core.cli queue                         # drafts awaiting decision
  python -m osint_core.cli approve jane.doe@acme.com --note "good fit"
  python -m osint_core.cli reject spam@evil.com
  python -m osint_core.cli result jane.doe@acme.com
  python -m osint_core.cli campaign <job_id>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings  # noqa: E402


def _out(obj) -> None:
    print(json.dumps(obj, indent=2, default=str)[:6000])


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _enrich(args) -> None:
    if args.sync:
        from app.core.pipeline import EnrichmentPipeline

        result = asyncio.run(EnrichmentPipeline().enrich(
            args.email, task_id="cli-sync"))
        _store(args.email, result.model_dump(mode="json"))
        _out({"status": "done", "lead": args.email,
              "draft_subjects": (result.agents.get("copywriter") or {}).get("subject_lines")})
    else:
        from app.workers.tasks import enrich_lead_task

        task = enrich_lead_task.apply_async(args=[args.email], queue="osint")
        _out({"status": "queued", "task_id": task.id})


def _bulk(args) -> None:
    from app.workers.tasks import enrich_bulk_task
    from app.workflows import engine as wf

    with open(args.file) as fh:
        emails = [line.strip() for line in fh if line.strip() and "@" in line]
    job_id = enrich_bulk_task.apply_async(args=[emails], queue="osint").get(timeout=15)
    if args.name:
        wf.create_campaign(args.name, job_id, len(emails))
        for e in emails:
            wf.init_lead(job_id, e)
    _out({"status": "queued", "job_id": job_id, "leads": len(emails)})


def _watch(args) -> None:
    """Live wire-schema event stream (works without the API server)."""
    import redis

    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    # single most-specific channel: publisher writes every envelope to each
    # scope channel, so one subscription is complete and never duplicated
    if args.lead or "@" in args.id:
        channels = [f"osint:events:lead:{args.id.lower()}"]
    else:
        channels = [f"osint:events:job:{args.id}"]
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(*channels)
    print(f"streaming {channels} — Ctrl-C to stop", file=sys.stderr)
    try:
        for msg in pubsub.listen():
            env = json.loads(msg["data"])
            line = (f"[{env['progress_percentage']:>5.1f}%] "
                    f"{env['active_framework']:<18} {env['lifecycle_status']}")
            if env.get("extracted_delta"):
                line += f"  +{json.dumps(env['extracted_delta'])[:100]}"
            if env.get("error_logs"):
                line += f"  !! {env['error_logs'][:160]}"
            print(line, flush=True)
    except KeyboardInterrupt:
        pass


def _jobs(_args) -> None:
    r = _redis()
    out = []
    for key in r.scan_iter("job:*", count=200):
        if ":lead:" in key:
            continue
        d = r.hgetall(key)
        d["job_id"] = key.split(":", 1)[1]
        out.append(d)
    _out({"jobs": out})


def _job(args) -> None:
    _out(_redis().hgetall(f"job:{args.job_id}") or {})


def _queue(_args) -> None:
    from app.workflows import engine as wf

    _out({"pending": wf.pending_queue()})


def _decide(args) -> None:
    from app.workflows import engine as wf

    _out(wf.decide(args.email, args.action, args.note or ""))


def _result(args) -> None:
    r = _redis()
    raw = r.get(f"result:{args.email}")
    if not raw:
        print("no result — enrich first", file=sys.stderr)
        sys.exit(1)
    result = json.loads(raw)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2, default=str)
        print(f"written to {args.out}")
    else:
        _out(result)


def _campaign(args) -> None:
    from app.workflows import engine as wf

    _out(wf.campaign_status(args.job_id))


def _store(email: str, payload: dict) -> None:
    r = _redis()
    pipe = r.pipeline()
    pipe.setex(f"result:{email}", 30 * 86400, json.dumps(payload))
    pipe.setex(f"dossier:{email}", 30 * 86400, json.dumps(payload["dossier"]))
    pipe.execute()


def main() -> None:
    p = argparse.ArgumentParser(prog="osint_core", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("enrich"); s.add_argument("email"); s.add_argument("--sync", action="store_true")
    s = sub.add_parser("bulk"); s.add_argument("file"); s.add_argument("--name")
    s = sub.add_parser("watch"); s.add_argument("id"); s.add_argument("--lead", action="store_true")
    sub.add_parser("jobs")
    s = sub.add_parser("job"); s.add_argument("job_id")
    sub.add_parser("queue")
    s = sub.add_parser("approve"); s.add_argument("email"); s.add_argument("--note", default="")
    s = sub.add_parser("reject"); s.add_argument("email"); s.add_argument("--note", default="")
    s = sub.add_parser("result"); s.add_argument("email"); s.add_argument("--out")
    s = sub.add_parser("campaign"); s.add_argument("job_id")

    args = p.parse_args()
    {"enrich": _enrich, "bulk": _bulk, "watch": _watch, "jobs": _jobs,
     "job": _job, "queue": _queue, "approve": lambda a: _decide(_ns(a, "approve")),
     "reject": lambda a: _decide(_ns(a, "reject")),
     "result": _result, "campaign": _campaign}[args.cmd](args)


def _ns(args, action):
    args.action = action
    return args


if __name__ == "__main__":
    main()
