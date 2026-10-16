"""System routes: health, machine-readable stage contracts, template catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette import status as http_status

from ...contracts import CONTRACTS, HANDOFFS, StageName
from ...db import session_scope
from ...errors import SlideinError
from ...security import auth_mode, require_auth
from ...services.templates import TemplateService

router = APIRouter()


@router.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "healthy", "service": "slidein-api", "version": "1.0.0"}


def _contract_payload(contract) -> dict:
    return {
        "stage": contract.stage.value,
        "title": contract.title,
        "summary": contract.summary,
        "requires": [
            {
                "name": f.name,
                "kind": f.kind.value,
                "required": f.required,
                "description": f.description,
            }
            for f in contract.requires
        ],
        "produces": [
            {
                "name": f.name,
                "kind": f.kind.value,
                "required": f.required,
                "description": f.description,
            }
            for f in contract.produces
        ],
        "transitions": [list(t) for t in contract.transitions],
        "failures": [
            {
                "code": f.code,
                "retryable": f.retryable,
                "recovery_action": f.recovery_action,
                "description": f.description,
            }
            for f in contract.failures
        ],
        "needs_review_when": list(contract.needs_review_when),
        "permission": contract.permission,
        "max_attempts": contract.max_attempts,
        "notes": contract.notes,
    }


@router.get("/contracts", tags=["system"])
async def list_contracts() -> dict:
    """The contracts the workflow enforces, in the same order the stages run."""
    return {
        "stages": [_contract_payload(CONTRACTS[s]) for s in StageName],
        "handoffs": [
            {
                "from": h.from_stage.value,
                "to": h.to_stage.value,
                "carried": list(h.carried),
                "blocked_by": list(h.blocked_by),
            }
            for h in HANDOFFS
        ],
    }


@router.get("/session", tags=["system"])
async def session(request_state=Depends(require_auth)) -> dict:
    auth = request_state
    return {"auth": auth.to_dict(), "auth_mode": auth_mode()}


@router.get("/templates", tags=["system"])
async def list_templates(request_state=Depends(require_auth)) -> dict:
    """Workspace template catalog: versioned starting points per industry."""
    async with session_scope() as session:
        templates = await TemplateService(session).list_templates()
    return {"templates": templates}


@router.get("/templates/{template_id}", tags=["system"])
async def get_template_doc(
    template_id: str, request_state=Depends(require_auth)
) -> dict:
    async with session_scope() as session:
        try:
            doc = await TemplateService(session).get_template(template_id)
        except SlideinError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND, detail=exc.to_dict()
            )
    return {"template": doc}
