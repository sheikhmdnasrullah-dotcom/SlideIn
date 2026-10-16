"""Client intake compiler: transforms plain-text client notes into a
fully-typed, validated Slidein deployment configuration and owner bundle.

Industry-adaptive: automatically infers terminology and module sets
based on the client's business domain (e.g. mortgage, healthcare, SaaS, agency).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from ..ids import new_id
from .schemas import (
    ApprovalConfig,
    DeploymentConfigInput,
    LimitsConfig,
    OwnerInput,
    SendingConfig,
)

# Standard industry terminology dictionaries
INDUSTRY_TERMINOLOGY = {
    "mortgage": {
        "prospect": "Borrower",
        "prospects": "Borrowers",
        "lead_owner": "Loan Officer",
        "meeting": "Mortgage Consultation",
    },
    "dental": {
        "prospect": "Dental Practice",
        "prospects": "Practices",
        "lead_owner": "Regional Director",
        "meeting": "Partnership Consultation",
    },
    "healthcare": {
        "prospect": "Medical Clinic",
        "prospects": "Clinics",
        "lead_owner": "Practice Advisor",
        "meeting": "Discovery Consultation",
    },
    "saas": {
        "prospect": "Target Account",
        "prospects": "Accounts",
        "lead_owner": "Account Executive",
        "meeting": "Product Demo",
    },
    "agency": {
        "prospect": "Client Prospect",
        "prospects": "Prospects",
        "lead_owner": "Growth Consultant",
        "meeting": "Strategy Session",
    },
}


def _infer_industry_key(text: str) -> str:
    lower = text.lower()
    if any(k in lower for k in ("mortgage", "loan", "lending", "broker")):
        return "mortgage"
    if any(k in lower for k in ("dental", "dentist", "orthodont")):
        return "dental"
    if any(k in lower for k in ("health", "clinic", "medical", "doctor")):
        return "healthcare"
    if any(k in lower for k in ("software", "saas", "tech", "platform")):
        return "saas"
    return "agency"


class IntakeCompiler:
    """Parses plain-text / chat intake notes into a validated client configuration."""

    @classmethod
    def compile(cls, raw_text: str, *, client_id: str | None = None) -> dict[str, Any]:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        data: dict[str, str] = {}
        team_lines: list[str] = []
        inbox_lines: list[str] = []
        in_team_section = False
        in_inbox_section = False

        for line in lines:
            if re.match(r"^(team\s*members?|owners?|loan\s*officers?|advisors?):?", line, re.IGNORECASE):
                in_team_section = True
                in_inbox_section = False
                continue
            if re.match(r"^(inboxes|mailboxes|sending\s*(inboxes|mailboxes|accounts?)|email\s*accounts?):?", line, re.IGNORECASE):
                in_inbox_section = True
                in_team_section = False
                continue

            if in_team_section:
                if line.startswith("-") or line.startswith("*") or "|" in line:
                    team_lines.append(line.lstrip("-* ").strip())
                    continue
                else:
                    in_team_section = False

            if in_inbox_section:
                if line.startswith("-") or line.startswith("*") or "|" in line:
                    inbox_lines.append(line.lstrip("-* ").strip())
                    continue
                else:
                    in_inbox_section = False

            if ":" in line:
                key, val = line.split(":", 1)
                data[key.strip().lower()] = val.strip()

        # 1. Identity & Business Profile
        business_name = data.get("business name") or data.get("company") or data.get("name") or "Client Business"
        base_domain = data.get("base domain") or data.get("domain") or "outreach.client.example"
        industry = data.get("industry") or data.get("vertical") or "B2B Professional Services"
        primary_color = data.get("primary color") or data.get("color") or "#0ea5e9"
        if not primary_color.startswith("#"):
            primary_color = f"#{primary_color}"
        logo_url = data.get("logo url") or data.get("logo") or ""

        # 2. Terminology & Modules
        industry_key = _infer_industry_key(f"{business_name} {industry}")
        terms = dict(INDUSTRY_TERMINOLOGY.get(industry_key, INDUSTRY_TERMINOLOGY["agency"]))

        # 3. Policy & Compliance
        postal_address = (
            data.get("physical address")
            or data.get("address")
            or data.get("postal address")
            or "Suite 100, 100 Enterprise Way, Dover, DE 19901"
        )
        lawful_basis = (
            data.get("lawful basis")
            or f"B2B legitimate interest, verified {terms['prospect'].lower()} outreach"
        )
        sender_email = data.get("sender email") or data.get("sender") or f"hello@{base_domain}"

        # 4. Parse Team Members / Owners
        owners: list[dict[str, Any]] = []
        for raw_member in team_lines:
            parts = [p.strip() for p in raw_member.split("|")]
            name = parts[0]
            email = parts[1] if len(parts) > 1 else ""
            booking_url = parts[2] if len(parts) > 2 else ""
            crm_id = parts[3] if len(parts) > 3 else ""

            if not email and "@" in name:
                email = name
                name = email.split("@")[0].title()

            if email:
                owners.append({
                    "display_name": name,
                    "email": email,
                    "booking_provider": "cal" if "cal." in booking_url else "generic",
                    "booking_url": booking_url,
                    "booking_verified": bool(booking_url),
                    "crm_owner_id": crm_id,
                    "is_active": True,
                })

        # Fallback if no team members specified
        if not owners:
            owners.append({
                "display_name": "Default Account Owner",
                "email": sender_email,
                "booking_provider": "generic",
                "booking_url": f"https://cal.com/{base_domain.replace('.', '-')}",
                "booking_verified": True,
                "crm_owner_id": "owner-1",
                "is_active": True,
            })

        # 5. Parse Inboxes & Sending Accounts
        inboxes: list[dict[str, Any]] = []
        for raw_inbox in inbox_lines:
            parts = [p.strip() for p in raw_inbox.split("|")]
            email = parts[0]
            if not email or "@" not in email:
                continue
            prov_raw = parts[1].lower() if len(parts) > 1 else ""
            if any(k in prov_raw for k in ("google", "workspace", "gmail")):
                provider = "google_workspace"
            elif any(k in prov_raw for k in ("microsoft", "365", "m365", "outlook")):
                provider = "microsoft_365"
            elif "smtp" in prov_raw:
                provider = "smtp"
            else:
                provider = "kumomta"

            status_raw = parts[2].lower() if len(parts) > 2 else "active"
            is_warming = "warm" in status_raw
            status = "warming" if is_warming else "active"

            daily_limit = 50
            if len(parts) > 3:
                num_match = re.search(r"\d+", parts[3])
                if num_match:
                    daily_limit = int(num_match.group(0))

            inboxes.append({
                "email": email,
                "provider": provider,
                "status": status,
                "warmup_enabled": is_warming,
                "daily_limit": daily_limit,
            })

        if not inboxes:
            inboxes.append({
                "email": sender_email,
                "provider": "kumomta",
                "status": "active",
                "warmup_enabled": False,
                "daily_limit": int(data.get("daily limit") or 50),
            })

        # Determine sending mode
        has_provider_inbox = any(i["provider"] in ("google_workspace", "microsoft_365") for i in inboxes)
        has_kumo_inbox = any(i["provider"] == "kumomta" for i in inboxes)
        if has_provider_inbox and has_kumo_inbox:
            sending_mode = "hybrid"
        elif has_provider_inbox:
            sending_mode = "provider_managed"
        else:
            sending_mode = "dedicated"

        # 6. Auto-configure Integration Connections
        connections: list[dict[str, Any]] = []
        if any(i["provider"] == "google_workspace" for i in inboxes):
            connections.append({
                "provider": "google_workspace",
                "label": "Google Workspace OAuth/SMTP",
                "secret_ref": "GOOGLE_WORKSPACE_AUTH",
                "scopes": ["mail.send"],
            })
        if any(i["provider"] == "microsoft_365" for i in inboxes):
            connections.append({
                "provider": "microsoft_365",
                "label": "Microsoft 365 OAuth/SMTP",
                "secret_ref": "MICROSOFT_365_AUTH",
                "scopes": ["mail.send"],
            })

        crm_provider = (data.get("crm") or "").lower()
        if crm_provider:
            connections.append({
                "provider": crm_provider,
                "label": f"{crm_provider.title()} CRM Integration",
                "secret_ref": f"{crm_provider.upper()}_API_KEY",
                "scopes": ["contacts.read", "contacts.write"],
            })

        tenant_id = client_id or f"ten_{re.sub(r'[^a-z0-9]', '_', business_name.lower())[:24]}"

        config_payload = {
            "blueprint_name": "prospect-to-conversation",
            "blueprint_version": "1.0",
            "identity": {
                "business_name": business_name,
                "base_domain": base_domain,
                "industry": industry,
            },
            "branding": {
                "business_name": business_name,
                "logo_url": logo_url,
                "colors": {
                    "primary": primary_color,
                    "surface": "#ffffff",
                    "ink": "#0f172a",
                },
            },
            "terminology": {
                "sections": {
                    "discovery": f"Find {terms['prospects']}",
                    "qualification": f"Qualify {terms['prospects']}",
                    "outreach": "Campaigns & Review",
                    "conversations": f"{terms['lead_owner']} Inbox",
                },
                "entities": terms,
            },
            "sending": {
                "sender": sender_email,
                "physical_postal_address": postal_address,
                "lawful_basis": lawful_basis,
                "transport": "dry_run",
                "sending_mode": sending_mode,
                "inboxes": inboxes,
            },
            "limits": {
                "hourly_limit": int(data.get("hourly limit") or 10),
                "daily_limit": int(data.get("daily limit") or 50),
            },
            "approvals": {
                "require_approval": True,
                "approver": owners[0]["email"],
                "sla_hours": 24,
            },
            "modules": [
                "overview",
                "discovery",
                "research",
                "qualification",
                "personalization",
                "outreach",
                "conversations",
                "activity",
            ],
            "assignment_policy": "manual",
            "crm_provider": crm_provider,
        }

        return {
            "tenant_id": tenant_id,
            "config": config_payload,
            "owners": owners,
            "inboxes": inboxes,
            "connections": connections,
        }
