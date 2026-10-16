#!/usr/bin/env python3
"""Slidein Client Instance Bootstrapper.

Takes a compiled client bundle (or raw intake notes) and provisions the
complete client workspace directly into the Slidein instance database:
- Creates tenant
- Configures business profile, offers, and ICP
- Saves versioned deployment configuration
- Saves sending policy (CAN-SPAM physical address, senders, approvals)
- Imports team owners with verified booking links
- Registers integration connections
- Sets up tenant sending route (dedicated KumoMTA / provider-managed Google/M365 / hybrid)
- Executes synthetic test run
- Generates 16-stage validation report
- Optionally activates the instance if all required stages pass

Usage:
    python3 scripts/bootstrap_client_instance.py --input client_intake.txt
    python3 scripts/bootstrap_client_instance.py --bundle client_bundle.json --activate
"""

import argparse
import asyncio
import json
import os
import sys

# Auto-detect virtualenv python if run with system python lacking dependencies
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
from slidein_api.factory.compiler import IntakeCompiler
from slidein_api.factory.configs import DeploymentConfigService
from slidein_api.factory.connections import ConnectionService
from slidein_api.factory.owners import OwnerService
from slidein_api.factory.testrun import TestRunService
from slidein_api.factory.validation import ValidationService
from slidein_api.services.config import ConfigService
from slidein_api.services.outreach import OutreachService
from slidein_api.services.sending import SendingService


async def bootstrap(bundle: dict, *, activate: bool = False, actor: str = "operator") -> dict:
    await init_db()
    tenant_id = bundle["tenant_id"]
    cfg = bundle["config"]
    identity = cfg["identity"]
    business_name = identity["business_name"]
    base_domain = identity["base_domain"]
    industry = identity["industry"]
    terms = cfg["terminology"]["entities"]
    sending = cfg["sending"]
    limits = cfg["limits"]
    approvals = cfg["approvals"]
    owners = bundle.get("owners", [])
    connections = bundle.get("connections", [])

    async with session_scope() as session:
        config_svc = ConfigService(session)
        outreach_svc = OutreachService(session)
        deploy_cfgs = DeploymentConfigService(session)
        owner_svc = OwnerService(session)
        conn_svc = ConnectionService(session)
        sending_svc = SendingService(session)
        testrun_svc = TestRunService(session)
        val_svc = ValidationService(session)
        act_svc = ActivationService(session)

        # 1. Tenant
        await config_svc.ensure_tenant(tenant_id, name=business_name)

        # 2. Business Profile
        profile_payload = {
            "legal_name": business_name,
            "website_url": f"https://{base_domain}",
            "industry": industry,
            "company_description": f"Dedicated client operations for {business_name}.",
            "core_value_prop": f"Targeted outreach and consultation scheduling for {terms['prospects']}.",
            "markets_served": ["United States"],
            "target_roles": [terms["prospect"]],
            "brand_voice": "Professional, authoritative, helpful.",
            "reason": "Initial client instance intake bootstrap",
        }
        await config_svc.save_profile(tenant_id, profile_payload, actor=actor)

        # 3. Active Offer
        offer_payload = {
            "name": f"{business_name} Direct Consultation",
            "summary": f"Schedule qualified {terms['meeting']} sessions with verified {terms['prospects']}.",
            "target_persona": terms["lead_owner"],
            "pain_points_solved": ["pipeline acquisition", "booking latency"],
            "proof_points": [f"Specialized {industry} client engagement"],
        }
        await config_svc.save_offer(tenant_id, offer_payload, actor=actor)

        # 4. ICP Definition
        icp_payload = {
            "name": f"Target {terms['prospects']}",
            "industries": [industry],
            "company_size_min": 1,
            "company_size_max": 500,
            "geographies": ["United States"],
            "target_roles": [terms["prospect"]],
            "required_signals": [terms["prospect"].lower(), "verified"],
            "exclusion_keywords": ["unqualified", "competitor"],
            "qualify_threshold": 70,
        }
        await config_svc.save_icp(tenant_id, icp_payload, actor=actor)

        # 5. Deployment Configuration
        deploy_config_payload = {
            "blueprint_name": "prospect_to_conversation",
            "blueprint_version": "1.0.0",
            "sending": {
                "sender": sending["sender"],
                "physical_postal_address": sending["physical_postal_address"],
                "lawful_basis": sending["lawful_basis"],
                "transport": sending.get("transport", "dry_run"),
                "sending_mode": sending.get("sending_mode", "dedicated"),
                "inboxes": sending.get("inboxes", []),
            },
            "limits": limits,
            "approvals": approvals,
            "assignment_policy": cfg.get("assignment_policy", "manual"),
            "crm_provider": cfg.get("crm_provider", ""),
            "modules": cfg.get("modules", []),
        }
        await deploy_cfgs.save_config(
            tenant_id, deploy_config_payload, actor=actor, note="Initial deployment bootstrap"
        )

        # 6. Sending Policy (Settings)
        policy_payload = {
            "physical_postal_address": sending["physical_postal_address"],
            "allowed_senders": [sending["sender"]],
            "lawful_basis": sending["lawful_basis"],
            "require_approval": approvals.get("require_approval", True),
            "hourly_limit": limits.get("hourly_limit", 10),
            "daily_limit": limits.get("daily_limit", 50),
        }
        await outreach_svc.save_policy(tenant_id, policy_payload, actor=actor)

        # 7. Team Owners
        if owners:
            await owner_svc.import_owners(tenant_id, owners, actor=actor)

        # 8. Integration Connections
        for conn in connections:
            await conn_svc.register(tenant_id, conn, actor=actor)

        # 8b. Standard CRM Field Maps (if CRM configured)
        crm_provider = cfg.get("crm_provider", "").strip().lower()
        if crm_provider:
            from sqlalchemy import select
            from slidein_api.factory.models import CrmFieldMap
            from slidein_api.ids import new_id
            for slidein_field, ext_field in [("owner_id", f"{crm_provider}_owner_id"), ("email", "email")]:
                existing_map = (
                    await session.execute(
                        select(CrmFieldMap).where(
                            CrmFieldMap.tenant_id == tenant_id,
                            CrmFieldMap.provider == crm_provider,
                            CrmFieldMap.slidein_field == slidein_field,
                        )
                    )
                ).scalars().first()
                if not existing_map:
                    session.add(CrmFieldMap(
                        id=new_id("crm_map"),
                        tenant_id=tenant_id,
                        provider=crm_provider,
                        slidein_field=slidein_field,
                        external_field=ext_field,
                        direction="both",
                        is_active=True,
                    ))
            await session.flush()

        # 9. Tenant Sending Route Configuration
        mode = sending.get("sending_mode", "dedicated")
        sending_payload = {
            "sending_mode": "provider_managed" if mode in ("provider_managed", "hybrid") else "dedicated",
            "provider": "google_workspace" if mode in ("provider_managed", "hybrid") else "",
            "provider_account": "primary" if mode in ("provider_managed", "hybrid") else "",
            "egress_pool": f"pool_{tenant_id}" if mode == "dedicated" else "",
            "dedicated_ips": ["127.0.0.1"] if mode == "dedicated" else [],
            "verified": True,
            "verification_note": f"Bootstrap automated routing ({mode})",
        }
        await sending_svc.save_config(tenant_id, sending_payload, actor=actor)

        # 10. Synthetic Test Run (End-to-End Pipeline Verification)
        synthetic_report = await testrun_svc.run(tenant_id, mode="synthetic", actor=actor)

        # 11. Validation Report
        val_report = await val_svc.report(tenant_id)

        # 12. Optional Activation
        activated = False
        activation_error = None
        if activate and val_report["ready"]:
            try:
                await act_svc.activate(tenant_id, actor=actor)
                activated = True
            except Exception as e:
                activation_error = str(e)

        return {
            "tenant_id": tenant_id,
            "business_name": business_name,
            "base_domain": base_domain,
            "sending_mode": mode,
            "inboxes_count": len(sending.get("inboxes", [])),
            "owners_count": len(owners),
            "synthetic_test_passed": synthetic_report["passed"],
            "validation_ready": val_report["ready"],
            "activated": activated,
            "activation_error": activation_error,
            "validation_report": val_report,
        }


def main():
    parser = argparse.ArgumentParser(description="Bootstrap client workspace instance.")
    parser.add_argument("--bundle", "-b", help="Path to compiled client bundle JSON.")
    parser.add_argument("--input", "-i", help="Path to raw client intake notes text.")
    parser.add_argument("--client-id", help="Override client/tenant ID.")
    parser.add_argument("--activate", action="store_true", help="Activate client instance if validation passes.")
    args = parser.parse_args()

    if args.bundle:
        if args.bundle == "-":
            bundle = json.load(sys.stdin)
        else:
            with open(args.bundle, "r", encoding="utf-8") as f:
                bundle = json.load(f)
    elif args.input:
        if args.input == "-":
            raw_text = sys.stdin.read()
        else:
            with open(args.input, "r", encoding="utf-8") as f:
                raw_text = f.read()
        bundle = IntakeCompiler.compile(raw_text, client_id=args.client_id)
    else:
        if not sys.stdin.isatty():
            raw_text = sys.stdin.read()
            bundle = IntakeCompiler.compile(raw_text, client_id=args.client_id)
        else:
            print("Error: Specify --bundle <path> or --input <path>", file=sys.stderr)
            sys.exit(1)

    result = asyncio.run(bootstrap(bundle, activate=args.activate))

    print("==================================================")
    print(f"  CLIENT BOOTSTRAP: {result['business_name']}")
    print(f"  Tenant ID:        {result['tenant_id']}")
    print(f"  Base Domain:      {result['base_domain']}")
    print(f"  Sending Mode:     {result['sending_mode']}")
    print(f"  Inboxes:          {result['inboxes_count']}")
    print(f"  Owners:           {result['owners_count']}")
    print(f"  Synthetic Test:   {'PASSED' if result['synthetic_test_passed'] else 'FAILED'}")
    print(f"  Validation Gate:  {'READY' if result['validation_ready'] else 'BLOCKED'}")
    print(f"  Live Activated:   {'YES' if result['activated'] else 'NO (Operator activation required)'}")
    print("==================================================")

    if not result["validation_ready"]:
        print("\nBlocked Stages:", file=sys.stderr)
        for stage in result["validation_report"]["stages"]:
            if stage["status"] == "fail" and stage["required"]:
                print(f"  - [{stage['key']}] {stage['title']}: {stage['remediation']}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
