"""FIDELITY GATE — the single definition of done for report reproduction.

This tool is the acceptance criterion demanded by ``docs/FIDELITY_SPEC.md``. It
compares every page of every report's generated PDF against its reference PDF
and **exits non-zero unless every page of every report is a 100% pixel match**.

It deliberately measures only pixels. Text similarity, page counts and page
sizes are *diagnostics*: a page-count/page-size mismatch is a HARD FAIL (it
cannot be a match), but agreeing on them proves nothing on its own.

What it does, per report:

1. Hard-fail if the page **count** differs from the reference.
2. Hard-fail if any page's **size in points** differs from the reference.
3. Rasterise both PDFs page by page, losslessly, with the *same* matrix, and
   require identical pixel dimensions (dimension-locked).
4. Per page report two numbers:

   * ``exact``   — share of pixels whose RGB delta is exactly 0;
   * ``visible`` — share of pixels whose max RGB channel delta is <= 8
     (anything above that is a visible difference, not rasteriser noise).

The gate is keyed on ``visible`` at 100.0%, and also reports the worst page
across all reports so progress is impossible to fake by sampling.

Usage::

    uv run python tools/fidelity_gate.py                  # all reports, all pages
    uv run python tools/fidelity_gate.py --only "WARDS"   # one report
    uv run python tools/fidelity_gate.py --pages 1        # DIAGNOSTIC ONLY
    uv run python tools/fidelity_gate.py --json output/fidelity/gate.json

Nothing here may be weakened to make a report pass: the threshold, the zoom, the
tolerance and the "every page" rule are the contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

#: Rasterisation zoom. 2x = 144 dpi; every pixel of the page is compared.
ZOOM = 2.0
#: Max RGB channel delta still counted as "not visibly different".
VISIBLE_TOLERANCE = 8
#: Required match, in percent, on every page of every report.
TARGET_PCT = 100.0
#: Page size agreement tolerance in points (PDF boxes are stored as floats).
SIZE_TOLERANCE_PT = 0.05


@dataclass
class PageResult:
    page: int
    width_pt: float
    height_pt: float
    pixels: int
    exact_pct: float
    visible_pct: float
    max_delta: int
    worst_band: tuple[int, int] | None = None

    @property
    def ok(self) -> bool:
        return self.visible_pct >= TARGET_PCT


@dataclass
class ReportResult:
    name: str
    reference: Path
    generated: Path
    pages: list[PageResult] = field(default_factory=list)
    hard_fail: str | None = None

    @property
    def ok(self) -> bool:
        return self.hard_fail is None and bool(self.pages) and all(p.ok for p in self.pages)

    @property
    def worst_visible(self) -> float:
        return min((p.visible_pct for p in self.pages), default=0.0)

    @property
    def worst_exact(self) -> float:
        return min((p.exact_pct for p in self.pages), default=0.0)


def _raster(document: pymupdf.Document, index: int, zoom: float) -> np.ndarray:
    pixmap = document[index].get_pixmap(
        matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csRGB
    )
    array = np.frombuffer(pixmap.samples, dtype=np.uint8)
    return array.reshape(pixmap.height, pixmap.width, 3)


def _worst_band(delta: np.ndarray, bands: int = 12) -> tuple[int, int] | None:
    """Return (band index, bands) of the horizontal band with most bad pixels.

    A cheap locator so a failing page says *where* it fails without writing any
    image files.
    """
    bad = delta > VISIBLE_TOLERANCE
    if not bad.any():
        return None
    height = bad.shape[0]
    step = max(height // bands, 1)
    counts = [bad[i * step : (i + 1) * step].sum() for i in range(bands)]
    return int(max(range(bands), key=lambda i: counts[i])), bands


def compare_report(name: str, reference: Path, generated: Path, *, zoom: float = ZOOM,
                   pages: int | None = None) -> ReportResult:
    """Compare one report's generated PDF against its reference, page by page."""
    result = ReportResult(name=name, reference=reference, generated=generated)
    if not generated.exists():
        result.hard_fail = f"generated PDF missing ({generated.relative_to(ROOT)})"
        return result

    with pymupdf.open(reference) as ref_doc, pymupdf.open(generated) as gen_doc:
        if ref_doc.page_count != gen_doc.page_count:
            result.hard_fail = (
                f"page count {gen_doc.page_count} != reference {ref_doc.page_count}"
            )
            return result

        limit = ref_doc.page_count if pages is None else min(pages, ref_doc.page_count)
        for index in range(limit):
            ref_rect, gen_rect = ref_doc[index].rect, gen_doc[index].rect
            if (
                abs(ref_rect.width - gen_rect.width) > SIZE_TOLERANCE_PT
                or abs(ref_rect.height - gen_rect.height) > SIZE_TOLERANCE_PT
            ):
                result.hard_fail = (
                    f"page {index + 1} size {gen_rect.width:.2f}x{gen_rect.height:.2f}pt "
                    f"!= reference {ref_rect.width:.2f}x{ref_rect.height:.2f}pt"
                )
                return result

            ref_img = _raster(ref_doc, index, zoom)
            gen_img = _raster(gen_doc, index, zoom)
            if ref_img.shape != gen_img.shape:
                result.hard_fail = (
                    f"page {index + 1} raster {gen_img.shape} != reference {ref_img.shape}"
                )
                return result

            delta = np.abs(ref_img.astype(np.int16) - gen_img.astype(np.int16)).max(axis=2)
            total = delta.size
            exact_bad = int(np.count_nonzero(delta))
            visible_bad = int(np.count_nonzero(delta > VISIBLE_TOLERANCE))
            result.pages.append(
                PageResult(
                    page=index + 1,
                    width_pt=round(ref_rect.width, 2),
                    height_pt=round(ref_rect.height, 2),
                    pixels=total,
                    exact_pct=100.0 * (total - exact_bad) / total,
                    visible_pct=100.0 * (total - visible_bad) / total,
                    max_delta=int(delta.max()),
                    worst_band=_worst_band(delta),
                )
            )
    return result


def _discover(only: str | None):
    from sars import sources

    return sources.select(only) if only else sources.discover()


def run(only: str | None = None, *, templated: bool = True, zoom: float = ZOOM,
        pages: int | None = None, quiet: bool = False) -> list[ReportResult]:
    directory = "template_pdf" if templated else "pdf"
    results: list[ReportResult] = []
    for pair in sorted(_discover(only), key=lambda p: p.name.casefold()):
        generated = ROOT / "output" / directory / f"{pair.name}.pdf"
        result = compare_report(pair.name, pair.pdf, generated, zoom=zoom, pages=pages)
        results.append(result)
        if not quiet:
            _print_report(result)
    return results


def _print_report(result: ReportResult) -> None:
    if result.hard_fail:
        print(f"{result.name}\n    HARD FAIL: {result.hard_fail}", flush=True)
        return
    flag = "PASS" if result.ok else "FAIL"
    print(
        f"{result.name}\n"
        f"    {flag}  worst page visible {result.worst_visible:7.4f}%  "
        f"exact {result.worst_exact:7.4f}%  ({len(result.pages)} page(s))",
        flush=True,
    )
    for page in result.pages:
        where = ""
        if page.worst_band is not None:
            band, bands = page.worst_band
            where = f"  worst band {band + 1}/{bands}"
        print(
            f"      p{page.page:<3d} {page.width_pt:6.1f}x{page.height_pt:6.1f}pt  "
            f"visible {page.visible_pct:8.4f}%  exact {page.exact_pct:8.4f}%  "
            f"max_delta {page.max_delta:3d}{where}",
            flush=True,
        )


def summarise(results: list[ReportResult]) -> tuple[int, int, float]:
    passed = sum(1 for r in results if r.ok)
    worst = min((r.worst_visible for r in results if not r.hard_fail), default=0.0)
    if any(r.hard_fail for r in results):
        worst = 0.0
    return passed, len(results), worst


def to_json(results: list[ReportResult]) -> dict:
    passed, total, worst = summarise(results)
    return {
        "zoom": ZOOM,
        "visible_tolerance": VISIBLE_TOLERANCE,
        "target_pct": TARGET_PCT,
        "passed": passed,
        "total": total,
        "worst_page_visible_pct": worst,
        "reports": [
            {
                "name": r.name,
                "ok": r.ok,
                "hard_fail": r.hard_fail,
                "page_count": len(r.pages),
                "worst_visible_pct": r.worst_visible,
                "worst_exact_pct": r.worst_exact,
                "pages": [
                    {
                        "page": p.page,
                        "size_pt": [p.width_pt, p.height_pt],
                        "visible_pct": p.visible_pct,
                        "exact_pct": p.exact_pct,
                        "max_delta": p.max_delta,
                    }
                    for p in r.pages
                ],
            }
            for r in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="substring of one report name")
    parser.add_argument(
        "--conversion",
        action="store_true",
        help="gate output/pdf (conversion path) instead of output/template_pdf",
    )
    parser.add_argument("--zoom", type=float, default=ZOOM, help="raster zoom (default 2.0)")
    parser.add_argument(
        "--pages",
        type=int,
        default=None,
        help="DIAGNOSTIC ONLY: limit pages per report. Never use to claim a pass.",
    )
    parser.add_argument("--json", type=Path, help="also write the results as JSON")
    args = parser.parse_args(argv)

    label = "conversion" if args.conversion else "templated"
    scope = f" (first {args.pages} page(s) — DIAGNOSTIC, not a pass)" if args.pages else ""
    print(
        f"fidelity gate — {label} output vs reference PDFs @ {args.zoom:g}x, "
        f"target {TARGET_PCT:.0f}% visible match on EVERY page{scope}\n"
    )

    results = run(args.only, templated=not args.conversion, zoom=args.zoom, pages=args.pages)
    passed, total, worst = summarise(results)

    print()
    failing = [r for r in results if not r.ok]
    if failing:
        print("failing reports (worst page visible %):")
        for r in sorted(failing, key=lambda r: r.worst_visible):
            detail = r.hard_fail or f"{r.worst_visible:.4f}%"
            print(f"    {r.name}: {detail}")
        print()
    print(f"PASS {passed}/{total}")
    print(f"worst page across all reports = {worst:.4f}% visible")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(to_json(results), indent=2), encoding="utf-8")
        print(f"json -> {args.json}")

    if args.pages:
        print("\nNOTE: --pages was used; this run is a diagnostic and cannot be a pass.")
        return 1
    return 0 if passed == total and total else 1


if __name__ == "__main__":
    raise SystemExit(main())
