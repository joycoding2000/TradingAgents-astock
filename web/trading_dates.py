"""Small, dependency-free safeguards for user-selected A-share analysis dates."""

from __future__ import annotations

from datetime import date, timedelta


def most_recent_weekday(value: date) -> date:
    """Return Friday for a weekend date, otherwise return ``value`` unchanged.

    This prevents the common and severe mistake of describing Saturday/Sunday
    as an A-share trading session. Public-holiday availability is still checked
    by the data layer; a selected weekday is intentionally not rewritten here.
    """
    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value
