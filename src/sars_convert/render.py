"""Render clean HTML to A4 PDF with WeasyPrint.

Placeholder module. Filled by a later feature.

Planned responsibility
-----------------------
Take the clean semantic HTML+CSS produced by :mod:`sars_convert.converter` and
render it to an A4 PDF using WeasyPrint, choosing landscape or portrait
orientation per document (see the orientation table in the project README).
"""

from __future__ import annotations


def render(html: str, out_path: str, *, landscape: bool = True) -> None:
    """Render clean HTML to an A4 PDF at ``out_path``.

    Not implemented yet - placeholder for a later feature.
    """
    raise NotImplementedError("render.render is implemented in a later feature")
