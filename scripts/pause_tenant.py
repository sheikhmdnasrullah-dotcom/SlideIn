#!/usr/bin/env python3
"""Slidein Tenant Pause / Resume CLI.

Allows an operator to immediately pause or resume outreach for a specific
tenant, or trip/reset the deliverability circuit breaker.

Usage:
    python3 scripts/pause_tenant.py --tenant-id ten_beacon_dental --pause --reason "Client requested pause"
    python3 scripts/pause_tenant.py --tenant-id ten_beacon_dental --resume
    python3 scripts/pause_tenant.py --tenant-id ten_beacon_dental --status
"""

import argparse
import asyncio
import os
import sys

# Auto-detect virtualenv python
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
venv_py = os.path.join(root_dir, "slidein-api", ".venv", "bin", "python")
if os.path.exists(venv_py) and sys.executable != venv_py:
    try:
        import sqlalchemy
    except ImportError:
        os.execv(venv_py, [venv_py] + sys.argv)

api_dir = os.path.join(root_dir, "slidein-api")
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from slidein_api.db import init_db, session_scope
from slidein_api.factory.activation import ActivationService
from slidein_api.services.sending import SendingService


async def handle_tenant(tenant_id: str, action: str, reason: str = ""):
    await init_db()
    async with session_scope() as session:
        act_svc = ActivationService(session)
        send_svc = SendingService(session)

        if action == "status":
            stat = await act_svc.status(tenant_id)
            cb = await send_svc.get_circuit_state(tenant_id)
            route = await send_svc.get_config(tenant_id)
            print("==================================================")
            print(f"  Tenant Status:   {stat.get('status', 'unknown').upper()}")
            print(f"  Is Active:       {stat.get('is_active')}")
            print(f"  Circuit Breaker: {cb.get('status', 'closed').upper()}")
            print(f"  Sending Mode:    {route.get('sending_mode')}")
            print(f"  Verified Route:  {route.get('verified')}")
            if stat.get("deactivation_reason"):
                print(f"  Pause Reason:    {stat.get('deactivation_reason')}")
            print("==================================================")
            return

        if action == "pause":
            if not reason:
                reason = "Operator paused tenant outreach"
            res = await act_svc.deactivate(tenant_id, actor="operator", reason=reason)
            print(f"==> Paused tenant '{tenant_id}': {res.get('status')}")
            print(f"==> Reason: {reason}")
            return

        if action == "resume":
            res = await act_svc.activate(tenant_id, actor="operator")
            print(f"==> Resumed/Activated tenant '{tenant_id}': {res.get('status')}")
            return


def main():
    parser = argparse.ArgumentParser(description="Pause or resume tenant outreach.")
    parser.add_argument("--tenant-id", "-t", required=True, help="Tenant workspace ID.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pause", action="store_true", help="Pause the tenant.")
    group.add_argument("--resume", action="store_true", help="Resume/activate the tenant.")
    group.add_argument("--status", action="store_true", help="Check status.")
    parser.add_argument("--reason", default="", help="Reason for pausing.")
    args = parser.parse_args()

    action = "pause" if args.pause else ("resume" if args.resume else "status")
    asyncio.run(handle_tenant(args.tenant_id, action, reason=args.reason))


if __name__ == "__main__":
    main()
