# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""The public interface is exactly what the documentation says it is."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import faithful_core

API = {
    "errors": ["CollectionError", "FaithfulError", "InputError", "OutputError", "UsageError"],
    "exitcodes": ["ExitCode"],
    "safety": [
        "FORMULA_TRIGGERS",
        "command_line",
        "csv_cell",
        "escape_markdown",
        "neutralize_formula",
        "terminal",
        "terminal_line",
        "visible",
    ],
    "clock": ["date_and_time", "now"],
    "console": ["finish", "prepare", "say", "stdout_closed"],
    "xmlsafe": [
        "MAX_BYTES",
        "MAX_DEPTH",
        "MAX_ELEMENTS",
        "Take",
        "XmlError",
        "decode",
        "parse",
        "split",
    ],
    "files": ["copy_new", "refuse_aliases", "write_files"],
    "collect.names": ["account_name", "install_hint", "server_name"],
    "collect.secrets": [
        "InstallHint",
        "PROVIDERS",
        "REDACTED",
        "redact",
        "remember",
        "resolve",
    ],
    "collect.script": ["ScriptResource"],
    "collect.winrm": [
        "AUTHS",
        "POLL_SECONDS",
        "Sink",
        "TRANSPORTS",
        "Target",
        "client",
        "collect",
        "drain",
        "publish_file",
        "settings",
    ],
    "render": ["CSP", "html_text", "json_dump", "md_table", "md_text", "plural"],
}
SOURCE = Path(faithful_core.__file__).parent
PRODUCTS = ("pakad", "toledot", "mishpat", "shaar", "merilo", "gvul")


@pytest.mark.parametrize("module", sorted(API))
def test_each_module_exports_exactly_its_documented_names(module: str) -> None:
    exported = importlib.import_module(f"faithful_core.{module}").__all__
    assert sorted(exported) == sorted(API[module])
    assert not [name for name in exported if name.startswith("_")]


@pytest.mark.parametrize("module", sorted(API))
def test_every_exported_name_exists_and_is_documented(module: str) -> None:
    loaded = importlib.import_module(f"faithful_core.{module}")
    for name in API[module]:
        assert hasattr(loaded, name), name
        if callable(loaded.__dict__[name]) and getattr(loaded.__dict__[name], "__module__", None):
            assert loaded.__dict__[name].__doc__, f"{module}.{name} has no docstring"


def test_the_package_has_no_dependencies_and_exports_only_its_version() -> None:
    assert faithful_core.__all__ == ["__version__"]
    assert isinstance(faithful_core.__version__, str)


def test_no_message_or_docstring_names_a_product() -> None:
    found = [
        f"{path.relative_to(SOURCE)}:{number}"
        for path in sorted(SOURCE.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if any(product in line.lower() for product in PRODUCTS)
    ]
    assert found == []
