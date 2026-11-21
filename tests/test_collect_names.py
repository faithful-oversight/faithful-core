# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the server and account name checks and the install hint."""

from __future__ import annotations

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from faithful_core.collect import names
from faithful_core.errors import CollectionError

BAD_SERVERS = [
    ("10.0.0.5", "is an IP address"),
    ("[fe80::1]", "is an IP address"),
    ("dc01", "not a fully qualified DNS name"),
    ("dc01.corp.example/x", "not a fully qualified DNS name"),
    ("u:p@dc01.corp.example", "not a fully qualified DNS name"),
    ("-dc.corp.example", "not a fully qualified DNS name"),
    ("dc01.10", "not a fully qualified DNS name"),
    ("a" * 64 + ".corp.example", "not a fully qualified DNS name"),
    ("a." * 127 + "example", "not a fully qualified DNS name"),
]


@pytest.mark.parametrize(("server", "problem"), BAD_SERVERS)
def test_server_must_be_a_dns_name(server: str, problem: str) -> None:
    with pytest.raises(CollectionError, match=problem):
        names.server_name(server)


@pytest.mark.parametrize(("server", "problem"), BAD_SERVERS)
def test_the_message_names_the_option_the_caller_gives(server: str, problem: str) -> None:
    with pytest.raises(CollectionError, match=rf"^--host {re.escape(repr(server))}") as caught:
        names.server_name(server, flag="--host")
    assert "--server" not in str(caught.value)
    assert problem in str(caught.value)


def test_the_default_option_name_is_server() -> None:
    with pytest.raises(CollectionError, match=r"^--server 'dc01' "):
        names.server_name("dc01")


def test_a_server_name_that_is_accepted_loses_only_its_trailing_dot() -> None:
    assert names.server_name("DC01.Corp.Example.") == "DC01.Corp.Example"
    assert names.server_name("dc01.corp.example") == "dc01.corp.example"


@given(st.text())
def test_a_server_name_is_either_refused_or_plain_dns(server: str) -> None:
    try:
        name = names.server_name(server)
    except CollectionError:
        return
    assert name.isascii()
    assert all(c.isalnum() or c in "-." for c in name)
    assert "." in name


def test_usernames_are_returned_as_domain_and_user() -> None:
    assert names.account_name("CORP\\auditor") == "CORP\\auditor"
    assert names.account_name("auditor@corp.example") == "corp.example\\auditor"
    assert names.account_name(None) is None


@pytest.mark.parametrize(
    "username", ["auditor", "\\auditor", "CORP\\", "@corp.example", "C\\a:b", "C\\u\n"]
)
def test_a_username_needs_a_domain(username: str) -> None:
    with pytest.raises(CollectionError, match="must be DOMAIN"):
        names.account_name(username)


def test_the_install_hint_names_every_extra_and_points_to_pypi() -> None:
    hint = names.install_hint("faithful-example", "winrm", "vault")
    assert hint == (
        'pipx install --force "faithful-example[winrm,vault]" '
        '(or, with pip, pip install "faithful-example[winrm,vault]")'
    )
    assert "git+" not in hint


def test_the_install_hint_without_extras_has_no_brackets() -> None:
    assert names.install_hint("faithful-example") == (
        'pipx install --force "faithful-example" (or, with pip, pip install "faithful-example")'
    )


def test_the_install_hint_can_point_to_a_git_repository() -> None:
    source = "https://github.com/example-org/faithful-example"
    hint = names.install_hint("faithful-example", "winrm", source=source)
    spec = f'"faithful-example[winrm] @ git+{source}"'
    assert hint == f"pipx install --force {spec} (or, with pip, pip install {spec})"


def test_the_install_hint_from_git_without_extras() -> None:
    hint = names.install_hint("faithful-example", source="https://example.com/r")
    assert '"faithful-example @ git+https://example.com/r"' in hint
