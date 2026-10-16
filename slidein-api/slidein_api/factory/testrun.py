"""Safe test execution: sample (read-only) or synthetic (labeled writes
with cleanup). Nothing here can send: drafts stay pending review and the
transport is never invoked."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import ConfigError, SlideinError
from ..ids import new_id
from ..models import EvidenceItem, Prospect, QualificationResult, utcnow
from ..services.config import ConfigService
from ..services.discovery import DiscoveryService
from ..services.outreach import OutreachService
from ..services.personalization import PersonalizationService
from .activation import ActivationService
from .configs import DeploymentConfigService
from .owners import OwnerService


class TestRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(
        self, tenant_id: str, *, mode: str, prospect_id: str | None = None,
        actor: str = "operator",
    ) -> dict:
        if mode == "sample":
            if not prospect_id:
                raise ConfigError(
                    "Sample mode needs a prospect_id",
                    code="prospect_required",
                    recovery_action="select_sample_prospect",
                )
            return await self._run_sample(tenant_id, prospect_id, actor=actor)
        if mode == "synthetic":
            return await self._run_synthetic(tenant_id, actor=actor)
        raise ConfigError(
            f"Unknown test mode {mode!r}",
            code="test_mode_invalid",
            recovery_action="select_test_mode",
        )

    def _finding(self, check: str, status: str, message: str,
                 *, blocking: bool) -> dict:
        return {"check": check, "status": status, "message": message,
                "blocking": blocking}

    async def _common_findings(
        self, tenant_id: str, prospect: Prospect | None,
    ) -> tuple[list[dict], OwnerService]:
        findings: list[dict] = []
        config = ConfigService(self.session)
        outreach = OutreachService(self.session)
        owners = OwnerService(self.session)

        readiness = await config.readiness(tenant_id)
        checks = {c["key"]: c["status"] for c in readiness.get("checklist", [])}
        core_ok = all(
            checks.get(k) == "pass"
            for k in ("business_profile", "active_offers", "icp_rules")
        )
        findings.append(self._finding(
            "readiness", "pass" if core_ok else "fail",
            f"readiness score {readiness.get('overall_score', 0)}",
            blocking=True,
        ))

        deliverability = await outreach.deliverability_status(tenant_id)
        quarantined = bool(deliverability.get("quarantined"))
        findings.append(self._finding(
            "quarantine", "fail" if quarantined else "pass",
            "tenant is quarantined" if quarantined else "not quarantined",
            blocking=True,
        ))

        owner_count = await owners.owner_count(tenant_id)
        if prospect is None:
            findings.append(self._finding(
                "booking", "skip", "no prospect under test", blocking=False,
            ))
        elif owner_count == 0:
            findings.append(self._finding(
                "booking", "skip",
                "no team owners configured; drafts carry no booking link",
                blocking=False,
            ))
        else:
            try:
                resolved = await owners.resolve_booking(tenant_id, prospect.id)
            except SlideinError as exc:
                findings.append(self._finding(
                    "booking", "fail",
                    f"held for review: {exc.code} — {exc.message}",
                    blocking=True,
                ))
            else:
                findings.append(self._finding(
                    "booking", "pass",
                    f"resolved to {resolved['owner_name']} "
                    f"({resolved['booking_provider'] or 'link'})",
                    blocking=True,
                ))
        return findings, owners

    async def _finish(
        self, tenant_id: str, mode: str, findings: list[dict], actor: str,
        extra: dict | None = None,
    ) -> dict:
        passed = all(
            f["status"] == "pass" or not f["blocking"] for f in findings
        )
        deploy_cfgs = DeploymentConfigService(self.session)
        active = await deploy_cfgs.get_active(tenant_id)
        summary = {
            "mode": mode, "passed": passed,
            "config_version": (active or {}).get("version_no"),
            "at": utcnow().isoformat(), "actor": actor,
            "findings": len(findings),
        }
        await ActivationService(self.session).record_test(tenant_id, summary)
        report = {"tenant_id": tenant_id, "mode": mode, "passed": passed,
                  "findings": findings, "last_test": summary}
        if extra:
            report.update(extra)
        return report

    async def _run_sample(
        self, tenant_id: str, prospect_id: str, actor: str
    ) -> dict:
        prospect = await self.session.get(Prospect, prospect_id)
        if prospect is None or prospect.tenant_id != tenant_id:
            findings = [self._finding(
                "sample", "fail", "sample prospect not found", blocking=True,
            )]
            return await self._finish(tenant_id, "sample", findings, actor)
        findings, _ = await self._common_findings(tenant_id, prospect)
        return await self._finish(
            tenant_id, "sample", findings, actor,
            {"prospect_id": prospect_id},
        )

    async def _run_synthetic(self, tenant_id: str, actor: str) -> dict:
        config = ConfigService(self.session)
        discovery = DiscoveryService(self.session)
        personalization = PersonalizationService(self.session)
        owners = OwnerService(self.session)

        icp = await config.active_icp(tenant_id)
        if icp is None:
            findings = [self._finding(
                "synthetic", "fail", "no active ICP to test against",
                blocking=True,
            )]
            return await self._finish(tenant_id, "synthetic", findings, actor)

        stamp = utcnow().strftime("%Y%m%d%H%M%S%f")
        email = f"factory-test-{stamp}@example.invalid"
        try:
            ingest = await discovery.create_records(
                tenant_id, icp_id=icp["id"],
                records=[{
                    "email": email, "company_name": "Factory Test Co",
                    "first_name": "Test", "last_name": "Prospect",
                }],
                source="factory-test", created_by=f"factory-test:{actor}",
            )
        except SlideinError as exc:
            findings = [self._finding(
                "synthetic", "fail",
                f"ingest blocked: {exc.code} — {exc.message}", blocking=True,
            )]
            return await self._finish(tenant_id, "synthetic", findings, actor)
        if not ingest["prospect_ids"]:
            findings = [self._finding(
                "synthetic", "fail",
                f"ingest skipped: {ingest['skipped_records']}", blocking=True,
            )]
            return await self._finish(tenant_id, "synthetic", findings, actor)

        prospect_id = ingest["prospect_ids"][0]
        draft_id: str | None = None
        try:
            prospect = await self.session.get(Prospect, prospect_id)
            assert prospect is not None

            # 1. If owners exist, assign the first active owner to the synthetic prospect
            active_owners = await owners.list_owners(tenant_id)
            if active_owners:
                await owners.assign_prospect(
                    tenant_id, prospect_id, owner_id=active_owners[0]["id"],
                    source="factory-test", actor=actor,
                )

            # 2. Add synthetic research evidence so personalization has proof points
            ev = EvidenceItem(
                id=new_id("evidence"),
                tenant_id=tenant_id,
                prospect_id=prospect.id,
                evidence_type="company_fact",
                claim_text=f"Synthetic onboarding verification evidence for {prospect.company_name}",
                source_url="https://example.invalid/synthetic",
                source_name="synthetic-test",
                confidence=1.0,
                verification_status="verified",
                retrieved_by=f"factory-test:{actor}",
            )
            self.session.add(ev)

            # 3. Add synthetic qualification pass
            active_profile = await config.active_profile(tenant_id)
            qual = QualificationResult(
                id=new_id("qualification"),
                tenant_id=tenant_id,
                prospect_id=prospect.id,
                icp_id=icp["id"],
                icp_version=icp.get("version"),
                profile_version=active_profile.get("version") if active_profile else None,
                score=100,
                is_qualified=True,
                matching_criteria=[{"criterion": "synthetic_test_pass", "evidence_ids": [ev.id]}],
                missing_criteria=[],
                explanation="Synthetic onboarding verification pass",
                evaluated_by=f"factory-test:{actor}",
            )
            self.session.add(qual)
            await self.session.flush()

            try:
                draft = await personalization.generate_draft(
                    tenant_id=tenant_id, prospect=prospect,
                    actor=f"factory-test:{actor}",
                )
                draft_id = draft["id"]
                gen_finding = self._finding(
                    "draft", "pass",
                    f"draft {draft_id} generated (pending review, nothing sent)",
                    blocking=True,
                )
            except SlideinError as exc:
                gen_finding = self._finding(
                    "draft", "fail",
                    f"draft blocked: {exc.code} — {exc.message}", blocking=True,
                )
            findings, _ = await self._common_findings(tenant_id, prospect)
            findings.insert(0, gen_finding)
            return await self._finish(
                tenant_id, "synthetic", findings, actor,
                {"prospect_id": prospect_id, "draft_id": draft_id},
            )
        finally:
            # Cleanup: soft-delete the synthetic prospect, reject its draft.
            prospect = await self.session.get(Prospect, prospect_id)
            if prospect is not None:
                prospect.deleted_at = utcnow()
            if draft_id is not None:
                try:
                    await personalization.reject_draft(
                        tenant_id=tenant_id, draft_id=draft_id,
                        reason="factory test cleanup",
                        actor=f"factory-test:{actor}",
                    )
                except SlideinError:
                    pass
            await self.session.flush()
