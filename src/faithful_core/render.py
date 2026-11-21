# SPDX-FileCopyrightText: 2026 Faithful Oversight, LLC
# SPDX-License-Identifier: Apache-2.0
"""Small helpers that every report renderer needs.

The renderers themselves stay in each product, because every product reports different
things. These helpers are the parts that must behave the same everywhere: they put
untrusted text into Markdown, HTML, and JSON without letting it change the structure.
"""

from __future__ import annotations

import html
import json
from typing import TYPE_CHECKING

from faithful_core.safety import escape_markdown, visible

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["CSP", "html_text", "json_dump", "md_table", "md_text", "plural"]

CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'none'; base-uri 'none'"
"""Content security policy for an HTML report: no scripts, no network access, no forms."""


def html_text(value: object) -> str:
    """Make a value safe to put in HTML text or in a quoted attribute.

    Invisible and reordering characters become visible escapes first, then the HTML
    special characters, including both quotes, are escaped.
    """
    return html.escape(visible(str(value)), quote=True)


def plural(n: int, one: str, many: str | None = None) -> str:
    """Return ``n`` and the noun in the right number, such as ``1 file`` or ``2 files``.

    ``many`` is the plural form; without it, an ``s`` is added to ``one``.
    """
    return f"{n} {one if n == 1 else many or one + 's'}"


def md_text(value: object) -> str:
    """Escape a value for a Markdown table cell or paragraph; see ``escape_markdown``."""
    return escape_markdown(str(value))


def md_table(head: tuple[str, ...], rows: Iterable[Iterable[object]]) -> list[str]:
    """Return the lines of a Markdown table.

    The heading cells are written as given, so they must be fixed text of the caller's own.
    Every cell of a row is escaped with :func:`md_text`.
    """
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    lines += ["| " + " | ".join(md_text(cell) for cell in row) + " |" for row in rows]
    return lines


def json_dump(value: object) -> str:
    """Render a value as indented JSON, in the order it was built, ending with a line feed.

    Non-ASCII text is kept as it is. If the value holds a lone surrogate, which UTF-8
    cannot hold, the text is written again with JSON escapes, which keep it exactly.
    """
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = json.dumps(value, indent=2, ensure_ascii=True) + "\n"
    return text
