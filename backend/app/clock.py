"""Today's date for the whole app: the UTC date, whatever the server's time zone.

Due dates, reminders, approvals, project ends and reading deadlines all compare
against this, so a document can't be "due today" for one screen and "overdue"
for another.
"""

from __future__ import annotations

from datetime import UTC, date, datetime


def today() -> date:
    return datetime.now(UTC).date()
