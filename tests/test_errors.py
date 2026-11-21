# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared exception classes."""

from __future__ import annotations

import pytest

from faithful_core.errors import (
    CollectionError,
    FaithfulError,
    InputError,
    OutputError,
    UsageError,
)

ERRORS = [InputError, CollectionError, UsageError, OutputError]


@pytest.mark.parametrize("error", ERRORS)
def test_every_error_is_a_faithful_error(error: type[FaithfulError]) -> None:
    with pytest.raises(FaithfulError, match="boom"):
        raise error("boom")


def test_the_errors_are_distinct_classes() -> None:
    assert len(set(ERRORS)) == len(ERRORS)
    assert not any(issubclass(a, b) for a in ERRORS for b in ERRORS if a is not b)


def test_the_base_class_is_an_ordinary_exception() -> None:
    assert issubclass(FaithfulError, Exception)
    assert not issubclass(FaithfulError, (OSError, ValueError))
