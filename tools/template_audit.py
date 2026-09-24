"""Audit the data -> template -> HTML -> PDF path across every document.

Read-only diagnostic: for each document it extracts the structured data, feeds
it to the matching template, prints the result to PDF in a temp dir and verifies
that PDF against the reference. Prints one line per document plus a summary, so
the templated path can be measured exactly like ``sars verify`` measures the
conversion path.

Usage::

    python tools/template_audit.py             # every document
    python tools/template_audit.py "SCHOOLS RANK"
"""

from __future__ import annotations

import sys
import tempfile
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sars import sources, template_maker  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.extract_data import extract_report  # noqa: E402
from sars.verify import tokens, verify  # noqa: E402


def _doc_similarity(reference: Path, generated: Path) -> tuple[float, int, int]:
    """Whole-document content completeness, independent of pagination.

    A template *reflows*: it is handed data and decides its own page breaks, so
    it cannot be expected to reproduce the reference's row-per-page split (and
    for new data there is no reference split to reproduce). What must hold is
    that no value is lost or invented across the document as a whole, which is
    what this measures. Returns ``(similarity, n_missing, n_extra)``.
    """
    ref_c = Counter(tokens(reference))
    out_c = Counter(tokens(generated))
    matched = sum((ref_c & out_c).values())
    total = sum(ref_c.values())
    missing = sum((ref_c - out_c).values())
    extra = sum((out_c - ref_c).values())
    return (matched / total if total else 1.0), missing, extra


def _distinct_loss(reference: Path, generated: Path) -> tuple[list[str], list[str]]:
    """Token *kinds* present in one document and absent from the other.

    The reference repeats its column-header band on every page it spans, while a
    reflowing template repeats it once per page *it* spans - so a page-count
    difference shows up as many "missing" copies of chrome that is in fact
    present. Comparing the distinct token sets ignores that repetition and
    isolates genuine loss: a value the output never prints at all.
    """
    ref_set = set(tokens(reference))
    out_set = set(tokens(generated))
    return sorted(ref_set - out_set), sorted(out_set - ref_set)


@dataclass
class Row:
    name: str
    rtype: str
    page_sim: float
    doc_sim: float
    ref_pages: int
    out_pages: int
    missing: int
    extra: int
    lost_kinds: list[str] = field(default_factory=list)
    new_kinds: list[str] = field(default_factory=list)
    err: str = ""

    @property
    def content_ok(self) -> bool:
        """No token *kind* from the reference is absent from the output."""
        return not self.lost_kinds and not self.err


def audit(only: str | None) -> int:
    rows: list[Row] = []
    tmp = Path(tempfile.mkdtemp(prefix="sars-tmpl-"))

    for pair in sources.select(only):
        try:
            doc = extract_document(pair.pdf, pair.html)
            report = extract_report(doc, pair.name)
            rtype = getattr(getattr(report, "meta", None), "report_type", "?")
            out = tmp / f"{pair.name}.pdf"
            template_maker.render_pdf(rtype, report, out)

            ref = pymupdf.open(pair.pdf)
            orientation = "landscape" if ref[0].rect.width > ref[0].rect.height else "portrait"
            ref_pages = len(ref)
            ref.close()
            gen = pymupdf.open(out)
            out_pages = len(gen)
            gen.close()

            res = verify(pair.pdf, out, orientation)
            doc_sim, missing, extra = _doc_similarity(pair.pdf, out)
            lost, gained = _distinct_loss(pair.pdf, out)
            rows.append(
                Row(
                    pair.name,
                    rtype,
                    res.similarity,
                    doc_sim,
                    ref_pages,
                    out_pages,
                    missing,
                    extra,
                    lost,
                    gained,
                )
            )
        except Exception as exc:  # diagnostic tool: report, never abort the sweep
            rows.append(
                Row(pair.name, "-", 0.0, 0.0, 0, 0, -1, -1, err=f"{type(exc).__name__}: {exc}")
            )
            if "-v" in sys.argv:
                traceback.print_exc()

    width = max(len(r.name) for r in rows)
    for r in rows:
        flag = "OK  " if r.content_ok else "LOSS"
        print(
            f"[{flag}] {r.name:<{width}}  {r.rtype:<22} "
            f"doc={r.doc_sim * 100:6.2f}% lost_kinds={len(r.lost_kinds):3d} "
            f"pages={r.ref_pages}->{r.out_pages} miss={r.missing} extra={r.extra} {r.err}"
        )
        if r.lost_kinds and "-v" in sys.argv:
            print(f"         lost: {r.lost_kinds[:20]}")

    complete = sum(1 for r in rows if r.content_ok)
    same_pages = sum(1 for r in rows if r.ref_pages == r.out_pages and not r.err)
    mean_doc = sum(r.doc_sim for r in rows) / len(rows) if rows else 0.0
    print(
        f"\nsummary  no value lost {complete}/{len(rows)}; "
        f"pagination matches {same_pages}/{len(rows)}; "
        f"mean document similarity {mean_doc * 100:.2f}%"
    )
    return 0 if complete == len(rows) else 1


if __name__ == "__main__":
    arg = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    raise SystemExit(audit(arg))
