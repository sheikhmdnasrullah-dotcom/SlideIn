"""Customer-controlled, file-backed Business Brain store.

One workspace directory per tenant under a configurable root. All knowledge
reads/writes go through here; nothing is cached in memory across calls, so a
runtime restart simply re-reads the same files.

Writes are atomic (write-to-temp + fsync + rename) and validated afterwards.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..ids import new_id
from . import schema as brain_schema


FRONTMATTER_DELIMITER = "---"


class BrainNotInitialized(ValueError):
    pass


class InvalidBrain(ValueError):
    pass


class TaskTransitionError(ValueError):
    pass


@dataclass
class BrainStatus:
    tenant_id: str
    root: str
    schema_version: int
    initialized: bool
    valid: bool
    errors: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    brain_version: int = 0
    checked_at: str = ""


@dataclass
class BrainValidation:
    tenant_id: str
    ok: bool
    errors: list = field(default_factory=list)
    checked_at: str = ""


@dataclass
class BrainWriteResult:
    ok: bool
    kind: str
    version: int
    previous_version: int
    audit: list = field(default_factory=list)
    validation: BrainValidation = field(default_factory=BrainValidation)


@dataclass
class TaskRecord:
    task_id: str
    status: str
    stage: str
    tenant_id: str
    requested_outcome: str
    requested_by: str
    context_refs: list = field(default_factory=list)
    workflow_step: str = ""
    constraints: list = field(default_factory=list)
    permitted_tools: list = field(default_factory=list)
    success_criteria: list = field(default_factory=list)
    attempts: int = 0
    checkpoints: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    error: str = ""
    created_at: str = ""
    updated_at: str = ""
    version: int = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "stage": self.stage,
            "tenant_id": self.tenant_id,
            "requested_outcome": self.requested_outcome,
            "requested_by": self.requested_by,
            "context_refs": list(self.context_refs),
            "workflow_step": self.workflow_step,
            "constraints": list(self.constraints),
            "permitted_tools": list(self.permitted_tools),
            "success_criteria": list(self.success_criteria),
            "attempts": self.attempts,
            "checkpoints": list(self.checkpoints),
            "evidence_refs": list(self.evidence_refs),
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }


_TASK_FIELDS = (
    "task_id", "status", "stage", "tenant_id", "requested_outcome",
    "requested_by", "context_refs", "workflow_step", "constraints",
    "permitted_tools", "success_criteria", "attempts", "checkpoints",
    "evidence_refs", "error", "created_at", "updated_at", "version",
)


REQUIRED_FILES_CHECK = (
    "brain.md",
    "CHANGELOG.md",
    "tasks/index.md",
    "workflows/index.md",
    "knowledge/index.md",
)


class BusinessBrainStore:
    """File-backed Business Brain for one tenant workspace."""

    def __init__(self, root_base: Path) -> None:
        self._base = Path(root_base).resolve()
        self._local_lock = threading.RLock()

    # -- paths -------------------------------------------------------------

    def _root(self, tenant_id: str) -> Path:
        return self._base / brain_schema.safe_tenant_segment(tenant_id)

    def _path(self, tenant_id: str, relpath: str) -> Path:
        return self._root(tenant_id) / relpath

    def _brain_path(self, tenant_id: str) -> Path:
        return self._root(tenant_id) / "brain.md"

    def _changelog_path(self, tenant_id: str) -> Path:
        return self._root(tenant_id) / "CHANGELOG.md"

    def _task_index_path(self, tenant_id: str) -> Path:
        return self._root(tenant_id) / brain_schema.task_index_relpath()

    # -- low-level file primitives ----------------------------------------

    def _read_text(self, tenant_id: str, relpath: str) -> str:
        path = self._path(tenant_id, relpath)
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return ""
        except OSError as exc:
            raise InvalidBrain("could not read workspace file %s: %s" % (relpath, exc))

    def _write_atomic(self, tenant_id: str, relpath: str, text: str) -> None:
        path = self._path(tenant_id, relpath)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        try:
            fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    # -- frontmatter ------------------------------------------------------

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict, str]:
        if not text.startswith(FRONTMATTER_DELIMITER + "\n"):
            return {}, text
        parts = text.split("\n" + FRONTMATTER_DELIMITER + "\n", 1)
        if len(parts) != 2:
            return {}, text
        raw, body = parts[0], parts[1]
        data: dict[str, Any] = {}
        for line in raw.split("\n"):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                inner = value[1:-1].strip()
                parsed = None
                if inner:
                    try:
                        parsed = json.loads(value)
                    except (ValueError, TypeError):
                        parsed = None
                if isinstance(parsed, list):
                    data[key] = parsed
                elif inner:
                    data[key] = [v.strip().strip("'\"") for v in inner.split(",") if v.strip()]
            elif value in ("true", "false"):
                data[key] = value == "true"
            else:
                data[key] = value
        return data, body

    @staticmethod
    def _frontmatter_text(data: dict) -> str:
        lines = [FRONTMATTER_DELIMITER]
        for key, value in dict(data).items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (list, tuple)):
                items = [str(v) for v in value if str(v) != ""]
                rendered = "[" + ", ".join(items) + "]"
            else:
                rendered = str(value)
            lines.append("%s: %s" % (key, rendered))
        lines.append(FRONTMATTER_DELIMITER)
        return "\n".join(lines) + "\n"

    def _read_fact(self, tenant_id: str, kind: str) -> tuple[dict, str, bool]:
        relpath = "business/" + brain_schema.BUSINESS_FILENAMES[kind]
        text = self._read_text(tenant_id, relpath)
        data, body = self._split_frontmatter(text)
        return data, body, bool(text.strip())

    # -- brain.md ---------------------------------------------------------

    def render_brain(self, tenant_id: str, *, facts: dict, task_ids: list,
                     integrity_ok: bool, brain_version: int) -> str:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        lines: list[str] = []
        lines.append(FRONTMATTER_DELIMITER)
        lines.append("schema_version: %d" % brain_schema.BRAIN_SCHEMA_VERSION)
        lines.append("workspace: %s" % tenant_id)
        lines.append("brain_version: %d" % brain_version)
        lines.append("generated_at: %s" % now)
        lines.append(FRONTMATTER_DELIMITER)
        lines.append("")
        lines.append("# Slidein Business Brain")
        lines.append("")
        lines.append("Schema version: %d" % brain_schema.BRAIN_SCHEMA_VERSION)
        lines.append("Workspace: %s" % tenant_id)
        lines.append("Last integrity validation: %s" % ("ok" if integrity_ok else "failed"))
        lines.append("")
        lines.append("## Authoritative knowledge")
        lines.append("")
        lines.append("- [Knowledge index](knowledge/index.md)")
        lines.append("- [Workflows](workflows/index.md)")
        lines.append("- [Tasks](tasks/index.md)")
        lines.append("- [Evidence](evidence/)")
        lines.append("- [Artifacts](artifacts/)")
        lines.append("- [Schemas](schemas/)")
        lines.append("")
        lines.append("## Business facts")
        lines.append("")
        for kind in brain_schema.BUSINESS_KINDS:
            data, _body, _present = self._read_fact(tenant_id, kind)
            version = data.get("version")
            lines.append(
                "- [%s](business/%s) - schema_version %s - version %s"
                % (kind, brain_schema.BUSINESS_FILENAMES[kind], data.get("schema_version"), version)
            )
        lines.append("")
        lines.append("## Current workflow state")
        lines.append("")
        step = ""
        for task_id in task_ids:
            task = self._task_from_file(tenant_id, task_id)
            if task and task.get("status") not in ("completed", "cancelled"):
                step = str(task.get("workflow_step") or task.get("stage") or "")
        lines.append("- Current workflow step: %s" % (step or "none"))
        lines.append("")
        lines.append("## Open tasks")
        lines.append("")
        for task_id in task_ids:
            task = self._task_from_file(tenant_id, task_id)
            if task and task.get("status") in ("queued", "planning", "running", "awaiting_approval", "verifying", "failed"):
                lines.append("- [%s](tasks/%s.md) - %s - %s" % (task_id, task_id, task.get("status"), task.get("requested_outcome")))
        lines.append("")
        lines.append("## Recovery")
        lines.append("")
        lines.append("- Migration/recovery: brain schema v%d" % brain_schema.BRAIN_SCHEMA_VERSION)
        lines.append("- Last successful integrity validation: %s" % (
            "pending" if not integrity_ok else "checked"))
        lines.append("")
        return "\n".join(lines)

    # -- init / status / validate -----------------------------------------

    def init(self, tenant_id: str, *, created_by: str = "operator") -> BrainStatus:
        root = self._root(tenant_id)
        root.mkdir(parents=True, exist_ok=True)
        for sub in ("business", "workflows", "knowledge", "tasks", "evidence", "artifacts", "schemas"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        self._write_atomic(tenant_id, "brain.md", self.render_brain(
            tenant_id, facts={}, task_ids=[], integrity_ok=True, brain_version=0))
        self._write_atomic(tenant_id, "CHANGELOG.md", self._changelog_template())
        for kind in brain_schema.BUSINESS_KINDS:
            relpath = "business/" + brain_schema.BUSINESS_FILENAMES[kind]
            if not self._path(tenant_id, relpath).exists():
                self._write_atomic(tenant_id, relpath, self._fact_template(kind, version=0))
        self._write_atomic(tenant_id, brain_schema.task_index_relpath(), self._task_index_template())
        for relpath in ("workflows/index.md", "knowledge/index.md"):
            if not self._path(tenant_id, relpath).exists():
                self._write_atomic(tenant_id, relpath, self._section_template(relpath))
        return self.status(tenant_id)

    def status(self, tenant_id: str) -> BrainStatus:
        root = self._root(tenant_id)
        initialized = (root / "brain.md").exists()
        errors: list[str] = []
        files: dict[str, bool] = {}
        if not initialized:
            return BrainStatus(
                tenant_id=tenant_id, root=str(root), schema_version=brain_schema.BRAIN_SCHEMA_VERSION,
                initialized=False, valid=False, errors=["brain.md is missing"],
                files=files, brain_version=0, checked_at="",
            )
        validation = self.validate(tenant_id)
        errors = list(validation.errors)
        brain_version = 0
        data, _body, _present = self._read_fact(tenant_id, "profile")
        brain_version = int(data.get("version") or 0)
        for relpath in REQUIRED_FILES_CHECK:
            files[relpath] = self._path(tenant_id, relpath).exists()
        return BrainStatus(
            tenant_id=tenant_id, root=str(root), schema_version=brain_schema.BRAIN_SCHEMA_VERSION,
            initialized=True, valid=not errors, errors=errors, files=files,
            brain_version=brain_version, checked_at=validation.checked_at,
        )

    def validate(self, tenant_id: str) -> BrainValidation:
        checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        errors: list[str] = []
        brain_path = self._brain_path(tenant_id)
        if not brain_path.exists():
            return BrainValidation(tenant_id=tenant_id, ok=False, errors=["brain.md is missing"], checked_at=checked_at)
        try:
            text = brain_path.read_text(encoding="utf-8")
        except OSError as exc:
            return BrainValidation(tenant_id=tenant_id, ok=False, errors=["brain.md unreadable: %s" % exc], checked_at=checked_at)
        data, _body = self._split_frontmatter(text)
        if str(data.get("schema_version")) != str(brain_schema.BRAIN_SCHEMA_VERSION):
            errors.append("brain.md schema_version must be %d" % brain_schema.BRAIN_SCHEMA_VERSION)
        for relpath in brain_schema.REQUIRED_BUSINESS_FILES:
            if not self._path(tenant_id, relpath).exists():
                errors.append("required workspace file missing: %s" % relpath)
        for kind in brain_schema.BUSINESS_KINDS:
            relpath = "business/" + brain_schema.BUSINESS_FILENAMES[kind]
            path = self._path(tenant_id, relpath)
            if not path.exists():
                errors.append("required business file missing: %s" % relpath)
                continue
            try:
                fdata, _fbody = self._split_frontmatter(path.read_text(encoding="utf-8"))
            except OSError as exc:
                errors.append("business file %s unreadable: %s" % (relpath, exc))
                continue
            required_keys = brain_schema.REQUIRED_KEYS.get(kind, set())
            for key in sorted(required_keys):
                if key not in fdata or fdata.get(key) is None:
                    errors.append("business file %s missing required field %r" % (relpath, key))
        tasks_dir = self._root(tenant_id) / "tasks"
        if tasks_dir.exists():
            for entry in sorted(tasks_dir.glob("task_*.md")):
                if not entry.name.endswith(".md") or entry.name == "index.md":
                    continue
                try:
                    tdata, _tbody = self._split_frontmatter(entry.read_text(encoding="utf-8"))
                except OSError:
                    errors.append("task file %s unreadable" % entry.name)
                    continue
                if str(tdata.get("status")) not in brain_schema.TASK_STATUSES:
                    errors.append("task %s has invalid status %r" % (entry.name, tdata.get("status")))
                if not str(tdata.get("requested_outcome") or "").strip():
                    errors.append("task %s missing requested_outcome" % entry.name)
        return BrainValidation(tenant_id=tenant_id, ok=not errors, errors=errors, checked_at=checked_at)

    # -- facts -------------------------------------------------------------

    def read_facts(self, tenant_id: str) -> dict:
        facts: dict[str, dict] = {}
        for kind in brain_schema.BUSINESS_KINDS:
            data, _body, present = self._read_fact(tenant_id, kind)
            facts[kind] = dict(data) if present else {}
        return facts

    def write_fact(self, tenant_id: str, kind: str, fact: dict, *, actor: str,
                   reason: str = "") -> BrainWriteResult:
        if kind not in brain_schema.BUSINESS_KINDS:
            raise InvalidBrain("unknown business kind %r" % (kind,))
        relpath = "business/" + brain_schema.BUSINESS_FILENAMES[kind]
        existing_data, existing_body, _present = self._read_fact(tenant_id, kind)
        merged_in = brain_schema.normalise_fact(kind, fact)
        new_version = int(existing_data.get("version") or 0) + 1
        data = dict(existing_data)
        data.update(merged_in)
        data["schema_version"] = brain_schema.BRAIN_SCHEMA_VERSION
        data["version"] = new_version
        data["kind"] = kind
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["updated_by"] = actor
        text = self._frontmatter_text(data) + "\n" + self._fact_body(kind, merged_in, data)
        self._write_atomic(tenant_id, relpath, text)
        required_keys = brain_schema.REQUIRED_KEYS.get(kind, frozenset())
        missing = [k for k in sorted(required_keys) if not merged_in.get(k)]
        if missing:
            raise InvalidBrain(
                "business kind %r is missing required fields: %s" % (kind, ", ".join(missing)))
        audit = self._append_changelog(tenant_id, kind=kind, version=new_version, actor=actor, reason=reason)
        validation = self.validate(tenant_id)
        return BrainWriteResult(
            ok=validation.ok, kind=kind, version=new_version,
            previous_version=int(existing_data.get("version") or 0),
            audit=audit, validation=validation,
        )

    def _changelog_template(self) -> str:
        return (
            "---\n"
            "schema_version: %d\n"
            "workspace: \n"
            "generated_at: \n"
            "---\n"
            "\n"
            "# Business Brain Change Log\n"
            "\n"
            "- %s - no prior changes recorded\n"
            % (brain_schema.BRAIN_SCHEMA_VERSION, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        )

    def _append_changelog(self, tenant_id: str, *, kind: str, version: int,
                          actor: str, reason: str) -> list:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        entry = "- %s - kind=%s version=%d actor=%s reason=%s\n" % (stamp, kind, version, actor, reason)
        path = self._changelog_path(tenant_id)
        existing = self._read_text(tenant_id, "CHANGELOG.md")
        text = existing.rstrip("\n") + "\n" + entry
        self._write_atomic(tenant_id, "CHANGELOG.md", text)
        return [entry.strip()]

    def _fact_template(self, kind: str, *, version: int) -> str:
        relpath = "business/" + brain_schema.BUSINESS_FILENAMES[kind]
        data: dict[str, Any] = {
            "schema_version": brain_schema.BRAIN_SCHEMA_VERSION,
            "kind": kind,
            "version": version,
        }
        for key in sorted(brain_schema.REQUIRED_KEYS.get(kind, set())):
            data[key] = ""
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["updated_by"] = "system"
        body = self._fact_body(kind, {}, data)
        return self._frontmatter_text(data) + "\n" + body

    def _fact_body(self, kind: str, fact: dict, data: dict) -> str:
        title = {
            "profile": "Business Profile",
            "offers": "Offers",
            "icp": "Ideal Customer Profile",
            "policies": "Policies",
            "integrations": "Integrations",
        }.get(kind, kind.title())
        lines = ["# " + title, ""]
        lines.append("Schema version: %d" % brain_schema.BRAIN_SCHEMA_VERSION)
        lines.append("Version: %d" % int(data.get("version") or 0))
        lines.append("")
        keys = sorted(
            set(brain_schema.REQUIRED_KEYS.get(kind, set()))
            | {k for k, v in dict(fact).items() if v not in (None, "", [])}
        )
        for key in keys:
            value = data.get(key)
            rendered = ", ".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value or "")
            if not rendered:
                continue
            lines.append("- **%s**: %s" % (key, rendered))
        lines.append("")
        return "\n".join(lines)

    def _section_template(self, relpath: str) -> str:
        return "# Section\n\nSchema version: %d\n\n- placeholder entry\n" % brain_schema.BRAIN_SCHEMA_VERSION

    # -- task records -----------------------------------------------------

    def _task_text(self, task: TaskRecord) -> str:
        data = task.to_dict()
        lines = [FRONTMATTER_DELIMITER]
        for key in _TASK_FIELDS:
            value = data[key]
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, (list, tuple)):
                rendered = json.dumps([str(v) for v in value])
            else:
                rendered = str(value)
            lines.append("%s: %s" % (key, rendered))
        lines.append(FRONTMATTER_DELIMITER)
        body = [
            "# Task " + str(task.task_id),
            "",
            "## Requested outcome",
            str(task.requested_outcome or ""),
            "",
            "## Workflow step",
            str(task.workflow_step or task.stage or ""),
            "",
            "## Success criteria",
        ]
        for criterion in task.success_criteria or []:
            body.append("- " + str(criterion))
        body.append("")
        return "\n".join(lines) + "\n" + "\n".join(body) + "\n"

    def _task_from_file(self, tenant_id: str, task_id: str) -> dict:
        path = self._root(tenant_id) / "tasks" / (task_id + ".md")
        if not path.exists():
            raise KeyError(task_id)
        text = path.read_text(encoding="utf-8")
        data, _body = self._split_frontmatter(text)
        task = TaskRecord(
            task_id=str(data.get("task_id") or task_id),
            status=str(data.get("status") or "queued"),
            stage=str(data.get("stage") or "configure"),
            tenant_id=str(data.get("tenant_id") or tenant_id),
            requested_outcome=str(data.get("requested_outcome") or ""),
            requested_by=str(data.get("requested_by") or "operator"),
        )
        for key in _TASK_FIELDS:
            task.__dict__[key] = data.get(key) if key not in ("task_id",) else str(data.get("task_id") or task_id)
        task.context_refs = list(task.context_refs or [])
        task.checkpoints = list(task.checkpoints or [])
        task.evidence_refs = list(task.evidence_refs or [])
        task.constraints = list(task.constraints or [])
        task.permitted_tools = list(task.permitted_tools or [])
        task.success_criteria = list(task.success_criteria or [])
        task.attempts = int(task.attempts or 0)
        task.version = int(task.version or 0)
        task.created_at = str(task.created_at or "")
        task.updated_at = str(task.updated_at or "")
        task.error = str(task.error or "")
        task.stage = str(task.stage or task.workflow_step or "configure")
        task.workflow_step = str(task.workflow_step or task.stage or "configure")
        task.requested_by = str(task.requested_by or "operator")
        task.tenant_id = str(task.tenant_id or tenant_id)
        task.status = str(task.status or "queued")
        task.requested_outcome = str(task.requested_outcome or "")
        return task.to_dict()

    def _task_index_template(self) -> str:
        return "# Tasks\n\nSchema version: %d\n\n- none\n" % brain_schema.BRAIN_SCHEMA_VERSION

    def _write_task_index(self, tenant_id: str, task_ids: list) -> None:
        text = "# Tasks\n\nSchema version: %d\n\n" % brain_schema.BRAIN_SCHEMA_VERSION
        if not task_ids:
            text += "- none\n"
        else:
            for task_id in sorted(task_ids):
                text += "- %s\n" % task_id
        self._write_atomic(tenant_id, brain_schema.task_index_relpath(), text)

    def create_task(self, tenant_id: str, *, requested_outcome: str, workflow_step: str,
                    success_criteria, constraints=None, permitted_tools=None,
                    context_refs=None, actor: str = "operator") -> TaskRecord:
        task_id = new_id("task")
        task = TaskRecord(
            task_id=task_id,
            status="queued",
            stage=workflow_step,
            tenant_id=tenant_id,
            requested_outcome=requested_outcome,
            requested_by=actor,
            context_refs=list(context_refs or []),
            workflow_step=workflow_step,
            constraints=list(constraints or []),
            permitted_tools=list(permitted_tools or []),
            success_criteria=list(success_criteria or []),
            attempts=0,
            checkpoints=[],
            evidence_refs=[],
            error="",
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            version=0,
        )
        self._write_atomic(tenant_id, brain_schema.task_relpath(task_id), self._task_text(task))
        self._write_task_index(tenant_id, [task.task_id])
        return task

    def get_task(self, tenant_id: str, task_id: str) -> TaskRecord:
        task = self._task_from_file(tenant_id, task_id)
        return TaskRecord(**task)

    def list_tasks(self, tenant_id: str) -> list[TaskRecord]:
        tasks_dir = self._root(tenant_id) / "tasks"
        found: list[TaskRecord] = []
        if not tasks_dir.exists():
            return found
        for entry in sorted(tasks_dir.glob("task_*.md")):
            task = self._task_from_file(tenant_id, entry.stem)
            found.append(TaskRecord(**task))
        return found

    def transition_task(self, tenant_id: str, task_id: str, to: str, *,
                        actor: str = "operator", reason: str = "") -> TaskRecord:
        task = self.get_task(tenant_id, task_id)
        allowed = brain_schema.TASK_TRANSITIONS.get(task.status, ())
        if to not in allowed:
            raise TaskTransitionError(
                "task %s cannot transition from %s to %s" % (task_id, task.status, to))
        if to == "completed" and not task.success_criteria:
            raise TaskTransitionError(
                "task %s cannot complete without success criteria" % task_id)
        from_status = task.status
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        task.status = to
        task.updated_at = now
        task.version = int(task.version or 0) + 1
        task.updated_by = actor
        task.error = ""
        if to == "running":
            task.attempts = int(task.attempts or 0) + 1
            task.checkpoints = list(task.checkpoints or []) + [{
                "at": now, "actor": actor, "from_status": from_status,
                "note": reason or ("task %s started attempt %d" % (task_id, task.attempts)),
            }]
        self._write_atomic(tenant_id, brain_schema.task_relpath(task_id), self._task_text(task))
        task_ids = [t.task_id for t in self.list_tasks(tenant_id)]
        self._write_task_index(tenant_id, task_ids)
        return task



def get_store(root_base) -> BusinessBrainStore:
    return BusinessBrainStore(Path(root_base))


def get_brain(tenant_id: str, root_base=None):
    store = get_store(root_base or os.environ.get("SLIDEIN_WORKSPACE_ROOT") or str(Path(__file__).resolve().parents[2] / "data" / "slidein-workspaces"))
    return store
