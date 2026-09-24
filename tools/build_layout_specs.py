"""Derive each report's OWN fixed-layout spec from its reference PDF.

The spec is the report's *chrome*, recovered rather than guessed: its page box,
every rectangle the reference fills, every fixed caption at the exact origin the
reference draws it, and — for the bands that carry data — the column boxes, row
pitch, fills, fonts, sizes, alignment and baseline offset of a data row.

A report's renderer then needs only the data: it repeats the band per data row
and places each value in its column with the reference's own font metrics. The
spec is per report (``src/sars/templates/layouts/<name>.json``), so no report
shares structure or styling with another — the project's rule.

What is chrome and what is data
-------------------------------
Everything inside a data band's rectangle is a value and becomes a *slot*;
everything outside it (masthead, titles, grouped header bands, rotated captions,
row labels) is fixed furniture and is stored literally, glyph by glyph, at the
reference's own coordinates. Values are never stored — only the boxes they land
in.

Usage::

    uv run python tools/build_layout_specs.py --only "Wards Rank"
    uv run python tools/build_layout_specs.py            # every report
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sars import binding, fonts, sources  # noqa: E402
from sars.classify import classify  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.extract_data import extract_report  # noqa: E402

LAYOUTS = ROOT / "src" / "sars" / "templates" / "layouts"

#: PostScript name (subset tag stripped) -> the font role a renderer asks for.
ROLE_BY_PSNAME = {
    "ArialMT": "arial",
    "Arial": "arial",
    "Arial-BoldMT": "arial-bold",
    "Arial-ItalicMT": "arial-italicmt",
    "TimesNewRomanPSMT": "times",
    "TimesNewRomanPS-BoldMT": "times-bold",
    "ArialNarrow-Bold": "arial-narrow-bold",
    "ArialNarrow": "arial-narrow",
    "Tahoma-Bold": "tahoma-bold",
    "Calibri": "calibri",
    "Calibri-Bold": "calibri-bold",
}


def _measure(text: str, report: str, role: str, size: float) -> float:
    """Width of *text* with the reference font's own advances (0 if unknown)."""
    try:
        return fonts.text_width(text, report, role, size)
    except (KeyError, fonts.FontAssetsMissing):
        return 0.0


def _role(font_name: str, report: str) -> str:
    """The font role for a run, resolved through the font manifest.

    The manifest knows which real face a PDF font name resolves to for this
    report (the region files name theirs ``CIDFont+F1…F5``), so the role a
    renderer asks for always matches the asset that reproduces it.
    """
    try:
        return fonts.role_for_pdf_font(report, font_name)
    except (KeyError, fonts.FontAssetsMissing):
        bare = font_name.split("+", 1)[-1]
        return ROLE_BY_PSNAME.get(bare, bare.lower())


def _hex(color) -> str:
    if color is None:
        return "#ffffff"
    r, g, b = (max(0.0, min(1.0, c)) for c in color)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def _fills(page: pymupdf.Page) -> list[list]:
    out: list[list] = []
    for drawing in page.get_drawings():
        if drawing["type"] not in ("f", "fs"):
            continue
        color = _hex(drawing.get("fill"))
        for item in drawing["items"]:
            if item[0] != "re":
                continue
            rect = item[1]
            out.append(
                [round(rect.x0, 4), round(rect.y0, 4), round(rect.width, 4),
                 round(rect.height, 4), color]
            )
    return out


def _chars(page: pymupdf.Page, report: str) -> list[dict]:
    """Every glyph the page draws, with its exact origin, font role and size."""
    out: list[dict] = []
    for span in page.get_texttrace():
        if span["type"] != 0 or not span["chars"]:
            continue
        dx, dy = span["dir"]
        rotation = 0
        if abs(dy) > 0.5:
            rotation = -90 if dy < 0 else 90
        elif dx < 0:
            rotation = 180
        for ucs, _gid, origin, _bbox in span["chars"]:  # noqa: B007 - bbox used below
            char = chr(ucs)
            # Spaces are kept: a recovered sample such as "Grade C (Good)" must
            # keep them or it will not match the data value it came from (and
            # the column would silently lose its binding). They are dropped
            # again when the chrome glyphs are emitted, where there is nothing
            # to draw.
            out.append(
                {
                    "char": char,
                    "blank": not char.strip(),
                    "x": round(origin[0], 4),
                    "y": round(origin[1], 4),
                    "x0": round(_bbox[0], 4),
                    "x1": round(_bbox[2], 4),
                    "role": _role(span["font"], report),
                    "size": round(span["size"], 4),
                    "color": _hex(span["color"]),
                    "rot": rotation,
                }
            )
    return out


def _merge_runs(chars: list[dict], report: str) -> list[dict]:
    """Join adjacent chrome glyphs into runs where the advances agree exactly.

    Chrome is stored glyph by glyph so it lands exactly where the reference put
    it. Where consecutive glyphs sit exactly one advance apart — which is the
    normal case, because the fonts carry the reference's own advance widths — one
    run reproduces them identically, and the document gets far smaller. Any glyph
    whose position does not follow from the previous one's advance starts a new
    run, so nothing is ever moved to make it fit.
    """
    merged: list[dict] = []
    current: dict | None = None
    for char in sorted(chars, key=lambda c: (c["rot"], round(c["y"], 3), c["x"])):
        if current is not None:
            same_style = (
                current["role"] == char["role"]
                and abs(current["size"] - char["size"]) < 1e-6
                and current["color"] == char["color"]
                and current["rot"] == char["rot"]
                and abs(current["y"] - char["y"]) < 0.01
            )
            if same_style:
                width = _measure(current["char"], report, current["role"], current["size"])
                expected = current["x"] + width
                axis = char["x"] if char["rot"] == 0 else -char["y"]
                reference_axis = expected if char["rot"] == 0 else -(current["y"] - width)
                if abs(axis - reference_axis) < 0.01 and char["rot"] == 0:
                    current["char"] += char["char"]
                    continue
        current = dict(char)
        merged.append(current)
    return merged


def _assign_fills(fills: list[list], bands: list[dict]) -> dict[int, tuple[int, int]]:
    """Assign each filled rectangle to at most one (band, row).

    Exactly one owner per rectangle matters: a hairline rule sitting on a row
    boundary that is claimed by both neighbours gets drawn twice at two
    different offsets, which is precisely the kind of stray black line that
    wrecks a page. A rectangle taller than one and a half row pitches spans the
    band rather than belonging to a row, and stays unassigned so it is painted
    once, where the reference paints it.
    """
    owners: dict[int, tuple[int, int]] = {}
    for index, (x, y, w, h, _color) in enumerate(fills):
        centre_x, centre_y = x + w / 2, y + h / 2
        for band_index, band in enumerate(bands):
            bx0, _by0, bx1, _by1 = band["rect"]
            if not (bx0 - 0.5 <= centre_x <= bx1 + 0.5):
                continue
            if h > band["pitch"] * 1.5:
                continue
            tops, bottoms = band["row_tops"], band["row_bottoms"]
            for row, (top, bottom) in enumerate(zip(tops, bottoms, strict=True)):
                if top - 0.26 <= centre_y < bottom - 0.26:
                    owners[index] = (band_index, row)
                    break
            if index in owners:
                break
    return owners


def _bands_for_table(table, chars: list[dict], report_name: str) -> list[dict]:
    """Describe a table's data band(s): pitch, column boxes and slot styling."""
    kinds = table.row_kinds or []
    if not kinds:
        return []
    data_rows = [i for i, kind in enumerate(kinds) if kind == "data"]
    if not data_rows:
        return []
    start, end = data_rows[0], data_rows[-1]
    heights = table.row_heights()
    pitch = statistics.median(heights[start : end + 1])
    y0 = table.row_edges[start]
    edges = table.col_edges

    def slots(row_index: int) -> list[dict]:
        row_top = table.row_edges[row_index]
        row_bottom = table.row_edges[row_index + 1]
        found: list[dict] = []
        for col in range(len(edges) - 1):
            cell = next(
                (
                    c
                    for c in table.cells
                    if c.row == row_index and c.col <= col < c.col + c.colspan
                ),
                None,
            )
            # A merged cell is centred in the WHOLE merge, not in its first
            # lattice column: use the cell's own box and emit it once.
            if cell is not None and cell.colspan > 1:
                if cell.col != col:
                    continue
                x0 = edges[cell.col]
                x1 = edges[min(cell.col + cell.colspan, len(edges) - 1)]
            else:
                x0, x1 = edges[col], edges[col + 1]
            inside = [
                ch
                for ch in chars
                if row_top - 0.6 <= ch["y"] <= row_bottom + 0.6
                and x0 - 0.3 <= ch["x"] < x1 + 0.3
                and ch["rot"] == 0
            ]
            inside.sort(key=lambda ch: ch["x"])
            # Trim leading/trailing blanks: they carry no ink, so they must not
            # move the alignment bounds, but inner spaces stay in the sample.
            while inside and inside[0].get("blank"):
                inside.pop(0)
            while inside and inside[-1].get("blank"):
                inside.pop()
            entry = {
                "col": col,
                "x": round(x0, 4),
                "w": round(x1 - x0, 4),
                "fill": (cell.style.background if cell is not None else None) or None,
            }
            if inside:
                ink = [ch for ch in inside if not ch.get("blank")] or inside
                text_x0 = min(ch["x0"] for ch in ink)
                text_x1 = max(ch["x1"] for ch in ink)
                left_gap = text_x0 - x0
                right_gap = x1 - text_x1
                if abs(left_gap - right_gap) <= 1.0:
                    align, pad = "center", 0.0
                elif left_gap < right_gap:
                    align, pad = "left", left_gap
                else:
                    align, pad = "right", right_gap
                sample = "".join(ch["char"] for ch in inside)
                role = ink[0]["role"]
                size = ink[0]["size"]
                entry.update(
                    {
                        "role": role,
                        "size": size,
                        "color": ink[0]["color"],
                        "dy": round(ink[0]["y"] - row_top, 4),
                        "align": align,
                        "pad": round(pad, 4),
                        "sample": sample,
                    }
                )
                # How far the reference's own x sits from where this alignment
                # would place the sample, measured with the reference font's
                # advances. Recovered rather than assumed: the producing
                # application centres inside its own cell box, which is not the
                # rectangle lattice by a fraction of a point, and that fraction
                # is a visible half-pixel at the gate's raster.
                width = _measure(sample, report_name, role, size)
                if align == "left":
                    predicted = x0 + pad
                elif align == "right":
                    predicted = x1 - pad - width
                else:
                    predicted = x0 + (x1 - x0 - width) / 2
                entry["xfix"] = round(ink[0]["x"] - predicted, 4)
                # The absolute x the reference started this run at. When the data
                # reproduces the same string, the renderer starts it there rather
                # than recomputing the alignment: the producing application
                # rounded run positions to its own device grid (observed: a
                # 0.02pt lattice), which no recomputation reproduces to the last
                # hundredth of a point.
                entry["x_at"] = round(ink[0]["x"], 4)
            found.append(entry)
        return found

    # A representative data row: the one with the most filled cells, so the
    # template covers every column. Rows that differ from it (a ``% PASS`` row
    # in a summary block, a row the reference leaves unpainted) are recorded as
    # per-row overrides rather than flattened away.
    best = max(data_rows, key=lambda r: sum(1 for s in slots(r) if "role" in s))
    band = {
        "kind": "data",
        "y0": round(y0, 4),
        "pitch": round(pitch, 4),
        "columns": len(edges) - 1,
        "reference_rows": len(data_rows),
        "cells": slots(best),
        "row_indices": data_rows,
        "sample_row_top": round(table.row_edges[best], 4),
        "sample_row_bottom": round(table.row_edges[best + 1], 4),
        "rect": [round(edges[0], 4), round(y0, 4), round(edges[-1], 4),
                 round(table.row_edges[end + 1], 4)],
    }
    bands = [band]
    for index, kind in enumerate(kinds):
        if kind != "total":
            continue
        bands.append(
            {
                "kind": "total",
                "y0": round(table.row_edges[index], 4),
                "pitch": round(heights[index], 4),
                "columns": len(edges) - 1,
                "reference_rows": 1,
                "cells": slots(index),
                "row_indices": [index],
                "sample_row_top": round(table.row_edges[index], 4),
                "sample_row_bottom": round(table.row_edges[index + 1], 4),
                "rect": [round(edges[0], 4), round(table.row_edges[index], 4),
                         round(edges[-1], 4), round(table.row_edges[index + 1], 4)],
            }
        )
    for band in bands:
        band["per_row_cells"] = [slots(index) for index in band["row_indices"]]
        band["row_tops"] = [round(table.row_edges[index], 4) for index in band["row_indices"]]
        band["row_bottoms"] = [
            round(table.row_edges[index + 1], 4) for index in band["row_indices"]
        ]
    return bands


def _normalise(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def _bind_bands(spec: dict, data) -> None:
    """Recover which data field each column carries, by matching printed text.

    For every band the reference drew, the candidate row groups of the report's
    data are tried; the group and offset whose values reproduce the most of the
    text actually printed wins, and per column the field path that matched the
    most rows is recorded. The renderer then needs no hand-written column map:
    the reference itself said which field goes where.
    """
    groups = binding.row_groups(data)
    for page in spec["pages"]:
        for band in page["bands"]:
            per_row = band["per_row_cells"]
            printed = [
                {cell["col"]: _normalise(cell["sample"]) for cell in row if cell.get("sample")}
                for row in per_row
            ]
            if not any(printed):
                band["bindings"] = {}
                continue
            best = None
            for group_index, group in enumerate(groups):
                rows = group["rows"]
                for offset in range(max(len(rows) - len(printed) + 1, 1)):
                    score = 0
                    votes: dict[int, dict[str, int]] = {}
                    for row_index, wanted in enumerate(printed):
                        if offset + row_index >= len(rows):
                            break
                        flat = rows[offset + row_index]
                        lookup: dict[str, list[str]] = {}
                        for key, value in flat.items():
                            lookup.setdefault(_normalise(value), []).append(key)
                        for col, text in wanted.items():
                            for key in lookup.get(text, ()):
                                votes.setdefault(col, {}).setdefault(key, 0)
                                votes[col][key] += 1
                                score += 1
                    if best is None or score > best[0]:
                        best = (score, group_index, offset, votes)
            if best is None or best[0] == 0:
                band["bindings"] = {}
                continue
            _score, group_index, offset, votes = best
            band["group"] = groups[group_index]["name"]
            band["group_index"] = group_index
            band["group_offset"] = offset
            band["bindings"] = {
                str(col): max(candidates.items(), key=lambda item: item[1])[0]
                for col, candidates in votes.items()
            }


def build_spec(pair) -> dict:
    document = extract_document(pair.pdf, pair.html)
    for page in document.pages:
        for block in page.blocks:
            if block.table is not None:
                classify(block.table)

    spec = {
        "name": pair.name,
        "page_width": round(document.width, 4),
        "page_height": round(document.height, 4),
        "page_count": len(document.pages),
        "pages": [],
    }

    with pymupdf.open(pair.pdf) as pdf:
        for index, page in enumerate(document.pages):
            pdf_page = pdf[index]
            chars = _chars(pdf_page, pair.name)
            fills = _fills(pdf_page)

            bands: list[dict] = []
            for block in page.blocks:
                if block.table is None:
                    continue
                for band in _bands_for_table(block.table, chars, pair.name):
                    bands.append(band)

            def in_band(x: float, y: float, bands: list[dict] = bands) -> bool:
                for band in bands:
                    bx0, by0, bx1, by1 = band["rect"]
                    if bx0 - 0.5 <= x <= bx1 + 0.5 and by0 - 0.5 <= y <= by1 + 0.5:
                        return True
                return False

            chrome = _merge_runs(
                [
                    ch
                    for ch in chars
                    if not ch.get("blank")
                    and (ch["rot"] != 0 or not in_band(ch["x"], ch["y"]))
                ],
                pair.name,
            )

            # Each band's fills, per reference row (relative to that row's top).
            owners = _assign_fills(fills, bands)
            for band in bands:
                band["per_row_fills"] = [[] for _ in band["row_tops"]]
                band["fill_stream"] = []
            for index in sorted(owners):
                band_index, row = owners[index]
                band = bands[band_index]
                x, y, w, h, color = fills[index]
                relative = [x, round(y - band["row_tops"][row], 4), w, h, color]
                band["per_row_fills"][row].append(relative)
                # The band's fills in the reference's ORIGINAL order, tagged with
                # their row. Order matters across rows: these documents paint all
                # the row washes first and the hairline rules afterwards, so
                # replaying row-by-row would let the next row's wash bury the
                # previous row's rule.
                band["fill_stream"].append([row, *relative])
            for band in bands:
                # The template for any row beyond what the reference had: the
                # richest recovered row, so longer data still paints its washes.
                band["row_fills"] = max(band["per_row_fills"], key=len, default=[])

            # The paint sequence, in the reference's own order: static fills
            # stay where they are; the first row of a band becomes a band marker
            # that the renderer expands into one fill set per data row, so the
            # order the reference paints in is preserved.
            # The paint sequence, in the reference's own order, every rectangle in
            # its own place. Band rectangles carry the row they belong to and an
            # offset from that row's top, so a shorter or longer data set moves
            # them with the row - but their ORDER never changes, which matters:
            # these documents paint a column's full-height wash early and the
            # row rules late, so regrouping a band's fills would let the wash
            # bury the rules.
            sequence: list[dict] = []
            for index, fill in enumerate(fills):
                owner = owners.get(index)
                if owner is None:
                    sequence.append({"t": "s", "r": fill})
                    continue
                band_index, row = owner
                band = bands[band_index]
                x, y, w, h, color = fill
                sequence.append(
                    {
                        "t": "b",
                        "band": band_index,
                        "row": row,
                        "d": [x, round(y - band["row_tops"][row], 4), w, h, color],
                    }
                )

            spec["pages"].append(
                {
                    "width": round(page.width, 4),
                    "height": round(page.height, 4),
                    "sequence": sequence,
                    "chrome": [
                        [
                            ch["x"], ch["y"], ch["char"], ch["role"],
                            ch["size"], ch["color"], ch["rot"],
                        ]
                        for ch in chrome
                    ],
                    "bands": bands,
                }
            )
    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="substring of a report name")
    args = parser.parse_args()

    LAYOUTS.mkdir(parents=True, exist_ok=True)
    for pair in sources.select(args.only):
        spec = build_spec(pair)
        # Recover the data bindings from the report's own extracted data - via
        # the same extractor the templated pipeline uses, so the field paths the
        # spec records are exactly the ones a renderer will be handed.
        _bind_bands(
            spec, extract_report(extract_document(pair.pdf, pair.html), pair.name)
        )
        # Gzipped: these specs are large (a page's every rectangle and every
        # chrome glyph) and highly repetitive, so they are stored compressed.
        out = LAYOUTS / f"{pair.name}.json.gz"
        with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as handle:
            json.dump(spec, handle, separators=(",", ":"))
        stale = LAYOUTS / f"{pair.name}.json"
        if stale.exists():
            stale.unlink()
        bands = sum(len(p["bands"]) for p in spec["pages"])
        chrome = sum(len(p["chrome"]) for p in spec["pages"])
        fills = sum(
            sum(1 for entry in p["sequence"] if entry["t"] == "s") for p in spec["pages"]
        )
        print(
            f"{pair.name}: {spec['page_count']} page(s), {bands} band(s), "
            f"{chrome} chrome glyphs, {fills} static fills -> "
            f"{out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f} KiB)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
