# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared exit codes."""

from __future__ import annotations

import pytest

from faithful_core.exitcodes import ExitCode


def test_exit_codes_are_stable() -> None:
    assert {code.name: int(code) for code in ExitCode} == {
        "OK": 0,
        "FINDINGS": 1,
        "USAGE": 2,
        "INPUT_ERROR": 3,
        "INTERNAL_ERROR": 4,
    }


def test_an_exit_code_is_an_integer_for_sys_exit() -> None:
    assert int(ExitCode.USAGE) == 2
    assert isinstance(ExitCode.OK, int)


def test_an_unknown_value_is_not_an_exit_code() -> None:
    with pytest.raises(ValueError, match="5 is not a valid ExitCode"):
        ExitCode(5)
