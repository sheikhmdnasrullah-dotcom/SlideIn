"""Unit tests for prospect engagement modules:
- 24-hr US business day grace period scheduler
- Multi-channel notification dispatcher (Telegram, Discord, Slack)
- Notion Booking Calendar provider & strict cold link prevention
- Non-negotiable monthly pricing ($350/mo)
"""

from datetime import date, datetime, timedelta, timezone
import pytest

from slidein_api.services.scheduler import (
    compute_business_grace_deadline,
    is_us_business_day,
    GracePeriodTracker,
)
from slidein_api.services.notifications import NotificationDispatcher
from slidein_api.services.booking import (
    BookingProvider,
    BookingPolicyError,
    scan_content_for_unauthorized_links,
)


def test_us_business_day_detection():
    # 2026-10-16 is Friday (business day)
    friday = date(2026, 10, 16)
    assert is_us_business_day(friday) is True

    # 2026-10-17 is Saturday (weekend)
    saturday = date(2026, 10, 17)
    assert is_us_business_day(saturday) is False

    # 2026-10-18 is Sunday (weekend)
    sunday = date(2026, 10, 18)
    assert is_us_business_day(sunday) is False

    # 2026-12-25 is Christmas (US Federal Holiday)
    christmas = date(2026, 12, 25)
    assert is_us_business_day(christmas) is False


def test_24h_grace_period_skips_weekends():
    # Receive reply on Friday 10:00 AM UTC
    friday_10am = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
    deadline = compute_business_grace_deadline(friday_10am, business_hours=24)

    # Friday has 14 hours remaining (10:00 to 24:00)
    # Saturday & Sunday are skipped (0 hours)
    # Monday consumes remaining 10 hours (00:00 to 10:00 AM)
    assert deadline.weekday() == 0  # Monday
    assert deadline.year == 2026
    assert deadline.month == 10
    assert deadline.day == 19
    assert deadline.hour == 10
    assert deadline.minute == 0


def test_grace_period_tracker_human_takeover():
    start = datetime(2026, 10, 16, 10, 0, 0, tzinfo=timezone.utc)
    past_deadline = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

    # When no human intervened, auto reply triggers
    assert GracePeriodTracker.should_trigger_auto_reply(start, now=past_deadline) is True

    # When human replied, auto reply suppressed
    assert GracePeriodTracker.should_trigger_auto_reply(
        start, now=past_deadline, human_replied=True
    ) is False

    # When human took over, auto reply suppressed
    assert GracePeriodTracker.should_trigger_auto_reply(
        start, now=past_deadline, human_taken_over=True
    ) is False


def test_strict_cold_email_link_prevention():
    provider = BookingProvider(
        primary_booking_url="https://calendar.notion.so/meet/tanim",
    )

    # Should raise error if trying to generate link for cold outreach
    with pytest.raises(BookingPolicyError) as exc_info:
        provider.generate_scheduling_link(
            outreach_stage="cold_outreach",
            prospect_email="sarah@example.com",
            prospect_name="Sarah",
            prospect_intent="interested",
        )
    assert "Links are forbidden in first-touch cold emails" in str(exc_info.value)


def test_booking_link_allowed_when_interested():
    provider = BookingProvider(
        primary_booking_url="https://calendar.notion.so/meet/tanim",
    )

    link = provider.generate_scheduling_link(
        outreach_stage="reply_phase",
        prospect_email="sarah@example.com",
        prospect_name="Sarah",
        prospect_intent="interested",
    )
    assert "https://calendar.notion.so/meet/tanim" in link
    assert "sarah@example.com" in link


def test_dedicated_custom_booking_link_sync():
    provider = BookingProvider(
        primary_booking_url="https://calendar.notion.so/meet/default",
        custom_booking_url="https://cal.com/client-custom/demo",
    )
    assert provider.get_effective_booking_url() == "https://cal.com/client-custom/demo"


def test_non_negotiable_monthly_pricing():
    provider = BookingProvider(monthly_price_usd=350.0)

    # Full price or higher accepted
    assert provider.validate_pricing_offer(350.0) is True
    assert provider.validate_pricing_offer(400.0) is True

    # Attempted discount/negotiation rejected
    with pytest.raises(BookingPolicyError) as exc_info:
        provider.validate_pricing_offer(250.0)
    assert "below fixed monthly rate $350.00" in str(exc_info.value)


def test_scan_for_unauthorized_links():
    clean_text = "Hi Sarah, saw your recent update about scaling engineering. Would love to share how we approach this."
    assert scan_content_for_unauthorized_links(clean_text) == []

    dirty_text = "Hi Sarah, check our website https://slidein.me or book at cal.com/tanim."
    links = scan_content_for_unauthorized_links(dirty_text)
    assert len(links) >= 1
