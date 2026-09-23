"""Render clean HTML to A4 PDF with WeasyPrint.

Takes the clean semantic HTML+CSS produced by :mod:`sars_convert.build_html`
and renders one A4 PDF per document with WeasyPrint. Each clean HTML embeds its
own ``@page { size: A4 landscape|portrait; }`` rule (set by :mod:`build_html`
from the document orientation) and links the shared ``styles.css``. This module
does NOT override orientation; it only passes the correct ``base_url`` so the
relative stylesheet link resolves.

Public API
----------
``render(html_path, out_path, base_url=None)``
    Render a single clean HTML file to a PDF.
``render_all(html_dir, out_dir)``
    Render every ``*.html`` in ``html_dir`` to ``out_dir/<stem>.pdf``.
"""

from __future__ import annotations

import os

from weasyprint import HTML

from .build_html import HTML_DIR

PDF_DIR = os.path.join("output", "pdf")


def render(html_path: str, out_path: str, base_url: str | None = None) -> str:
    """Render one clean HTML file to a PDF at ``out_path``.

    ``base_url`` defaults to the directory containing ``html_path`` so the
    relative ``styles.css`` link (and any other relative asset) resolves. The
    ``@page`` size/orientation embedded in the HTML is respected as-is.
    """
    if base_url is None:
        base_url = os.path.dirname(os.path.abspath(html_path)) + os.sep
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    HTML(filename=html_path, base_url=base_url).write_pdf(out_path)
    return out_path


def render_all(html_dir: str = HTML_DIR, out_dir: str = PDF_DIR) -> list[str]:
    """Render every ``*.html`` in ``html_dir`` to ``out_dir/<stem>.pdf``.

    The shared stylesheet is skipped; only document HTML files are rendered.
    Returns the list of written PDF paths.
    """
    os.makedirs(out_dir, exist_ok=True)
    base_url = os.path.abspath(html_dir) + os.sep

    written: list[str] = []
    for name in sorted(os.listdir(html_dir)):
        if not name.endswith(".html"):
            continue
        html_path = os.path.join(html_dir, name)
        out_path = os.path.join(out_dir, f"{name[:-5]}.pdf")
        render(html_path, out_path, base_url=base_url)
        written.append(out_path)
    return written


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    paths = render_all()
    print(f"Wrote {len(paths)} PDF files to {PDF_DIR}/")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
