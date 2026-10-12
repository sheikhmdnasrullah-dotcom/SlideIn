"""Slidein universal core — industry-neutral workflow runner.

The shared workflow is a fixed stage pipeline:

    DISCOVER -> RESEARCH -> QUALIFY -> MATCH_OFFER -> PERSONALIZE ->
    VALIDATE -> EXECUTE -> MEASURE

Industry and tenant differences enter only as *data* (TenantContext,
SharedDefaultsRegistry content, stage inputs), never as conditional
branches in this runner. run() executes every registered stage in order
for every tenant; a tenant that needs different behavior gets different
configuration, a different adapter behind a stage interface, or — after
classification — a new versioned core capability. See
docs/architecture/CORE_VS_TENANT_BOUNDARIES.md.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum


STAGES: tuple[str, ...] = (
    "discover",
    "research",
    "qualify",
    "match_offer",
    "personalize",
    "validate",
    "execute",
    "measure",
)


class Stage(str, Enum):
    DISCOVER = "discover"
    RESEARCH = "research"
    QUALIFY = "qualify"
    MATCH_OFFER = "match_offer"
    PERSONALIZE = "personalize"
    VALIDATE = "validate"
    EXECUTE = "execute"
    MEASURE = "measure"


@dataclass(frozen=True)
class StageRecord:
    stage: Stage
    tenant_id: str
    input_keys: tuple[str, ...]
    output_keys: tuple[str, ...]


@dataclass
class WorkflowRun:
    """Mutable accumulator passed through stages. Stages read tenant
    context and shared config from here and append their outputs."""

    tenant_id: str
    tenant_context: object
    shared_snapshot: Mapping[str, object]
    state: dict[str, object] = field(default_factory=dict)
    stages_executed: list[StageRecord] = field(default_factory=list)


StageFn = Callable[[WorkflowRun], Mapping[str, object]]


class UniversalWorkflow:
    """Runs the same stage pipeline for every tenant.

    `stages` maps each Stage to its implementation. Implementations may
    read tenant data, but this runner performs no tenant- or
    industry-conditional dispatch — that is the property the
    architecture tests assert.
    """

    def __init__(self, stages: Mapping[Stage, StageFn]) -> None:
        missing = [s for s in Stage if s not in stages]
        if missing:
            raise ValueError(
                f"workflow is missing stages: {[s.value for s in missing]}"
            )
        self._stages = dict(stages)

    @property
    def stage_order(self) -> tuple[Stage, ...]:
        return tuple(Stage(s) for s in STAGES)

    def run(self, run: WorkflowRun) -> WorkflowRun:
        for stage in self.stage_order:
            fn = self._stages[stage]
            before = set(run.state)
            output = fn(run)
            if not isinstance(output, Mapping):
                raise TypeError(f"stage {stage.value} must return a mapping")
            for key, value in output.items():
                run.state[f"{stage.value}.{key}"] = copy.deepcopy(value)
            run.stages_executed.append(
                StageRecord(
                    stage=stage,
                    tenant_id=run.tenant_id,
                    input_keys=tuple(sorted(before)),
                    output_keys=tuple(sorted(str(k) for k in output)),
                )
            )
        return run
