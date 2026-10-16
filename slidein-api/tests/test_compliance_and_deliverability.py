"""Unit tests for Deliverability Guard, shared IP isolation, and cold-email statutory compliance."""

import os
import pytest

from slidein_api.services.deliverability_guard import (
    DeliverabilityGuard,
    DeliverabilityQuarantineError,
    MissingPhysicalAddressError,
    LawfulBasisMissingError,
    MAX_ALLOWED_BOUNCE_RATE,
    MAX_ALLOWED_COMPLAINT_RATE,
)


def test_missing_physical_address_raises_error():
    guard = DeliverabilityGuard("tenant_demo")
    settings = {
        "physical_postal_address": "",  # Empty!
        "lawful_basis": "b2b_legitimate_interest",
        "quarantined": False,
    }

    with pytest.raises(MissingPhysicalAddressError) as exc_info:
        guard.validate_pre_send_compliance(settings)
    assert "valid physical postal address is required" in str(exc_info.value)


def test_missing_lawful_basis_raises_error():
    guard = DeliverabilityGuard("tenant_demo")
    settings = {
        "physical_postal_address": "Suite 100, 100 Main St, Austin, TX 78701",
        "lawful_basis": "",  # Empty!
        "quarantined": False,
    }

    with pytest.raises(LawfulBasisMissingError) as exc_info:
        guard.validate_pre_send_compliance(settings)
    assert "Lawful basis" in str(exc_info.value)


def test_quarantined_tenant_is_blocked():
    guard = DeliverabilityGuard("tenant_abusive")
    settings = {
        "physical_postal_address": "Suite 100, 100 Main St, Austin, TX 78701",
        "lawful_basis": "b2b_legitimate_interest",
        "quarantined": True,
        "quarantine_reason": "High bounce rate (4.2%) on shared VPS IP",
    }

    with pytest.raises(DeliverabilityQuarantineError) as exc_info:
        guard.validate_pre_send_compliance(settings)
    assert "is quarantined from sending on shared IPs" in str(exc_info.value)


def test_compliant_settings_pass():
    guard = DeliverabilityGuard("tenant_healthy")
    settings = {
        "physical_postal_address": "Suite 100, 100 Main St, Austin, TX 78701",
        "lawful_basis": "b2b_legitimate_interest",
        "quarantined": False,
    }
    # Should not raise any error
    guard.validate_pre_send_compliance(settings)


def test_circuit_breaker_bounce_threshold():
    # 25 events: 2 bounces = 8.0% bounce rate (> 3.0% limit)
    events = ["delivered"] * 23 + ["bounced", "bounced"]
    tripped, reason = DeliverabilityGuard.evaluate_circuit_breaker(events)
    assert tripped is True
    assert "Hard bounce rate" in str(reason)

    # 50 events: 1 bounce = 2.0% bounce rate (< 3.0% limit)
    events_safe = ["delivered"] * 49 + ["bounced"]
    tripped, reason = DeliverabilityGuard.evaluate_circuit_breaker(events_safe)
    assert tripped is False
    assert reason is None


def test_circuit_breaker_complaint_threshold():
    # 100 events: 1 complaint = 1.0% (> 0.05% limit)
    events = ["delivered"] * 99 + ["complained"]
    tripped, reason = DeliverabilityGuard.evaluate_circuit_breaker(events)
    assert tripped is True
    assert "Spam complaint rate" in str(reason)


def test_format_compliant_body():
    body = "Hello Alex, loved your work on real-time event systems."
    address = "456 Market St, Suite 500, San Francisco, CA"
    
    formatted = DeliverabilityGuard.format_compliant_body(body, physical_address=address)
    assert "To stop receiving emails" in formatted
    assert "456 Market St, Suite 500, San Francisco, CA" in formatted


def test_build_compliance_headers():
    headers = DeliverabilityGuard.build_compliance_headers(
        tenant_id="tenant_123",
        sender_email="talk@nasrullahtanim.me",
        recipient_email="alex@company.com",
    )
    assert "List-Unsubscribe" in headers
    assert "List-Unsubscribe-Post" in headers
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert headers["X-Tenant-ID"] == "tenant_123"


def test_license_invariants():
    license_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../LICENSE"))
    assert os.path.exists(license_path)
    with open(license_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Business Source License 1.1" in content
    assert "Nasrullah Tanim" in content
    assert "Additional Use Grant" in content
    assert "Apache License, Version 2.0" in content
    assert "OPENOUTREACH (GPLv3)" in content
    assert "Clean-Room" in content
