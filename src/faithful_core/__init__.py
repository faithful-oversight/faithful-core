# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""faithful_core: the shared foundation of the Faithful Oversight tools."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("faithful-core")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
