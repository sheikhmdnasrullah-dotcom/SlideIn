"""System routes: health, and the machine-readable stage contracts."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...contracts import CONTRACTS, HANDOFFS, StageName
from ...security import auth_mode, require_auth

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
