# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Loading a PowerShell script that a tool ships as package data."""

from __future__ import annotations

import re
from importlib.resources import files

__all__ = [
    "ScriptResource",
]

_VERSION = re.compile(r"^\$CollectorVersion = '([0-9]+\.[0-9]+\.[0-9]+)'$", re.MULTILINE)


class ScriptResource:
    """A PowerShell script shipped in a product's ``data`` folder.

    Args:
        package: The importable package that holds the ``data`` folder, such as
            ``faithful_example``.
        name: The script's file name, such as ``Collect-Example.ps1``.
        noun: What the script is called in messages, such as ``collector`` or ``exporter``.
    """

    def __init__(self, package: str, name: str, noun: str) -> None:
        """Remember where the script is; nothing is read until it is asked for."""
        self.package = package
        self.name = name
        self.noun = noun

    def text(self) -> str:
        """Return the script.

        It is pure ASCII, so Windows PowerShell 5.1, which reads a file without a byte
        order mark in the system code page, reads it the same as PowerShell 7 does.
        """
        return files(self.package).joinpath(f"data/{self.name}").read_text(encoding="ascii")

    def version(self) -> str:
        """Return the script's own version, as it writes it into each file.

        Raises:
            ValueError: The script does not state a version in the form
                ``$CollectorVersion = 'X.Y.Z'``.
        """
        match = _VERSION.search(self.text())
        if match is None:
            msg = f"the {self.noun} script states no version"
            raise ValueError(msg)
        return match.group(1)
