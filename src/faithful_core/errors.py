# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Exceptions that Faithful Oversight tools report to the user.

A product catches :class:`FaithfulError` once, so an error raised inside this library
is handled the same way as an error the product raised itself.
"""

__all__ = [
    "CollectionError",
    "FaithfulError",
    "InputError",
    "OutputError",
    "UsageError",
]


class FaithfulError(Exception):
    """Base class for errors a tool reports to the user."""


class InputError(FaithfulError):
    """An input file or configuration cannot be read or has the wrong shape."""


class CollectionError(FaithfulError):
    """Live collection could not connect, authenticate, or read what it needs."""


class UsageError(FaithfulError):
    """The command's options do not fit together, so nothing was attempted."""


class OutputError(FaithfulError):
    """Output files cannot be written, or writing them would replace a file the tool reads."""
