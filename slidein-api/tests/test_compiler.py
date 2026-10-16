from __future__ import annotations

import pytest

from slidein_api.factory.compiler import IntakeCompiler


def test_compiler_parses_mortgage_intake_notes():
    raw_intake = """
    Business Name: Summit Mortgage Lenders
    Base Domain: apply.summitmortgage.example
    Industry: Residential Lending & Mortgage Refinancing
    Primary Color: #1e3a8a
    Logo URL: https://summitmortgage.example/logo.png
    Physical Address: 500 Financial Way, Denver, CO 80202
    Lawful Basis: B2B legitimate interest for licensed mortgage brokerage
    Sender: loans@apply.summitmortgage.example
    Daily Limit: 40
    Hourly Limit: 8

    Team Members:
    - John Davis | john@summitmortgage.example | https://cal.com/summit/john-davis | nmls-10492
    - Alice Chen | alice@summitmortgage.example | https://cal.com/summit/alice-chen | nmls-20941
    """

    bundle = IntakeCompiler.compile(raw_intake)
    assert bundle["tenant_id"].startswith("ten_summit_mortgage")

    cfg = bundle["config"]
    assert cfg["identity"]["business_name"] == "Summit Mortgage Lenders"
    assert cfg["branding"]["colors"]["primary"] == "#1e3a8a"
    assert cfg["sending"]["physical_postal_address"] == "500 Financial Way, Denver, CO 80202"
    assert cfg["limits"]["daily_limit"] == 40
    assert cfg["limits"]["hourly_limit"] == 8

    # Industry terminology verification
    assert cfg["terminology"]["entities"]["prospect"] == "Borrower"
    assert cfg["terminology"]["entities"]["lead_owner"] == "Loan Officer"

    # Owners verification
    owners = bundle["owners"]
    assert len(owners) == 2
    assert owners[0]["display_name"] == "John Davis"
    assert owners[0]["booking_url"] == "https://cal.com/summit/john-davis"
    assert owners[0]["booking_verified"] is True
    assert owners[0]["crm_owner_id"] == "nmls-10492"


def test_compiler_parses_dental_clinic_intake():
    raw_intake = """
    Company: Harbor Dental Partners
    Domain: outreach.harbordental.example
    Vertical: Pediatric & Orthodontic Dental Clinics
    Color: 0ea5e9
    Address: 12 Dock Lane, Portland, OR 97201

    Advisors:
    - Dr. Sarah Jenkins | sarah@harbordental.example | https://cal.com/harbor/sarah
    """

    bundle = IntakeCompiler.compile(raw_intake)
    cfg = bundle["config"]
    assert cfg["identity"]["business_name"] == "Harbor Dental Partners"
    assert cfg["branding"]["colors"]["primary"] == "#0ea5e9"
    assert cfg["terminology"]["entities"]["prospect"] == "Dental Practice"
    assert cfg["terminology"]["entities"]["lead_owner"] == "Regional Director"

    assert len(bundle["owners"]) == 1
    assert bundle["owners"][0]["email"] == "sarah@harbordental.example"


def test_compiler_parses_hybrid_inboxes_and_connections():
    raw_intake = """
    Company: Apex Growth Capital
    Base Domain: apexcap.example
    Industry: Private Equity & Mergers
    Address: 100 Wall St, New York, NY 10005
    CRM: Hubspot

    Team:
    - Marcus Vance | marcus@apexcap.example | https://cal.com/apex/marcus | hub-99

    Inboxes:
    - outreach1@apexcap.example | Google Workspace | active | 50/day
    - outreach2@apexcap.example | Google Workspace | active | 50/day
    - connect1@mail.apexcap.example | KumoMTA | warming | 15/day
    - connect2@mail.apexcap.example | KumoMTA | warming | 15/day
    - connect3@mail.apexcap.example | KumoMTA | warming | 15/day
    - connect4@mail.apexcap.example | KumoMTA | warming | 15/day
    """

    bundle = IntakeCompiler.compile(raw_intake)
    cfg = bundle["config"]

    # Verify sending mode is hybrid
    assert cfg["sending"]["sending_mode"] == "hybrid"
    inboxes = cfg["sending"]["inboxes"]
    assert len(inboxes) == 6

    # 2 Google Workspace active
    gw = [i for i in inboxes if i["provider"] == "google_workspace"]
    assert len(gw) == 2
    assert all(i["status"] == "active" and not i["warmup_enabled"] for i in gw)

    # 4 KumoMTA warming
    kumo = [i for i in inboxes if i["provider"] == "kumomta"]
    assert len(kumo) == 4
    assert all(i["status"] == "warming" and i["warmup_enabled"] for i in kumo)

    # Connections auto-configured
    connections = bundle["connections"]
    provs = {c["provider"] for c in connections}
    assert "google_workspace" in provs
    assert "hubspot" in provs

