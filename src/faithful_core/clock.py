# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Writing times as text the same way on every platform, and the report time."""

from __future__ import annotations

import os
from datetime import UTC, datetime

__all__ = [
    "date_and_time",
    "now",
]


def date_and_time(moment: datetime, separator: str = "T") -> str:
    """Return ``YYYY-MM-DD`` and ``HH:MM:SS`` joined by ``separator``.

    ``strftime("%Y")`` is not used: on Linux it writes year 1 as ``1`` rather than
    ``0001``, which no reader of these files accepts.
    """
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}{separator}"
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}"
    )


def now() -> datetime:
    """Return the report time: the clock, or ``SOURCE_DATE_EPOCH`` for a repeatable report.

    ``SOURCE_DATE_EPOCH`` counts for a value of ASCII digits only. Anything else, or a
    value the platform cannot turn into a time, is ignored and the clock is used. The
    clock reading has no microseconds, so two reports made in the same second match.
    """
    fixed = os.environ.get("SOURCE_DATE_EPOCH", "")
    if fixed.isascii() and fixed.isdigit():
        try:
            return datetime.fromtimestamp(int(fixed), UTC)
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.now(UTC).replace(microsecond=0)
