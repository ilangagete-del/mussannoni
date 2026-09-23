"""Command-line entry point for sars_convert.

Runs the full pipeline end to end: recover the IR from the reference PDFs
(:mod:`sars_convert.extract`), build clean semantic HTML+CSS from it
(:mod:`sars_convert.build_html`), then render each document to an A4 PDF with
WeasyPrint (:mod:`sars_convert.render`). See ``README.md``.
"""

from __future__ import annotations

from . import build_html, extract, render


def main(argv: list[str] | None = None) -> int:
    """Extract the IR, build clean HTML, then render each document to PDF."""
    ir_paths = extract.extract_all()
    print(f"Extracted {len(ir_paths)} IR files to {extract.IR_DIR}/")
    html_paths = build_html.build_all()
    print(f"Wrote {len(html_paths)} clean HTML files to {build_html.HTML_DIR}/")
    pdf_paths = render.render_all()
    print(f"Wrote {len(pdf_paths)} PDF files to {render.PDF_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
