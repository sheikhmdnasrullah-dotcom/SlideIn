"""Typed deployment configuration. Data only — clients can never upload
executable code, prompts, or tool grants through these schemas."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^/\s]+(\/\S*)?$", re.IGNORECASE)


class SendingConfig(BaseModel):
    sender: str = ""
    physical_postal_address: str = ""
    lawful_basis: str = ""
    transport: Literal["dry_run", "smtp"] = "dry_run"
    sending_mode: str = "dedicated"
    inboxes: list[dict] = Field(default_factory=list)

    @field_validator("sender")
    @classmethod
    def _sender_valid(cls, value: str) -> str:
        if value and not _EMAIL_RE.match(value):
            raise ValueError("sender must be an email address")
        return value.strip()


class LimitsConfig(BaseModel):
    hourly_limit: int = Field(default=10, ge=1, le=1000)
    daily_limit: int = Field(default=50, ge=1, le=10000)


class ApprovalConfig(BaseModel):
    require_approval: bool = True
    approver: str = ""
    sla_hours: int = Field(default=24, ge=1, le=720)


class OwnerInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    email: str
    crm_provider: str = ""
    crm_owner_id: str = ""
    booking_provider: str = ""
    booking_url: str = ""
    booking_event_ref: str = ""
    booking_verified: bool = False
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def _email_valid(cls, value: str) -> str:
        if not _EMAIL_RE.match(value or ""):
            raise ValueError("owner email must be a valid email address")
        return value.strip().lower()

    @field_validator("booking_url")
    @classmethod
    def _url_valid(cls, value: str) -> str:
        if value and not _URL_RE.match(value):
            raise ValueError("booking_url must be an http(s) URL")
        return value.strip()


class CrmMapInput(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    slidein_field: str = Field(min_length=1, max_length=128)
    external_field: str = Field(min_length=1, max_length=255)
    direction: Literal["in", "out", "both"] = "both"


class ConnectionInput(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=255)
    secret_ref: str = ""
    scopes: list[str] = Field(default_factory=list)


class DeploymentConfigInput(BaseModel):
    blueprint_name: str = Field(min_length=1, max_length=128)
    blueprint_version: str = Field(min_length=1, max_length=32)
    sending: SendingConfig = Field(default_factory=SendingConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    approvals: ApprovalConfig = Field(default_factory=ApprovalConfig)
    assignment_policy: Literal["manual", "round_robin", "crm_owner"] = "manual"
    crm_provider: str = ""
    modules: list[str] = Field(default_factory=list)
