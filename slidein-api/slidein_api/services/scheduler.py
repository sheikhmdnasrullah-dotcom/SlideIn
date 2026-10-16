"""Business hours & grace period scheduler for autonomous prospect engagement.

Rules enforced:
1. A 24-hour human review grace window starts when an inbound prospect reply arrives.
2. The timer skips US off days: weekends (Saturday, Sunday) and official US Federal Holidays.
3. If a human responds or takes over within the grace window, the agent is paused.
4. If 24 business hours elapse without human intervention, the agent auto-replies
   using grounded knowledge that mirrors natural human cadence.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Set

#: Standard fixed US Federal Holidays (observed month, day).
_FIXED_US_HOLIDAYS = {
    (1, 1),    # New Year's Day
    (6, 19),   # Juneteenth
    (7, 4),    # Independence Day
    (11, 11),  # Veterans Day
    (12, 25),  # Christmas Day
}


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Find the nth occurrence of a weekday in a month (weekday: 0=Mon, 6=Sun)."""
    first_day = date(year, month, 1)
    offset = (weekday - first_day.weekday()) % 7
    first_weekday = first_day + timedelta(days=offset)
    return first_weekday + timedelta(weeks=n - 1)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Find the last occurrence of a weekday in a month."""
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=offset)


def get_us_federal_holidays(year: int) -> Set[date]:
    """Return the set of US Federal Holidays for a given year."""
    holidays: set[date] = set()
    for m, d in _FIXED_US_HOLIDAYS:
        try:
            h = date(year, m, d)
            # If holiday falls on Saturday, observed on Friday; if Sunday, observed on Monday
            if h.weekday() == 5:
                holidays.add(h - timedelta(days=1))
            elif h.weekday() == 6:
                holidays.add(h + timedelta(days=1))
            else:
                holidays.add(h)
        except ValueError:
            pass

    # Floating holidays:
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))   # MLK Jr Day (3rd Mon in Jan)
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))   # Washington's Birthday (3rd Mon in Feb)
    holidays.add(_last_weekday_of_month(year, 5, 0))     # Memorial Day (last Mon in May)
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))   # Labor Day (1st Mon in Sep)
    holidays.add(_nth_weekday_of_month(year, 10, 0, 2))  # Columbus Day (2nd Mon in Oct)
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))  # Thanksgiving Day (4th Thu in Nov)

    return holidays


def is_us_business_day(d: date) -> bool:
    """Returns True if the date is a Monday-Friday and not a US federal holiday."""
    if d.weekday() >= 5:  # Saturday or Sunday
        return False
    holidays = get_us_federal_holidays(d.year)
    return d not in holidays


def compute_business_grace_deadline(
    start_dt: datetime,
    business_hours: int = 24,
) -> datetime:
    """Compute the expiration timestamp by adding business hours.
    
    Hours accumulate continuously during US business days (excluding weekends & holidays).
    Hour-by-hour stepping guarantees accurate spanning across long weekends or holiday clusters.
    """
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    current_dt = start_dt
    remaining_hours = float(business_hours)

    while remaining_hours > 0:
        current_date = current_dt.date()
        if is_us_business_day(current_date):
            remaining_today_hours = (24 - current_dt.hour) - (current_dt.minute / 60.0) - (current_dt.second / 3600.0)
            if remaining_hours <= remaining_today_hours:
                current_dt += timedelta(hours=remaining_hours)
                remaining_hours = 0
            else:
                current_dt = datetime.combine(
                    current_date + timedelta(days=1),
                    time.min,
                    tzinfo=current_dt.tzinfo,
                )
                remaining_hours -= remaining_today_hours
        else:
            current_dt = datetime.combine(
                current_date + timedelta(days=1),
                time.min,
                tzinfo=current_dt.tzinfo,
            )

    return current_dt


class GracePeriodTracker:
    """Manages the 24-hour business grace period state for conversations."""

    @staticmethod
    def should_trigger_auto_reply(
        reply_received_at: datetime,
        now: datetime | None = None,
        grace_hours: int = 24,
        human_replied: bool = False,
        human_taken_over: bool = False,
    ) -> bool:
        """Determines if the autonomous agent should execute the auto-reply."""
        if human_replied or human_taken_over:
            return False
        
        now = now or datetime.now(timezone.utc)
        deadline = compute_business_grace_deadline(reply_received_at, business_hours=grace_hours)
        return now >= deadline
