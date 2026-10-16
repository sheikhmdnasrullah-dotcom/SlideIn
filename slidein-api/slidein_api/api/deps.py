"""Shared route dependencies: module access gates.

Every section entry point and stage action calls `module_gate` with the
module(s) it fronts. Cross-tenant isolation stays in `resolve_workspace`
and role checks stay in `require_role`; this layer answers only "did this
workspace enable this module?".

Mapping policy (see WHITELABEL_TARGET_ARCHITECTURE.md):

* stage actions (discover/research/qualify/personalize/approve/send) are
  gated on their own module;
* shared record reads (prospects, drafts) require ANY of the modules that
  front them;
* machine ingress (`POST /webhooks/inbound`) is intentionally ungated:
  suppression and opt-out are compliance actions that must apply even when
  the inbox section is hidden.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..services.modules import check_any_module_enabled, check_module_enabled
from ..services.templates import TemplateService


async def module_gate(
    session: AsyncSession, tenant_id: str, *module_ids: str
) -> None:
    """Enforce module access server-side against EFFECTIVE modules
    (tenant settings over template defaults over the full set).

    Raises `SlideinError` (`not_authorized` → 403, unknown module → 400),
    converted by the app-level exception handler like `require_role`.
    """
    effective = await TemplateService(session).effective(tenant_id)
    stored = {"enabled": effective["modules"]["enabled"]}
    if len(module_ids) == 1:
        check_module_enabled(stored, module_ids[0])
    else:
        check_any_module_enabled(stored, list(module_ids))
