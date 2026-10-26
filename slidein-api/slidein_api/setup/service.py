"""One operation: context in, usable workspace out.

    provide context -> generate setup -> review exceptions
    -> connect tools -> test -> activate

`SetupService.generate` reads whatever sources the operator supplied,
extracts a provenance-carrying business profile, proposes a workspace
blueprint validated against the module registry and a registered
workflow blueprint, persists it, and reports exactly what is still
missing. `status` derives the six named stages the mission asks for, so
"generated" is never reported as "active".
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ValidationError
from ..factory.activation import ActivationService
from ..factory.configs import DeploymentConfigService
from ..factory.connections import ConnectionService
from ..factory.validation import ValidationService
from ..identity import IdentityService
from ..models import Tenant
from ..services.config import ConfigService
from ..services.modules import ModulesService
from ..services.outreach import OutreachService
from ..services.suppression import SuppressionService
from ..services.templates import TemplateService
from .blueprint import detect_crm, propose_blueprint
from .extract import extract_profile
from .questions import apply_answers, build_questions, grouped, open_blocking
from .sources import normalise_sources

PROFILE_REQUIRED = (
    "legal_name", "website_url", "industry", "business_description", "core_value_prop",
)

SETUP_STAGES: tuple[tuple[str, str], ...] = (
    ("workspace_generated", "Workspace generated"),
    ("configuration_validated", "Configuration validated"),
    ("integrations_connected", "Integrations connected"),
    ("workflow_tested", "Workflow tested"),
    ("owner_ready", "Owner access ready"),
    ("ready_for_approval", "Ready for approval"),
    ("active", "Active"),
)

STAGE_TARGETS: dict[str, dict[str, str]] = {
    "workspace_generated": {"label": "Add client context and generate the setup",
                            "target": "#intake"},
    "configuration_validated": {"label": "Answer the open setup questions",
                                "target": "#questions"},
    "integrations_connected": {"label": "Connect and probe the required tools",
                               "target": "#integrations"},
    "workflow_tested": {"label": "Run the first controlled test",
                        "target": "#test"},
    "owner_ready": {"label": "Create the owner login for Console and Dashboard",
                    "target": "#access"},
    "ready_for_approval": {"label": "Review the setup and request approval",
                           "target": "#review"},
    "active": {"label": "Open the workspace overview", "target": "/overview"},
}

_VALIDATION_KEYS = (
    "template", "intake", "qualification", "sending", "approvals",
    "booking", "crm_maps",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_list(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;\n|,]", value or "") if part.strip()]


class SetupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- storage -----------------------------------------------------------

    async def _tenant(self, tenant_id: str) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def _setup_block(self, tenant_id: str) -> dict:
        row = await self._tenant(tenant_id)
        settings = dict(row.settings or {}) if row is not None else {}
        block = settings.get("setup")
        return dict(block) if isinstance(block, dict) else {}

    async def _write_setup_block(self, tenant_id: str, block: dict) -> None:
        row = await self._tenant(tenant_id)
        if row is None:
            raise ValidationError(
                f"Workspace {tenant_id!r} does not exist",
                code="not_found", recovery_action="provision_workspace",
            )
        settings = dict(row.settings or {})
        settings["setup"] = block
        row.settings = settings
        await self.session.flush()

    # -- generate ----------------------------------------------------------

    async def generate(
        self, tenant_id: str, payload: dict, *, actor: str = "operator"
    ) -> dict:
        stored = await self._setup_block(tenant_id)
        existing_answers = dict(stored.get("answers") or {})

        if "sources" in payload:
            sources_raw = payload.get("sources") or []
        else:
            sources_raw = stored.get("sources") or []

        answers = dict(existing_answers)
        for key, value in (payload.get("answers") or {}).items():
            if str(value).strip() == "":
                answers.pop(str(key), None)
            else:
                answers[str(key)] = str(value).strip()

        normalised = normalise_sources(sources_raw)
        sources = normalised.sources
        draft = extract_profile(sources)
        apply_answers(draft, answers)

        corpus = "\n".join(
            s.text for s in sources if s.status in ("ready", "truncated")
        )
        tenant = await self._tenant(tenant_id)
        tenant_name = (tenant.name if tenant else "") or tenant_id

        blueprint = propose_blueprint(
            draft, answers, tenant_name=tenant_name, corpus=corpus)
        questions = build_questions(
            draft,
            answers,
            corpus=corpus,
            outreach_enabled=bool(blueprint["scope"]["include_outreach"]),
            crm_detected=detect_crm(corpus) or str(answers.get("crm_provider") or ""),
        )

        config = ConfigService(self.session)
        legal_name = str(
            draft["fields"].get("legal_name", {}).get("value") or "").strip()
        await config.ensure_tenant(tenant_id, name=legal_name or None)

        profile_saved = await self._save_profile(tenant_id, draft, answers, actor=actor)
        offer_saved = await self._save_offer(tenant_id, draft, actor=actor)
        icp_saved = await self._save_icp(tenant_id, draft, actor=actor)

        deploy = DeploymentConfigService(self.session)
        saved_config = await deploy.save_config(
            tenant_id, blueprint["deployment_config"], actor=actor,
            note="generated by client setup",
        )

        await ModulesService(self.session).update_modules(
            tenant_id,
            {"enabled": blueprint["modules"]["enabled"],
             "nav_order": blueprint["modules"]["nav_order"]},
            actor=actor,
        )
        await self._write_terminology(tenant_id, blueprint["terminology"]["sections"])
        await self._maybe_save_policy(tenant_id, answers, actor=actor)
        await self._register_connections(tenant_id, blueprint, actor=actor)

        suppression = SuppressionService(self.session)
        if not await suppression.is_configured(tenant_id):
            await suppression.seed_defaults(tenant_id)

        block = {
            "version": int(stored.get("version") or 0) + 1,
            "generated_at": _now(),
            "generated_by": actor,
            "sources": [s.to_dict() for s in sources],
            "rejected": normalised.rejected,
            "answers": answers,
            "draft": draft,
            "questions": questions,
            "blueprint": {
                "blueprint": blueprint["blueprint"],
                "modules": blueprint["modules"],
                "terminology": blueprint["terminology"],
                "required_integrations": blueprint["required_integrations"],
                "approval_policy": blueprint["approval_policy"],
                "reporting": blueprint["reporting"],
                "scope": blueprint["scope"],
                "proposed_enhancements": blueprint["proposed_enhancements"],
                "validation": blueprint["validation"],
            },
            "config_version": saved_config["version_no"],
        }
        await self._write_setup_block(tenant_id, block)

        return {
            "tenant_id": tenant_id,
            "generated_at": block["generated_at"],
            "sources": block["sources"],
            "rejected_sources": block["rejected"],
            "profile": {
                "fields": draft["fields"],
                "conflicts": draft["conflicts"],
                "counts": draft["counts"],
                "saved": profile_saved,
                "offer_created": offer_saved,
                "icp_created": icp_saved,
            },
            "blueprint": block["blueprint"],
            "questions": questions,
            "open_questions": grouped(questions),
            "status": await self.status(tenant_id),
        }

    async def answer(
        self, tenant_id: str, answers: dict, *, actor: str = "operator"
    ) -> dict:
        """Record answers, then regenerate from the same sources."""
        if not isinstance(answers, dict) or not answers:
            raise ValidationError(
                "answers must be an object of key/value pairs",
                code="fix_request", recovery_action="fix_request",
            )
        return await self.generate(
            tenant_id, {"answers": answers}, actor=actor
        )

    # -- persistence helpers ------------------------------------------------

    async def _save_profile(
        self, tenant_id: str, draft: dict, answers: dict, *, actor: str
    ) -> bool:
        values = {
            key: str(draft["fields"].get(key, {}).get("value") or "").strip()
            for key in PROFILE_REQUIRED
        }
        if any(not values[key] for key in PROFILE_REQUIRED):
            return False

        config = ConfigService(self.session)
        current = await config.active_profile(tenant_id)
        geo = _split_list(draft["fields"].get("geography", {}).get("value") or "")
        payload = {
            "legal_name": values["legal_name"],
            "website_url": values["website_url"],
            "industry": values["industry"],
            "company_description": values["business_description"],
            "core_value_prop": values["core_value_prop"],
            "markets_served": geo,
            "brand_voice": draft["fields"].get("brand_voice", {}).get("value") or "",
            "target_roles": [],
            "reason": "client setup",
        }
        if current and _same_profile(current, payload):
            return False
        await config.save_profile(tenant_id, payload, actor=actor)
        return True

    async def _save_offer(self, tenant_id: str, draft: dict, *, actor: str) -> bool:
        products = str(draft["fields"].get("products_services", {}).get("value") or "").strip()
        if not products:
            return False
        config = ConfigService(self.session)
        if await config.active_profile(tenant_id) is None:
            return False
        parts = [p.strip() for p in re.split(r"[;\n]", products) if p.strip()]
        name = parts[0][:255]
        icp = str(draft["fields"].get("ideal_customer_profile", {}).get("value") or "")
        differentiators = str(draft["fields"].get("differentiators", {}).get("value") or "")
        config = ConfigService(self.session)
        active = await config.list_offers(tenant_id)
        summary = products[:2000]
        if any(o.get("name") == name and o.get("summary") == summary for o in active):
            return False
        await config.save_offer(tenant_id, {
            "name": name,
            "summary": summary,
            "target_persona": icp[:255],
            "pain_points_solved": [],
            "proof_points": [differentiators[:255]] if differentiators else [],
            "reason": "client setup",
        }, actor=actor)
        return True

    async def _save_icp(self, tenant_id: str, draft: dict, *, actor: str) -> bool:
        icp_text = str(draft["fields"].get("ideal_customer_profile", {}).get("value") or "").strip()
        if not icp_text:
            return False
        config = ConfigService(self.session)
        if await config.active_profile(tenant_id) is None:
            return False
        industries = _split_list(
            draft["fields"].get("industries_served", {}).get("value") or "")
        industry = str(draft["fields"].get("industry", {}).get("value") or "")
        geographies = _split_list(draft["fields"].get("geography", {}).get("value") or "")
        signals = _split_list(
            draft["fields"].get("qualification_rules", {}).get("value") or "")
        exclusions = _split_list(
            draft["fields"].get("exclusion_rules", {}).get("value") or "")
        name = re.split(r"[.;]", icp_text)[0].strip()[:255]
        config = ConfigService(self.session)
        active = await config.list_icps(tenant_id)
        target = {
            "industries": industries or ([industry] if industry else []),
            "geographies": geographies,
            "required_signals": signals,
            "exclusion_keywords": exclusions,
        }
        for row in active:
            if row.get("name") != name:
                continue
            if all(row.get(k) == v for k, v in target.items()):
                return False
        payload = {"name": name, "qualify_threshold": 70, **target}
        await config.save_icp(tenant_id, payload, actor=actor)
        return True

    async def _write_terminology(self, tenant_id: str, sections: dict) -> None:
        if not sections:
            return
        row = await self._tenant(tenant_id)
        if row is None:
            return
        settings = dict(row.settings or {})
        terms = dict(settings.get("terminology") or {})
        merged = dict(terms.get("sections") or {})
        merged.update({k: v for k, v in sections.items() if v})
        terms["sections"] = merged
        settings["terminology"] = terms
        row.settings = settings
        await self.session.flush()

    async def _maybe_save_policy(
        self, tenant_id: str, answers: dict, *, actor: str
    ) -> bool:
        """The sending policy is written only from explicit answers.

        Until address, sender and lawful basis are all confirmed there is
        no policy write, so the validation report keeps failing stage
        `sending` and activation stays blocked.
        """
        address = str(answers.get("physical_postal_address") or "").strip()
        sender = str(answers.get("sender") or "").strip()
        lawful = str(answers.get("lawful_basis") or "").strip()
        if not (address and sender and lawful):
            return False
        updates: dict[str, Any] = {
            "physical_postal_address": address,
            "lawful_basis": lawful,
            "allowed_senders": [sender],
            "require_approval": str(answers.get("require_approval", "true")).lower() != "false",
        }
        if str(answers.get("hourly_limit") or "").strip().isdigit():
            updates["hourly_limit"] = int(answers["hourly_limit"])
        if str(answers.get("daily_limit") or "").strip().isdigit():
            updates["daily_limit"] = int(answers["daily_limit"])
        await OutreachService(self.session).save_policy(
            tenant_id, updates, actor=actor
        )
        return True

    async def _register_connections(
        self, tenant_id: str, blueprint: dict, *, actor: str
    ) -> None:
        service = ConnectionService(self.session)
        existing = await service.list_connections(tenant_id)
        known = {(c["provider"], c["label"]) for c in existing}
        for item in blueprint["required_integrations"]:
            if not item.get("required") or not item.get("secret_ref"):
                continue
            key = (item["provider"], item["label"])
            if key in known:
                continue
            await service.register(tenant_id, {
                "provider": item["provider"],
                "label": item["label"],
                "secret_ref": item["secret_ref"],
                "scopes": ["send"] if item["provider"] == "smtp" else ["read", "write"],
            }, actor=actor)

    # -- status -------------------------------------------------------------

    async def status(self, tenant_id: str) -> dict:
        block = await self._setup_block(tenant_id)
        validation = await ValidationService(self.session).report(tenant_id)
        activation = await ActivationService(self.session).status(tenant_id)
        connections = await ConnectionService(self.session).list_connections(tenant_id)
        suppression_ok = await SuppressionService(self.session).is_configured(tenant_id)

        stages_by_key = {s["key"]: s for s in validation["stages"]}
        failed_required = set(validation["failed_required"])
        questions = block.get("questions") or []
        blocking = open_blocking(questions)
        blueprint_validation = (block.get("blueprint") or {}).get("validation") or {}

        required_connections = [
            item for item in (block.get("blueprint") or {}).get("required_integrations", [])
            if item.get("required")
        ]
        connection_status = {
            item["id"]: _connection_state(item, connections)
            for item in required_connections
        }

        def stage_failed(keys: tuple[str, ...]) -> bool:
            return any(key in failed_required for key in keys)

        generated = bool(block.get("generated_at"))
        validated = (
            generated
            and not stage_failed(_VALIDATION_KEYS)
            and bool(blueprint_validation.get("ok", False))
            and not blocking
        )
        integrations_connected = (
            validated
            and not stage_failed(("integrations",))
            and all(state in ("connected", "manual", "builtin", "not_required")
                    for state in connection_status.values())
        )
        tested = validated and not stage_failed(("safe_test",))
        active = str(activation.get("status")) == "active"
        owner_ready = await IdentityService(self.session).has_owner(tenant_id)
        ready = (
            generated and validated and integrations_connected and tested
            and owner_ready and not blocking and not active
        )

        derived = {
            "workspace_generated": generated,
            "configuration_validated": validated,
            "integrations_connected": integrations_connected,
            "workflow_tested": tested,
            "owner_ready": owner_ready,
            "ready_for_approval": ready,
            "active": active,
        }
        # `state` is the stage the operator is working on right now. Being
        # ready for approval is its own stage: "active" only ever means the
        # deployment is actually live.
        if derived["active"]:
            current = "active"
        else:
            current = next(
                (key for key, _ in SETUP_STAGES if key != "active"
                 and not derived[key]),
                "ready_for_approval",
            )

        blockers: list[dict] = []
        for key in validation["failed_required"]:
            stage = stages_by_key.get(key, {})
            blockers.append({
                "kind": "validation_stage",
                "id": key,
                "title": stage.get("title", key),
                "detail": stage.get("message", ""),
                "remediation": stage.get("remediation", ""),
                "human_action": bool(stage.get("human_action")),
            })
        for question in blocking:
            blockers.append({
                "kind": "open_question",
                "id": question["key"],
                "title": question["prompt"],
                "detail": question["help"],
                "remediation": f"Answer in {question['group']} — unblocks "
                                f"{question.get('unblocks') or 'setup'}.",
                "human_action": True,
            })
        for item_id, state in connection_status.items():
            if state in ("failing", "missing", "unknown"):
                detail = next(
                    (c.get("last_error", "") for c in connections
                     if c.get("label") == item_id), "")
                blockers.append({
                    "kind": "integration",
                    "id": item_id,
                    "title": f"Integration {item_id} is not verified",
                    "detail": detail or "Connection has not passed a live probe.",
                    "remediation": "Register the credential in the server secret "
                                    "store, then run the probe.",
                    "human_action": True,
                })
        for missing in blueprint_validation.get("missing_required", []):
            blockers.append({
                "kind": "blueprint_config",
                "id": missing,
                "title": f"Blueprint configuration missing: {missing}",
                "detail": "The registered workflow blueprint requires this value.",
                "remediation": "Answer the matching setup question, then regenerate.",
                "human_action": True,
            })
        for missing in blueprint_validation.get("missing_integrations", []):
            blockers.append({
                "kind": "blueprint_integration",
                "id": missing,
                "title": f"Required integration not connected: {missing}",
                "detail": "Live transport is selected but the credential is absent.",
                "remediation": "Register and probe the connection, or keep dry-run "
                                "transport for the first test.",
                "human_action": True,
            })
        if not owner_ready:
            blockers.append({
                "kind": "owner_access",
                "id": "owner_login",
                "title": "No owner login exists for this workspace",
                "detail": "Console and Dashboard cannot be signed in to until an "
                          "owner account has been created.",
                "remediation": "Create the owner login in the Access step below.",
                "human_action": True,
            })

        checklist = [
            {
                "key": key,
                "label": label,
                "done": derived[key],
                "status": "pass" if derived[key] else ("current" if key == current else "pending"),
                "detail": _stage_detail(key, derived, validation, activation,
                                        blocking, connection_status),
            }
            for key, label in SETUP_STAGES
        ]

        return {
            "tenant_id": tenant_id,
            "state": current,
            "states": derived,
            "checklist": checklist,
            "next_action": STAGE_TARGETS[current],
            "generated_at": block.get("generated_at", ""),
            "config_version": block.get("config_version"),
            "attempt": block.get("version", 0),
            "suppression_configured": suppression_ok,
            "open_blocking_questions": blocking,
            "blockers": blockers,
            "sources": block.get("sources") or [],
            "rejected_sources": block.get("rejected") or [],
            "validation": {
                "ready": validation["ready"],
                "failed_required": validation["failed_required"],
                "stages": validation["stages"],
            },
            "activation": activation,
            "connections": connections,
            "connection_state": connection_status,
            "blueprint_validation": blueprint_validation,
            "questions": questions,
            "answers": block.get("answers") or {},
            "profile": (block.get("draft") or {}).get("fields"),
            "conflicts": (block.get("draft") or {}).get("conflicts") or [],
            "counts": (block.get("draft") or {}).get("counts") or {},
            "blueprint": block.get("blueprint"),
            "proposed_enhancements": (
                (block.get("blueprint") or {}).get("proposed_enhancements") or []
            ),
        }


def _connection_state(item: dict, connections: list[dict]) -> str:
    probe = item.get("probe", "unsupported")
    if probe in ("manual", "builtin", "not_required"):
        return probe
    matches = [c for c in connections if c.get("provider") == item.get("provider")]
    if not matches:
        return "missing"
    if any(c.get("status") == "connected" for c in matches):
        return "connected"
    if any(c.get("status") == "failing" for c in matches):
        return "failing"
    if any(c.get("status") == "unknown" for c in matches):
        return "unknown"
    return "missing"


def _stage_detail(
    key: str,
    derived: dict,
    validation: dict,
    activation: dict,
    blocking: list,
    connection_state: dict,
) -> str:
    if key == "workspace_generated":
        return (
            "Business profile, offers, ICP and workspace blueprint persisted."
            if derived[key] else "No setup has been generated for this workspace yet."
        )
    if key == "configuration_validated":
        failed = [s["title"] for s in validation["stages"]
                  if s["required"] and s["status"] != "pass"
                  and s["key"] != "safe_test"]
        if derived[key]:
            return "All required configuration checks pass."
        if failed:
            return "Waiting on: " + ", ".join(failed)
        return (f"{len(blocking)} required question(s) still need an answer."
                if blocking else "Blueprint validation has outstanding items.")
    if key == "integrations_connected":
        if derived[key]:
            return "Every required integration is verified or explicitly not required."
        pending = [k for k, v in connection_state.items() if v in ("failing", "missing", "unknown")]
        return "Not verified: " + ", ".join(pending) if pending else (
            "An integration stage has not passed."
        )
    if key == "workflow_tested":
        last_test = (activation.get("last_test") or {})
        if derived[key]:
            return f"Safe test passed on config v{last_test.get('config_version')}."
        return "No passing safe test on the active configuration."
    if key == "owner_ready":
        return (
            "Owner login exists — Console and Dashboard can be signed in to."
            if derived[key]
            else "No login exists yet; create the owner account in the Access step."
        )
    if key == "ready_for_approval":
        if derived[key]:
            return f"{len(blocking)} open question(s) remain before approval."
        return "Everything checked; approval is the remaining step." if derived[key] else (
            f"{len(blocking)} open question(s); earlier stages must pass first."
        )
    if key == "active":
        return f"Deployment is {activation.get('status', 'inactive')}." if derived[key] else (
            "Not activated — activation requires every required stage to pass."
        )
    return ""


def _same_profile(current: dict, payload: dict) -> bool:
    for key in ("legal_name", "website_url", "industry",
                "company_description", "core_value_prop", "brand_voice"):
        if str(current.get(key) or "").strip() != str(payload.get(key) or "").strip():
            return False
    for key in ("markets_served",):
        if list(current.get(key) or []) != list(payload.get(key) or []):
            return False
    return True
