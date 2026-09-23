"""Command-line entry point for sars_convert.

Runs the implemented pipeline stages: recover the IR from the reference PDFs
(:mod:`sars_convert.extract`) and build clean semantic HTML+CSS from it
(:mod:`sars_convert.build_html`). The render (WeasyPrint -> A4 PDF) and verify
stages are wired up by later features; see ``README.md``.
"""

from __future__ import annotations

from . import build_html, extract


def main(argv: list[str] | None = None) -> int:
    """Extract the IR from the reference PDFs, then build clean HTML."""
    ir_paths = extract.extract_all()
    print(f"Extracted {len(ir_paths)} IR files to {extract.IR_DIR}/")
    html_paths = build_html.build_all()
    print(f"Wrote {len(html_paths)} clean HTML files to {build_html.HTML_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
