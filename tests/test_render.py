# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the report rendering helpers."""

from __future__ import annotations

import json
import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from faithful_core import render


def test_the_policy_forbids_scripts_and_the_network() -> None:
    assert render.CSP == (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'"
    )


def test_html_text_escapes_markup_quotes_and_hidden_characters() -> None:
    shown = render.html_text('<b onclick="x">&\'' + chr(0x202E))
    assert shown == "&lt;b onclick=&quot;x&quot;&gt;&amp;&#x27;\\u202e"


def test_html_text_accepts_any_object() -> None:
    assert render.html_text(42) == "42"
    assert render.html_text(None) == "None"


@given(st.text())
def test_html_text_never_leaves_a_markup_character(value: str) -> None:
    assert not re.search(r"[<>\"']", render.html_text(value))


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, "0 files"), (1, "1 file"), (2, "2 files")],
)
def test_plural_adds_an_s(n: int, expected: str) -> None:
    assert render.plural(n, "file") == expected


def test_plural_takes_an_irregular_form() -> None:
    assert render.plural(1, "entry", "entries") == "1 entry"
    assert render.plural(3, "entry", "entries") == "3 entries"


def test_md_text_escapes_structure() -> None:
    assert render.md_text("a|b") == "a\\|b"
    assert render.md_text(3) == "3"


def test_md_table_escapes_cells_and_not_the_heading() -> None:
    lines = render.md_table(("Name", "Note"), [["a|b", 1], ["line\nbreak", "ok"]])
    assert lines == [
        "| Name | Note |",
        "| --- | --- |",
        "| a\\|b | 1 |",
        "| line ↵ break | ok |",
    ]


def test_md_table_without_rows_is_just_the_heading() -> None:
    assert render.md_table(("A",), []) == ["| A |", "| --- |"]


def test_json_dump_is_indented_and_ends_with_a_line_feed() -> None:
    text = render.json_dump({"b": 1, "a": ["x", "café"]})
    assert text == '{\n  "b": 1,\n  "a": [\n    "x",\n    "café"\n  ]\n}\n'


def test_json_dump_keeps_a_lone_surrogate_exactly() -> None:
    text = render.json_dump({"k": "a\udc80b", "u": "ü"})
    text.encode("utf-8")  # must be encodable
    assert json.loads(text) == {"k": "a\udc80b", "u": "ü"}


@given(st.dictionaries(st.text(), st.text()))
def test_json_dump_round_trips_and_always_encodes(value: dict[str, str]) -> None:
    text = render.json_dump(value)
    text.encode("utf-8")
    assert json.loads(text) == value
