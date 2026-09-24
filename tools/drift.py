"""Glyph-level drift: where does a generated PDF put text vs the reference?

Pixels say *how much* is wrong; this says *what* is wrong. It matches the glyphs
of a generated PDF against the reference's glyphs (same page, same character,
nearest position) and reports the position error distribution, plus the glyphs
that are missing or extra.

Because both documents are PDFs, this is an exact measurement of the renderer's
geometry error - the feedback loop for making a report's layout right.

Usage::

    uv run python tools/drift.py "Wards Rank"                 # templated output
    uv run python tools/drift.py "Wards Rank" --replay        # oracle replay
    uv run python tools/drift.py "Wards Rank" --page 2 --list 40
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sars import sources  # noqa: E402


def glyphs(pdf: Path, index: int) -> list[tuple[str, float, float, float]]:
    out: list[tuple[str, float, float, float]] = []
    with pymupdf.open(pdf) as doc:
        if index >= doc.page_count:
            return out
        for span in doc[index].get_texttrace():
            if span["type"] != 0:
                continue
            for ucs, _gid, origin, _bbox in span["chars"]:
                char = chr(ucs)
                if not char.strip():
                    continue
                out.append((char, round(origin[0], 4), round(origin[1], 4), round(span["size"], 4)))
    return out


def fills(pdf: Path, index: int) -> list[tuple[float, float, float, float, str]]:
    """Every filled rectangle on a page: (x, y, w, h, colour)."""
    out: list[tuple[float, float, float, float, str]] = []
    with pymupdf.open(pdf) as doc:
        if index >= doc.page_count:
            return out
        for drawing in doc[index].get_drawings():
            if drawing["type"] not in ("f", "fs"):
                continue
            color = drawing.get("fill")
            if color is None:
                hexed = "none"
            else:
                hexed = "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in color)
            for item in drawing["items"]:
                if item[0] != "re":
                    continue
                rect = item[1]
                out.append(
                    (round(rect.x0, 3), round(rect.y0, 3), round(rect.width, 3),
                     round(rect.height, 3), hexed)
                )
    return out


def compare_fills(reference: Path, generated: Path, index: int, listing: int = 12) -> dict:
    """Match the generated page's rectangles against the reference's."""
    ref, gen = fills(reference, index), fills(generated, index)
    pool = list(gen)
    exact = 0
    shifted: list[tuple[float, tuple, tuple]] = []
    missing: list[tuple] = []
    for rect in ref:
        if rect in pool:
            pool.remove(rect)
            exact += 1
            continue
        # nearest candidate of the same colour and size
        best, best_d = None, None
        for candidate in pool:
            if candidate[4] != rect[4]:
                continue
            d = (
                abs(candidate[0] - rect[0]) + abs(candidate[1] - rect[1])
                + abs(candidate[2] - rect[2]) + abs(candidate[3] - rect[3])
            )
            if best_d is None or d < best_d:
                best, best_d = candidate, d
        if best is not None and best_d is not None and best_d < 4.0:
            pool.remove(best)
            shifted.append((best_d, rect, best))
        else:
            missing.append(rect)
    shifted.sort(reverse=True)
    return {
        "ref": len(ref),
        "gen": len(gen),
        "exact": exact,
        "shifted": shifted[:listing],
        "shifted_count": len(shifted),
        "missing": missing[:listing],
        "missing_count": len(missing),
        "extra": pool[:listing],
        "extra_count": len(pool),
    }


def compare(reference: Path, generated: Path, index: int, listing: int = 12) -> dict:
    ref, gen = glyphs(reference, index), glyphs(generated, index)
    by_char: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    for char, x, y, size in gen:
        by_char[char].append((x, y, size))

    dxs: list[float] = []
    dys: list[float] = []
    missing: Counter[str] = Counter()
    worst: list[tuple[float, str, float, float, float, float]] = []
    for char, x, y, _size in ref:
        pool = by_char.get(char)
        if not pool:
            missing[char] += 1
            continue
        best_i, best_d = None, None
        for i, (gx, gy, _gs) in enumerate(pool):
            d = abs(gx - x) + abs(gy - y)
            if best_d is None or d < best_d:
                best_i, best_d = i, d
        gx, gy, _gs = pool.pop(best_i)
        dxs.append(gx - x)
        dys.append(gy - y)
        worst.append((max(abs(gx - x), abs(gy - y)), char, x, y, gx - x, gy - y))

    extra = sum(len(v) for v in by_char.values())
    result = {
        "page": index + 1,
        "ref_glyphs": len(ref),
        "gen_glyphs": len(gen),
        "matched": len(dxs),
        "missing": sum(missing.values()),
        "missing_chars": missing.most_common(10),
        "extra": extra,
    }
    if dxs:
        result.update(
            {
                "dx_mean": statistics.fmean(dxs),
                "dy_mean": statistics.fmean(dys),
                "dx_max": max(dxs, key=abs),
                "dy_max": max(dys, key=abs),
                "within_0.01pt": sum(
                    1 for dx, dy in zip(dxs, dys, strict=True)
                    if abs(dx) <= 0.01 and abs(dy) <= 0.01
                ),
                "within_0.1pt": sum(
                    1 for dx, dy in zip(dxs, dys, strict=True)
                    if abs(dx) <= 0.1 and abs(dy) <= 0.1
                ),
                "within_0.5pt": sum(
                    1 for dx, dy in zip(dxs, dys, strict=True)
                    if abs(dx) <= 0.5 and abs(dy) <= 0.5
                ),
            }
        )
    worst.sort(reverse=True)
    result["worst"] = worst[:listing]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="substring of a report name")
    parser.add_argument("--page", type=int, default=0, help="page (1-based); 0 = every page")
    parser.add_argument("--replay", action="store_true", help="compare the oracle replay output")
    parser.add_argument("--conversion", action="store_true", help="compare the conversion output")
    parser.add_argument("--list", type=int, default=12, help="how many worst glyphs to list")
    args = parser.parse_args()

    pairs = sources.select(args.name)
    if len(pairs) != 1:
        print("name must select exactly one report: " + ", ".join(p.name for p in pairs))
        return 2
    pair = pairs[0]
    directory = "replay_pdf" if args.replay else ("pdf" if args.conversion else "template_pdf")
    generated = ROOT / "output" / directory / f"{pair.name}.pdf"
    if not generated.exists():
        print(f"missing {generated}")
        return 2

    with pymupdf.open(pair.pdf) as doc:
        pages = range(doc.page_count) if args.page == 0 else [args.page - 1]

    for index in pages:
        result = compare(pair.pdf, generated, index, args.list)
        print(
            f"{pair.name} p{result['page']}: ref {result['ref_glyphs']} glyphs, "
            f"generated {result['gen_glyphs']}, matched {result['matched']}, "
            f"missing {result['missing']}, extra {result['extra']}"
        )
        if result["missing_chars"]:
            print(f"    missing chars: {result['missing_chars']}")
        if result["matched"]:
            print(
                f"    dx mean {result['dx_mean']:+.4f} max {result['dx_max']:+.4f} | "
                f"dy mean {result['dy_mean']:+.4f} max {result['dy_max']:+.4f}"
            )
            n = result["matched"]
            print(
                f"    within 0.01pt {result['within_0.01pt']}/{n} "
                f"({100 * result['within_0.01pt'] / n:.1f}%), "
                f"0.1pt {100 * result['within_0.1pt'] / n:.1f}%, "
                f"0.5pt {100 * result['within_0.5pt'] / n:.1f}%"
            )
            for _d, char, x, y, dx, dy in result["worst"]:
                print(f"      {char!r} at ({x:.2f},{y:.2f}) dx={dx:+.3f} dy={dy:+.3f}")

        rects = compare_fills(pair.pdf, generated, index, args.list)
        print(
            f"    fills: reference {rects['ref']}, generated {rects['gen']}, "
            f"identical {rects['exact']}, shifted {rects['shifted_count']}, "
            f"missing {rects['missing_count']}, extra {rects['extra_count']}"
        )
        for d, want, got in rects["shifted"]:
            print(
                f"      shifted by {d:.3f}: reference {want} -> generated {got}"
            )
        for rect in rects["missing"]:
            print(f"      missing {rect}")
        for rect in rects["extra"]:
            print(f"      extra   {rect}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
