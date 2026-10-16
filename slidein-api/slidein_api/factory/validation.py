"""Onboarding validation: one report covering the 16 operator stages.

Every stage reports status, remediation, and whether a human must act.
Activation requires every *required* stage to pass; informational stages
never block but stay visible so nothing fails silently.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..blueprints import list_blueprints
from ..models import StageRun, Tenant
from ..services.config import ConfigService
from ..services.outreach import DEFAULT_POLICY, OutreachService
from .configs import DeploymentConfigService
from .connections import ConnectionService
from .models import CrmFieldMap, IntegrationConnection, TeamOwner
from .owners import OwnerService

REQUIRED_CRM_FIELDS = ("owner_id", "email")


def factory_block(settings: dict) -> dict:
    block = settings.get("factory")
    return dict(block) if isinstance(block, dict) else {}


class ValidationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _stage(
        self, key: str, title: str, status: str, message: str, *,
        required: bool, remediation: str = "", human_action: bool = False,
    ) -> dict:
        return {
            "key": key, "title": title, "status": status, "message": message,
            "required": required, "remediation": remediation,
            "human_action": human_action,
        }

    async def report(self, tenant_id: str) -> dict:
        stages: list[dict] = []
        config = ConfigService(self.session)
        outreach = OutreachService(self.session)
        owners = OwnerService(self.session)
        deploy_cfgs = DeploymentConfigService(self.session)
        connections = ConnectionService(self.session)

        tenant = await self.session.get(Tenant, tenant_id)
        stored_settings = dict(tenant.settings) if tenant else {}
        block = factory_block(stored_settings)

        # 1. workspace ---------------------------------------------------------
        if tenant is None:
            stages.append(self._stage(
                "workspace", "Client workspace exists", "fail",
                "No workspace row for this tenant.", required=True,
                remediation="Provision the workspace (factory provision), then "
                            "add its API key to the server secret store.",
                human_action=True,
            ))
        elif not tenant.is_active:
            stages.append(self._stage(
                "workspace", "Client workspace exists", "fail",
                "Workspace is deactivated.", required=True,
                remediation="Review deactivation reason, then re-activate.",
                human_action=True,
            ))
        else:
            stages.append(self._stage(
                "workspace", "Client workspace exists", "pass",
                f"Workspace {tenant.name!r} is active.", required=True,
            ))

        # 2. template ----------------------------------------------------------
        active_cfg = await deploy_cfgs.get_active(tenant_id)
        if active_cfg is None:
            stages.append(self._stage(
                "template", "Workflow template selected", "fail",
                "No active deployment config.", required=True,
                remediation="Save a deployment config pinning a registered "
                            "blueprint name and version.",
                human_action=True,
            ))
        else:
            stages.append(self._stage(
                "template", "Workflow template selected", "pass",
                f"{active_cfg['blueprint_name']}@"
                f"{active_cfg['blueprint_version']} "
                f"(config v{active_cfg['version_no']}).",
                required=True,
            ))
        payload = (active_cfg or {}).get("payload") or {}
        transport = str(payload.get("transport") or payload.get("sending", {}).get("transport") or "dry_run")
        # payload shape: DeploymentConfigInput has top-level sending.limits...;
        # transport lives under sending.
        sending_cfg = payload.get("sending") or {}
        transport = str(sending_cfg.get("transport") or "dry_run").lower()
        crm_provider = str(payload.get("crm_provider") or "")
        assignment_policy = str(payload.get("assignment_policy") or "manual")

        # 3-4. intake + qualification ------------------------------------------
        readiness = await config.readiness(tenant_id)
        checks = {c["key"]: c for c in readiness.get("checklist", [])}
        core = ["business_profile", "active_offers", "icp_rules"]
        core_ok = all(
            checks.get(k, {}).get("status") == "pass" for k in core
        )
        stages.append(self._stage(
            "intake", "Business intake complete",
            "pass" if core_ok else "fail",
            f"readiness score {readiness.get('overall_score', 0)}; "
            + (", ".join(core) if core_ok else
               "missing: " + ", ".join(k for k in core
                                       if checks.get(k, {}).get("status") != "pass")),
            required=True,
            remediation="" if core_ok else
            "Complete business profile, at least one offer, one ICP.",
            human_action=not core_ok,
        ))
        icp = await config.active_icp(tenant_id)
        icp_ok = bool(icp) and bool(
            (icp.get("required_signals") or icp.get("requiredSignals"))
            or icp.get("qualify_threshold") is not None
            or icp.get("qualifyThreshold") is not None
        )
        stages.append(self._stage(
            "qualification", "Qualification rules defined",
            "pass" if icp_ok else "fail",
            "Active ICP carries signals/threshold." if icp_ok else
            "Active ICP has no required signals or threshold.",
            required=True,
            remediation="" if icp_ok else
            "Add required_signals and qualify_threshold to the ICP.",
            human_action=not icp_ok,
        ))

        # 5. integrations ------------------------------------------------------
        if transport == "dry_run":
            stages.append(self._stage(
                "integrations", "Integrations connected", "skip",
                "dry_run transport: no live sending integration needed.",
                required=False,
            ))
        else:
            ok, message = await connections.smtp_ready(tenant_id)
            stages.append(self._stage(
                "integrations", "Integrations connected",
                "pass" if ok else "fail", message, required=True,
                remediation="" if ok else
                "Register the SMTP connection with its secret reference, "
                "store the secret server-side, then run a live probe. "
                "No mail is sent by probes.",
                human_action=not ok,
            ))

        # 6. CRM maps ------------------------------------------------------------
        if not crm_provider and assignment_policy != "crm_owner":
            stages.append(self._stage(
                "crm_maps", "CRM field maps configured", "skip",
                "No CRM provider configured.", required=False,
            ))
        else:
            rows = (
                await self.session.execute(
                    select(CrmFieldMap.slidein_field).where(
                        CrmFieldMap.tenant_id == tenant_id,
                        CrmFieldMap.is_active.is_(True),
                    )
                )
            ).scalars().all()
            missing = [f for f in REQUIRED_CRM_FIELDS if f not in set(rows)]
            stages.append(self._stage(
                "crm_maps", "CRM field maps configured",
                "pass" if not missing else "fail",
                "Required canonical fields mapped." if not missing else
                f"Missing maps: {', '.join(missing)}.",
                required=True,
                remediation="" if not missing else
                "Map each required canonical field to the CRM's field.",
                human_action=bool(missing),
            ))

        # 7. booking -----------------------------------------------------------
        owner_rows = await owners.list_owners(tenant_id, active_only=True)
        if not owner_rows:
            stages.append(self._stage(
                "booking", "Owner booking destinations", "skip",
                "No team owners configured; drafts carry no booking link "
                "until owners are added.", required=False,
            ))
        else:
            bad = [
                o["email"] for o in owner_rows
                if not o["booking_verified"]
                or not (o["booking_url"] or o["booking_event_ref"])
            ]
            stages.append(self._stage(
                "booking", "Owner booking destinations",
                "pass" if not bad else "fail",
                f"{len(owner_rows)} owner(s), all verified." if not bad else
                f"Unverified/missing destinations: {', '.join(bad)}.",
                required=True,
                remediation="" if not bad else
                "Set each owner's booking URL and mark it verified only "
                "after opening it.",
                human_action=bool(bad),
            ))

        # 8. sending identity --------------------------------------------------
        raw_addr = stored_settings.get("physical_postal_address", "")
        raw_senders = stored_settings.get("allowed_senders") or []
        raw_basis = stored_settings.get("lawful_basis", "")
        addr_ok = bool(raw_addr) and raw_addr != DEFAULT_POLICY["physical_postal_address"]
        problems = []
        if not addr_ok:
            problems.append("explicit physical_postal_address")
        if not raw_senders:
            problems.append("allowed_senders")
        if not raw_basis:
            problems.append("lawful_basis")
        stages.append(self._stage(
            "sending", "Sending identity and limits",
            "pass" if not problems else "fail",
            "Explicit sender, address, and lawful basis stored."
            if not problems else f"Missing explicit: {', '.join(problems)}.",
            required=True,
            remediation="" if not problems else
            "Save the tenant sending policy with its own sender, postal "
            "address, and lawful basis. Defaults never send.",
            human_action=bool(problems),
        ))

        # 9. approvals -----------------------------------------------------------
        policy = await outreach.policy(tenant_id)
        approval_ok = bool(policy.get("require_approval"))
        stages.append(self._stage(
            "approvals", "Approval policy enforced",
            "pass" if approval_ok else "fail",
            "Human approval required before sending."
            if approval_ok else "Approval is not required.",
            required=True,
            remediation="" if approval_ok else
            "Set require_approval=true in the tenant sending policy.",
            human_action=not approval_ok,
        ))

        # 10. aggregate ----------------------------------------------------------
        required_failed = [
            s["key"] for s in stages
            if s["required"] and s["status"] != "pass"
        ]
        stages.append(self._stage(
            "readiness_gate", "Readiness gate",
            "pass" if not required_failed else "fail",
            "All required checks pass." if not required_failed else
            f"Blocked by: {', '.join(required_failed)}.",
            required=True,
            remediation="" if not required_failed else
            "Resolve each failed required stage above.",
            human_action=bool(required_failed),
        ))

        # 11. safe test ----------------------------------------------------------
        last_test = block.get("last_test") or {}
        active_version = (active_cfg or {}).get("version_no")
        test_ok = (
            bool(last_test.get("passed"))
            and last_test.get("config_version") == active_version
            and active_version is not None
        )
        if not active_cfg:
            test_message = "No deployment config to test against."
        elif not last_test:
            test_message = "No safe test has been run."
        elif last_test.get("config_version") != active_version:
            test_message = "Config changed since the last passing test."
        elif not last_test.get("passed"):
            test_message = "Last safe test failed."
        else:
            test_message = (
                f"Safe test passed on config v{active_version} "
                f"({last_test.get('mode', 'sample')})."
            )
        stages.append(self._stage(
            "safe_test", "Safe test executed", "pass" if test_ok else "fail",
            test_message, required=True,
            remediation="" if test_ok else
            "Run the factory safe test (sample or synthetic mode).",
            human_action=not test_ok,
        ))

        # 12-13. review + activation state ---------------------------------------
        stages.append(self._stage(
            "review", "Operator review", "pass",
            "This report is the review artifact; confirm each stage above.",
            required=False, human_action=True,
        ))
        status = block.get("status", "inactive")
        stages.append(self._stage(
            "activation", "Activation state", "pass",
            f"Deployment is {status}.", required=False,
        ))

        # 14. monitoring ---------------------------------------------------------
        deliverability = await outreach.deliverability_status(tenant_id)
        failed_runs = (
            await self.session.execute(
                select(StageRun)
                .where(StageRun.tenant_id == tenant_id,
                       StageRun.status == "failed")
                .order_by(StageRun.id.desc())
                .limit(5)
            )
        ).scalars().all()
        problems14: list[str] = []
        if deliverability.get("quarantined"):
            problems14.append(
                "tenant quarantined: "
                f"{deliverability.get('quarantine_reason', '')}")
        if failed_runs:
            codes = sorted({r.error_code for r in failed_runs if r.error_code})
            problems14.append(
                f"{len(failed_runs)} recent failed run(s)"
                + (f" ({', '.join(codes)})" if codes else ""))
        stages.append(self._stage(
            "monitoring", "Health and failures",
            "pass" if not problems14 else "fail",
            "No quarantine, no recent failed runs." if not problems14 else
            "; ".join(problems14) + ".",
            required=False,
            remediation="" if not problems14 else
            "Inspect runs/activity, resolve the cause, then re-validate.",
            human_action=bool(problems14),
        ))

        # 15. upgrade --------------------------------------------------------------
        latest_for_name = ""
        if active_cfg:
            same = [b for b in list_blueprints()
                    if b.name == active_cfg["blueprint_name"]]
            if same:
                latest_for_name = sorted(b.version for b in same)[-1]
        behind = bool(
            latest_for_name and active_cfg
            and active_cfg["blueprint_version"] != latest_for_name
        )
        stages.append(self._stage(
            "upgrade", "Template version currency",
            "fail" if behind else "pass",
            f"Upgrade available: {latest_for_name}." if behind else
            "Pinned to the latest registered version.",
            required=False,
            remediation="Save a new deployment config on the latest "
                        "blueprint version, test, then activate."
            if behind else "",
            human_action=behind,
        ))

        # 16. offboard --------------------------------------------------------------
        stages.append(self._stage(
            "offboard", "Offboard path defined", "pass",
            "Deactivate, export data, revoke keys and connections, archive.",
            required=False,
        ))

        failed_required = [
            s["key"] for s in stages
            if s["required"] and s["status"] != "pass"
        ]
        return {
            "tenant_id": tenant_id,
            "ready": not failed_required,
            "failed_required": failed_required,
            "stages": stages,
        }
