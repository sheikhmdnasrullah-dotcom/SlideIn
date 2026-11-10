#!/usr/bin/env python3
"""Dry-run API acceptance for the durable onboarding/worker deployment.

Uses only the public API and Python's standard library. It never enables
approval or sending and expects the deployment to use dry-run transport.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request

BUSINESS_CONTEXT = """Business name: Northwind Cloud
Website: https://northwind.example
Industry: Cloud infrastructure
Business description: Northwind Cloud reduces infrastructure waste for SaaS teams.
Core value proposition: Cut cloud spend without manual rightsizing.
Products: Automated cloud cost audits and continuous rightsizing.
Ideal customer: SaaS companies with Kubernetes and growing cloud bills.
Geography: North America; Europe
Tone: Direct and evidence-led.
"""


def request(base: str, path: str, key: str, tenant: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {key}",
            "X-Slidein-Tenant": tenant,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} returned {exc.code}: {exc.read().decode()}") from exc


def wait_for(label: str, read, predicate, timeout: int = 90) -> dict:
    deadline = time.monotonic() + timeout
    latest = None
    while time.monotonic() < deadline:
        latest = read()
        if predicate(latest):
            return latest
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for {label}: {json.dumps(latest)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--tenant", required=True)
    args = parser.parse_args()
    base, key, tenant = args.base_url, args.api_key, args.tenant
    prefix = f"/v1/tenants/{tenant}"

    intake = request(base, f"{prefix}/setup/intake", key, tenant, {
        "sources": [{"type": "notes", "label": "acceptance-context", "text": BUSINESS_CONTEXT}],
    })
    job_id = intake["job"]["id"]
    run_id = intake["run"]["id"]
    setup_job = wait_for(
        "setup job completion",
        lambda: request(base, f"{prefix}/autopilot/jobs/{job_id}", key, tenant),
        lambda body: body["job"]["state"] in {"complete", "dead_letter", "cancelled"},
    )
    if setup_job["job"]["state"] != "complete":
        raise RuntimeError(f"Setup did not complete: {json.dumps(setup_job)}")

    setup_run = request(base, f"{prefix}/setup/runs/{run_id}", key, tenant)
    profile = request(base, f"{prefix}/profile", key, tenant)
    if setup_run["run"]["state"] != "complete" or not profile["offers"] or not profile["icps"]:
        raise RuntimeError("Canonical profile, offer, or ICP was not created")

    autopilot = wait_for(
        "automatic research tick",
        lambda: request(base, f"{prefix}/autopilot", key, tenant),
        lambda body: body.get("last_tick_at") is not None,
    )
    switches = autopilot.get("switches") or autopilot
    enabled = switches.get("enabled")
    auto_approve = switches.get("auto_approve")
    send_enabled = switches.get("send_enabled")
    if enabled is not True or auto_approve is not False or send_enabled is not False:
        raise RuntimeError(f"Unsafe or inactive autopilot switches: {json.dumps(autopilot)}")

    print(json.dumps({
        "status": "passed",
        "setup_job_id": job_id,
        "setup_run_id": run_id,
        "profile_created": True,
        "offers_created": len(profile["offers"]),
        "icps_created": len(profile["icps"]),
        "research_started_automatically": True,
        "auto_approve": auto_approve,
        "send_enabled": send_enabled,
    }, indent=2))


if __name__ == "__main__":
    main()
