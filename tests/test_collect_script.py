# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for loading a packaged PowerShell script."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from faithful_core.collect.script import ScriptResource

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

NAME = "Collect-Example.ps1"
GOOD = "# a collector\n$CollectorVersion = '1.2.3'\nWrite-Output 'x'\n"


@pytest.fixture
def make_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Callable[[str | bytes], str]:
    """Return a function that creates an importable package with one script in its data folder."""
    name = f"example_pkg_{tmp_path.name.replace('-', '_')}"  # unique to the test

    def make(text: str | bytes) -> str:
        package = tmp_path / name
        (package / "data").mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        data = text if isinstance(text, bytes) else text.encode("ascii")
        (package / "data" / NAME).write_bytes(data)
        monkeypatch.syspath_prepend(str(tmp_path))
        request.addfinalizer(lambda: sys.modules.pop(name, None))
        return name

    return make


def test_the_script_is_read_as_ascii_text(make_package: Callable[[str | bytes], str]) -> None:
    package = make_package(GOOD)
    resource = ScriptResource(package, NAME, "collector")
    assert resource.text() == GOOD
    assert (resource.package, resource.name, resource.noun) == (package, NAME, "collector")


def test_the_script_states_its_version(make_package: Callable[[str | bytes], str]) -> None:
    package = make_package(GOOD)
    assert ScriptResource(package, NAME, "collector").version() == "1.2.3"


def test_a_script_with_no_version_is_reported_with_the_noun(
    make_package: Callable[[str | bytes], str],
) -> None:
    package = make_package("Write-Output 'x'\n")
    with pytest.raises(ValueError, match="the exporter script states no version"):
        ScriptResource(package, NAME, "exporter").version()


@pytest.mark.parametrize(
    "line",
    ['$CollectorVersion = "1.2.3"', "  $CollectorVersion = '1.2.3'", "$CollectorVersion = '1.2'"],
)
def test_only_the_exact_version_line_counts(
    make_package: Callable[[str | bytes], str], line: str
) -> None:
    package = make_package(f"{line}\n")
    with pytest.raises(ValueError, match="states no version"):
        ScriptResource(package, NAME, "collector").version()


def test_a_script_that_is_not_ascii_is_refused(make_package: Callable[[str | bytes], str]) -> None:
    package = make_package(GOOD.encode() + "ü".encode())
    with pytest.raises(UnicodeDecodeError):
        ScriptResource(package, NAME, "collector").text()


def test_nothing_is_read_until_it_is_asked_for() -> None:
    resource = ScriptResource("no_such_package_at_all", NAME, "collector")
    assert resource.noun == "collector"
    with pytest.raises(ModuleNotFoundError):
        resource.text()
