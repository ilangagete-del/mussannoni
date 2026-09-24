"""Baseline geometry oracle for every SARS report.

For each pair from :func:`sars.sources.discover`, print the reference PDF's
page size (points) and page count recovered through the fidelity oracle
(:func:`sars.extract.extract_document`, which takes ``pathlib.Path`` args), the
generated ``output/template_pdf/<name>.pdf`` page size and page count read with
PyMuPDF, and match booleans for size and page count.

Usage::

    python tools/measure_all.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sars import sources  # noqa: E402
from sars.extract import extract_document  # noqa: E402

TEMPLATE_PDF = ROOT / "output" / "template_pdf"


def _round(value: float) -> int:
    return int(round(value))


def reference_geometry(pair: sources.SourcePair) -> tuple[int, int, int]:
    """Reference (width, height, page_count) in points via the fidelity oracle."""
    doc = extract_document(pair.pdf, pair.html)
    page = doc.pages[0]
    return _round(page.width), _round(page.height), len(doc.pages)


def generated_geometry(name: str) -> tuple[int, int, int] | None:
    """Generated template (width, height, page_count) in points, or None if missing."""
    pdf = TEMPLATE_PDF / f"{name}.pdf"
    if not pdf.exists():
        return None
    with pymupdf.open(pdf) as document:
        rect = document[0].rect
        return _round(rect.width), _round(rect.height), document.page_count


def main() -> int:
    header = (
        f"{'REPORT':46} | {'REF SIZE':>11} {'REF PP':>6} | "
        f"{'GEN SIZE':>11} {'GEN PP':>6} | {'SIZE':>4} {'PAGES':>5}"
    )
    print(header)
    print("-" * len(header))

    size_ok = 0
    pages_ok = 0
    total = 0
    for pair in sources.discover():
        total += 1
        ref_w, ref_h, ref_pp = reference_geometry(pair)
        gen = generated_geometry(pair.name)
        if gen is None:
            print(
                f"{pair.name:46} | {ref_w:>4}x{ref_h:<6} {ref_pp:>6} | "
                f"{'MISSING':>11} {'-':>6} | {'-':>4} {'-':>5}"
            )
            continue
        gen_w, gen_h, gen_pp = gen
        size_match = (ref_w, ref_h) == (gen_w, gen_h)
        pages_match = ref_pp == gen_pp
        size_ok += size_match
        pages_ok += pages_match
        print(
            f"{pair.name:46} | {ref_w:>4}x{ref_h:<6} {ref_pp:>6} | "
            f"{gen_w:>4}x{gen_h:<6} {gen_pp:>6} | "
            f"{('YES' if size_match else 'NO'):>4} {('YES' if pages_match else 'NO'):>5}"
        )

    print("-" * len(header))
    print(f"totals: {size_ok}/{total} size match, {pages_ok}/{total} page-count match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
