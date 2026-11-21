# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for writing times and for the report time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from faithful_core import clock


def test_year_one_is_written_with_four_digits() -> None:
    moment = datetime(1, 1, 1, tzinfo=UTC)
    assert clock.date_and_time(moment) == "0001-01-01T00:00:00"


def test_the_separator_is_chosen_by_the_caller() -> None:
    moment = datetime(2026, 11, 3, 14, 5, 9, 999999, tzinfo=UTC)
    assert clock.date_and_time(moment) == "2026-11-03T14:05:09"
    assert clock.date_and_time(moment, " ") == "2026-11-03 14:05:09"


def test_the_time_is_written_as_it_is_without_conversion() -> None:
    moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-6)))
    assert clock.date_and_time(moment) == "2026-01-02T03:04:05"


@given(st.datetimes())
def test_the_text_always_has_the_same_shape(moment: datetime) -> None:
    text = clock.date_and_time(moment)
    assert len(text) == len("0001-01-01T00:00:00")
    assert datetime.fromisoformat(text) == moment.replace(microsecond=0)


def test_source_date_epoch_fixes_the_report_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert clock.now() == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


@pytest.mark.parametrize("value", ["", "abc", "-5", "1.5", "١٢", " 7", "99999999999999999999"])
def test_a_source_date_epoch_that_is_not_usable_falls_back_to_the_clock(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", value)
    before = datetime.now(UTC).replace(microsecond=0)
    moment = clock.now()
    after = datetime.now(UTC)
    assert moment.tzinfo is UTC
    assert moment.microsecond == 0
    assert before <= moment <= after


def test_without_source_date_epoch_the_clock_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert abs(clock.now() - datetime.now(UTC)) < timedelta(seconds=5)
