"""Customer-controlled Business Brain routes.

File-backed workspace surface: init/status/validate, authoritative business
fact writes (structured, atomic, audited), and durable task records with a
validated lifecycle.

Every handler is tenant-bound through `require_auth`; the workspace is always
the caller tenant's own Business Brain.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from ...business_brain import (
    BusinessBrainStore,
    InvalidBrain,
    TaskTransitionError,
)
from ...business_brain.store import (
    BrainStatus,
    BrainWriteResult,
)
from ...errors import SlideinError
from ...security import AuthContext, require_auth

router = APIRouter()

_DEFAULT_WORKSPACE_ROOT = str(
    Path(os.environ.get("SLIDEIN_WORKSPACE_ROOT")
         or (Path(__file__).resolve().parents[3] / "data" / "slidein-workspaces"))
)


def _store() -> BusinessBrainStore:
    return BusinessBrainStore(Path(os.environ.get("SLIDEIN_WORKSPACE_ROOT") or _DEFAULT_WORKSPACE_ROOT))


def _to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, SlideinError):
        status = 404 if exc.code in ("tenant_forbidden", "not_found") else (
            403 if exc.code in ("not_authorized", "session_invalid") else 400
        )
        return HTTPException(status_code=status, detail=exc.to_dict())
    if isinstance(exc, (InvalidBrain, ValueError, TaskTransitionError)):
        return HTTPException(status_code=422, detail={
            "code": "brain_invalid",
            "message": str(exc),
            "details": {},
            "recovery_action": "inspect_workspace",
            "retryable": False,
        })
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail={
            "code": "brain_task_not_found",
            "message": str(exc),
            "details": {},
            "recovery_action": "return_to_task_list",
            "retryable": False,
        })
    return HTTPException(status_code=500, detail={
        "code": "brain_unknown", "message": str(exc), "details": {},
        "recovery_action": "retry_stage", "retryable": True,
    })


def _status_to_dict(status: BrainStatus) -> dict:
    return {
        "tenant_id": status.tenant_id,
        "workspace_root": status.root,
        "schema_version": status.schema_version,
        "initialized": status.initialized,
        "valid": status.valid,
        "errors": list(status.errors),
        "files": {k: bool(v) for k, v in status.files.items()},
        "brain_version": status.brain_version,
        "checked_at": status.checked_at,
    }


@router.post("/brain/init")
async def brain_init(auth: AuthContext = Depends(require_auth)) -> dict:
    status = _store().init(auth.tenant_id, created_by=auth.email or auth.user_id or "operator")
    return _status_to_dict(status)


@router.get("/brain")
async def brain_status(auth: AuthContext = Depends(require_auth)) -> dict:
    status = _store().status(auth.tenant_id)
    return _status_to_dict(status)


@router.get("/brain/facts")
async def brain_facts(auth: AuthContext = Depends(require_auth)) -> dict:
    store = _store()
    status = store.status(auth.tenant_id)
    if not status.initialized:
        return {
            "tenant_id": auth.tenant_id,
            "initialized": False,
            "valid": False,
            "errors": list(status.errors),
            "facts": {},
        }
    return {"tenant_id": auth.tenant_id, "initialized": True, "valid": status.valid, "facts": store.read_facts(auth.tenant_id)}


@router.post("/brain/facts")
async def brain_write_fact(body: dict, auth: AuthContext = Depends(require_auth)) -> dict:
    store = _store()
    try:
        result: BrainWriteResult = store.write_fact(
            auth.tenant_id,
            kind=str(body.get("kind") or ""),
            fact=dict(body.get("fact") or {}),
            actor=str(body.get("actor") or auth.email or auth.user_id or "operator"),
            reason=str(body.get("reason") or "api write"),
        )
    except Exception as exc:
        raise _to_http(exc)
    return {
        "ok": result.ok,
        "kind": result.kind,
        "version": result.version,
        "previous_version": result.previous_version,
        "audit": list(result.audit),
        "validation": {
            "ok": result.validation.ok,
            "errors": list(result.validation.errors),
        },
        "fact": store.read_facts(auth.tenant_id).get(result.kind, {}),
    }


@router.get("/brain/tasks")
async def brain_list_tasks(
    status: str | None = Query(default=None, alias="status"),
    auth: AuthContext = Depends(require_auth),
) -> dict:
    store = _store()
    tasks = store.list_tasks(auth.tenant_id)
    if status:
        tasks = [t for t in tasks if t.status == status]
    return {
        "tenant_id": auth.tenant_id,
        "tasks": [t.to_dict() for t in tasks],
        "count": len(tasks),
    }


@router.post("/brain/tasks")
async def brain_create_task(body: dict, auth: AuthContext = Depends(require_auth)) -> dict:
    store = _store()
    task = store.create_task(
        auth.tenant_id,
        requested_outcome=str(body.get("requested_outcome") or ""),
        workflow_step=str(body.get("workflow_step") or "configure"),
        success_criteria=list(body.get("success_criteria") or []),
        constraints=list(body.get("constraints") or []),
        permitted_tools=list(body.get("permitted_tools") or []),
        context_refs=list(body.get("context_refs") or []),
        actor=str(body.get("actor") or auth.email or auth.user_id or "operator"),
    )
    return task.to_dict()


@router.get("/brain/tasks/{task_id}")
async def brain_get_task(task_id: str, auth: AuthContext = Depends(require_auth)) -> dict:
    try:
        task = _store().get_task(auth.tenant_id, task_id)
    except Exception as exc:
        raise _to_http(exc)
    return task.to_dict()


@router.post("/brain/tasks/{task_id}/transition")
async def brain_transition_task(task_id: str, body: dict, auth: AuthContext = Depends(require_auth)) -> dict:
    store = _store()
    try:
        task = store.transition_task(
            auth.tenant_id,
            task_id,
            str(body.get("to") or ""),
            actor=str(body.get("actor") or auth.email or auth.user_id or "operator"),
            reason=str(body.get("reason") or ""),
        )
    except Exception as exc:
        raise _to_http(exc)
    return task.to_dict()
