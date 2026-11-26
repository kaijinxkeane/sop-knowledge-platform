"""The company's calendar: dates in its time zone (`SOP_TIMEZONE`, default
Asia/Singapore), whatever time zone the server itself is set to.

Due dates, reminders, approvals, project ends and reading deadlines all compare
against `today()`, so a document can't be "due today" on one screen and
"overdue" on another. Timestamps are stored in UTC; `local_date` turns one into
the company's date. The worker runs its nightly jobs on this clock too.
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from functools import cache
from zoneinfo import ZoneInfo

from app.config import get_settings


@cache
def zone() -> tzinfo:
    return ZoneInfo(get_settings().time_zone)


def today() -> date:
    return datetime.now(zone()).date()


def local_date(moment: datetime) -> date:
    """The company's date at that moment (stored timestamps are UTC)."""
    return moment.astimezone(zone()).date()
