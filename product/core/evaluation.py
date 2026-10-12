"""Slidein universal core — cross-business evaluation framework.

A shared change is not successful because it helps the first tenant; it is
successful when it helps (or at least does not regress) a representative
set of materially different business contexts. EvalSuite encodes that:

- Cases carry provenance: synthetic, platform telemetry, or explicitly
  authorized tenant data. Anything else is rejected at admission.
- Suites are versioned; evaluation records reference suite versions so a
  release's evidence is reproducible.
- run() executes a workflow callable per case and reports per-context
  pass rates; check_regressions() compares ID-matched cases against a
  baseline and fails on any regression.

See docs/engineering/CROSS_BUSINESS_EVALUATION.md.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum


from product.core.errors import ProvenanceError


class EvalContext(str, Enum):
    """Materially different business contexts used as evaluation examples.
    These are dataset labels, not product branches — the workflow must not
    contain per-context conditional logic (see product.core.workflow)."""

    PROFESSIONAL_SERVICES = "professional_services"
    B2B_SAAS = "b2b_saas"
    REAL_ESTATE = "real_estate"
    BUSINESS_CONSULTING = "business_consulting"


class CaseProvenance(str, Enum):
    SYNTHETIC = "synthetic"
    PLATFORM_TELEMETRY = "platform_telemetry"
    AUTHORIZED_TENANT_DATA = "authorized_tenant_data"
    UNAUTHORIZED = "unauthorized"


@dataclass(frozen=True)
class EvalCase:
    """One reproducible check. `check` receives the workflow output for
    `input` and returns True when the expectation holds."""

    id: str
    context: EvalContext
    name: str
    input: dict[str, object]
    check: Callable[[dict[str, object]], bool]
    provenance: CaseProvenance
    authorization_ref: str = ""  # required when provenance is tenant data


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    context: EvalContext
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class SuiteReport:
    suite_name: str
    suite_version: int
    results: tuple[CaseResult, ...]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    def pass_rate(self, context: EvalContext | None = None) -> float:
        subset = [r for r in self.results if context is None or r.context is context]
        if not subset:
            return 1.0
        return sum(1 for r in subset if r.passed) / len(subset)

    def contexts_covered(self) -> frozenset[EvalContext]:
        return frozenset(r.context for r in self.results)


class EvalSuite:
    """Versioned, provenance-guarded evaluation suite."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._version = 1
        self._cases: dict[str, EvalCase] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> int:
        return self._version

    @property
    def cases(self) -> tuple[EvalCase, ...]:
        return tuple(self._cases.values())

    def add_case(self, case: EvalCase) -> EvalCase:
        """Admit a case. Tenant-sourced cases require an authorization
        reference; unauthorized material is rejected, not laundered."""
        if case.provenance is CaseProvenance.UNAUTHORIZED:
            raise ProvenanceError(
                f"case {case.id!r} has unauthorized provenance and cannot "
                f"enter shared evaluation"
            )
        if (
            case.provenance is CaseProvenance.AUTHORIZED_TENANT_DATA
            and not case.authorization_ref
        ):
            raise ProvenanceError(
                f"tenant-sourced case {case.id!r} requires an authorization_ref"
            )
        if case.id in self._cases:
            raise ProvenanceError(f"duplicate case id {case.id!r} in {self._name}")
        self._cases[case.id] = case
        self._version += 1
        return case

    def run(
        self, workflow: Callable[[dict[str, object]], dict[str, object]]
    ) -> SuiteReport:
        """Execute every case against the given workflow callable. Any
        exception in the workflow or the check counts as a failure, with
        the detail preserved."""
        results: list[CaseResult] = []
        for case in self._cases.values():
            try:
                output = workflow(copy.deepcopy(case.input))
                passed = bool(case.check(output))
                detail = "" if passed else "check returned False"
            except Exception as exc:  # noqa: BLE001 - evaluation must not crash
                passed = False
                detail = f"{type(exc).__name__}: {exc}"
            results.append(
                CaseResult(
                    case_id=case.id, context=case.context, passed=passed, detail=detail
                )
            )
        return SuiteReport(
            suite_name=self._name, suite_version=self._version, results=tuple(results)
        )


def check_regressions(baseline: SuiteReport, candidate: SuiteReport) -> tuple[str, ...]:
    """Return the IDs of cases that passed in the baseline but fail in the
    candidate report. A non-empty tuple means the shared change regresses
    at least one covered context and must not ship as-is."""
    if baseline.suite_name != candidate.suite_name:
        raise ProvenanceError("cannot compare reports from different suites")
    before = {r.case_id: r.passed for r in baseline.results}
    return tuple(
        r.case_id
        for r in candidate.results
        if before.get(r.case_id, False) is True and not r.passed
    )
