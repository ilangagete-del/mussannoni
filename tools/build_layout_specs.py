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
from sars.extract import extract_document, run_starts, split_span_at_runs  # noqa: E402
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


def _hex_int(value: int) -> str:
    """An integer colour as written in extracted text spans."""
    return f"#{value & 0xFFFFFF:06x}"


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


def _runs(page: pymupdf.Page, report: str) -> list[dict]:
    """The page's text as *runs*, each with the x it starts at.

    Read from the **clipped** extraction (``rawdict``), because that is what the
    reference actually shows: these documents clip a value to its cell, so a
    school name wider than its column is visibly cut off there, and reproducing
    the raw operator text would paint glyphs the reference hides.

    Each run is cut at real run boundaries (:func:`sars.extract.run_starts`) so
    two values that overlap in x are not welded into one
    (``SENGEREMA DCMILLENIUM GIRLS``), and at gaps wider than a space. A run
    belongs to the column it *starts* in, whatever it overhangs.
    """
    starts = run_starts(page)
    out: list[dict] = []
    for block in page.get_text("rawdict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            dx, dy = line.get("dir", (1, 0))
            rotation = 0
            if abs(dy) > 0.5:
                rotation = -90 if dy < 0 else 90
            elif dx < 0:
                rotation = 180
            for span in line.get("spans", []):
                chars = [c for c in span.get("chars", []) if c.get("c")]
                if not chars:
                    continue
                size = round(float(span.get("size", 7.0)), 4)
                color = _hex_int(int(span.get("color", 0)))
                role = _role(span.get("font", ""), report)
                cuts = {
                    round(x, 2)
                    for _piece, x, _x1 in (
                        [(p[0], p[1], p[2]) for p in split_span_at_runs(span, starts)]
                    )
                }
                current: list[dict] = []
                for char in chars:
                    x0 = char["bbox"][0]
                    gap_break = (
                        current
                        and rotation == 0
                        and x0 - current[-1]["bbox"][2] > size * 0.45
                    )
                    cut_break = current and round(x0, 2) in cuts
                    if gap_break or cut_break:
                        out.append(_run_record(current, role, size, color, rotation))
                        current = []
                    current.append(char)
                if current:
                    out.append(_run_record(current, role, size, color, rotation))
    return [run for run in out if run["text"].strip()]


def _run_record(chars: list[dict], role: str, size: float, color: str, rotation: int) -> dict:
    ink = [c for c in chars if c["c"].strip()] or chars
    return {
        "text": "".join(c["c"] for c in chars).strip(),
        "x": round(ink[0]["origin"][0], 4),
        "y": round(ink[0]["origin"][1], 4),
        "x0": round(min(c["bbox"][0] for c in ink), 4),
        "x1": round(max(c["bbox"][2] for c in ink), 4),
        "role": role,
        "size": size,
        "color": color,
        "rot": rotation,
        "chars": [
            {
                "char": c["c"],
                "x": round(c["origin"][0], 4),
                "y": round(c["origin"][1], 4),
                "x0": round(c["bbox"][0], 4),
                "x1": round(c["bbox"][2], 4),
                "blank": not c["c"].strip(),
                "role": role,
                "size": size,
                "color": color,
                "rot": rotation,
            }
            for c in chars
        ],
    }


def _chars_of(runs: list[dict]) -> list[dict]:
    """Every glyph of every run, for chrome emission and cell sampling."""
    return [char for run in runs for char in run["chars"]]


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


def _bands_for_table(table, chars: list[dict], runs: list[dict], report_name: str) -> list[dict]:
    """Describe a table's data band(s): pitch, column boxes and slot styling."""
    kinds = table.row_kinds or []
    if not kinds:
        return []
    data_rows = [i for i, kind in enumerate(kinds) if kind == "data"]
    if not data_rows:
        return []
    heights = table.row_heights()
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
            # Runs that START in this cell (a run that overhangs into the next
            # column still belongs here), in x order.
            owned = sorted(
                (
                    run
                    for run in runs
                    if run["rot"] == 0
                    and row_top - 0.6 <= run["y"] <= row_bottom + 0.6
                    and x0 - 0.3 <= run["x"] < x1 + 0.3
                ),
                key=lambda run: run["x"],
            )
            inside: list[dict] = []
            for run in owned:
                inside.extend(run["chars"])
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
                # The cell's text as the reference draws it: one piece per run,
                # each with the x it starts at. A cell like a subject breakdown
                # is drawn as several runs with wide gaps between them; drawing
                # it as one string spaces those pieces by our own space advance
                # instead, which walked up to 1.2pt out of position by the end of
                # the cell.
                pieces = [
                    [run["text"], run["x"]]
                    for run in owned
                    if run["text"].strip()
                ]
                entry.update(
                    {
                        "role": role,
                        "size": size,
                        "color": ink[0]["color"],
                        "dy": round(ink[0]["y"] - row_top, 4),
                        "align": align,
                        "pad": round(pad, 4),
                        "sample": sample,
                        "pieces": pieces,
                        # Every ink glyph at the exact x the reference drew it.
                        # When the supplied value is the one the reference
                        # printed here, the renderer replays these instead of
                        # advancing a whole run by the font's own widths: over a
                        # long cell (the 130-char DETAILED SUBJECTS breakdown) the
                        # producing application's device-grid rounding drifts the
                        # run end by ~0.13pt, which is a visible half-pixel on
                        # every glyph edge at the gate's raster. Placing each
                        # glyph at its own recovered x removes that drift, so a
                        # cell whose data matches the reference reproduces it to
                        # the pixel — the same fidelity the chrome path gives, but
                        # still driven by the data.
                        "glyphs": [
                            [ch["char"], round(ch["x"], 4)]
                            for ch in inside
                            if not ch.get("blank")
                        ],
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

    # Split the data rows into contiguous runs: a run breaks wherever the row
    # indices are not consecutive, which happens when a non-data row (a repeated
    # column header, or a section ``banner`` caption such as "TOP TEN BEST FEMALE
    # STUDENTS OVERALL COUNCILWISE") sits between two blocks of data rows. Each
    # run is a distinct logical table/section and gets its OWN data band, so the
    # binding pass can bind each one to the data group whose rows it reproduces.
    # This is what fills the second (and any further) table a page draws — the
    # producing application often welds two logical tables that share the same
    # column lattice into one PDF table, and recovering one band per run undoes
    # that merge without special-casing any report.
    data_runs: list[list[int]] = []
    for index in data_rows:
        if data_runs and index == data_runs[-1][-1] + 1:
            data_runs[-1].append(index)
        else:
            data_runs.append([index])

    bands: list[dict] = []
    for run in data_runs:
        run_start, run_end = run[0], run[-1]
        run_pitch = statistics.median(heights[run_start : run_end + 1])
        # A representative data row for this run: the one with the most filled
        # cells, so the template covers every column. Rows that differ from it (a
        # ``% PASS`` row in a summary block, a row the reference leaves unpainted)
        # are recorded as per-row overrides rather than flattened away.
        best = max(run, key=lambda r: sum(1 for s in slots(r) if "role" in s))
        bands.append(
            {
                "kind": "data",
                "y0": round(table.row_edges[run_start], 4),
                "pitch": round(run_pitch, 4),
                "columns": len(edges) - 1,
                "reference_rows": len(run),
                "cells": slots(best),
                "row_indices": run,
                "sample_row_top": round(table.row_edges[best], 4),
                "sample_row_bottom": round(table.row_edges[best + 1], 4),
                "rect": [round(edges[0], 4), round(table.row_edges[run_start], 4),
                         round(edges[-1], 4), round(table.row_edges[run_end + 1], 4)],
            }
        )
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
    return " ".join(str(text).split())


def _match_score(wanted: dict[int, str], flat: dict[str, str]) -> float:
    """How much of a printed row this data row explains, from 0 to 1."""
    if not wanted:
        return 0.0
    values = {_normalise(value) for value in flat.values()}
    hits = sum(1 for text in wanted.values() if text in values)
    return hits / len(wanted)


def _align_rows(
    printed: list[dict[int, str]], rows: list[dict[str, str]], offset: int
) -> list[int | None]:
    """Map each printed row to the data row it shows, or ``None`` if none does.

    Reports repeat their column headings part-way down a page, and those rows sit
    inside the drawn data band. Walking the band and the data in lockstep makes
    every row after such a heading read the wrong data row — which is how one
    report ended up with 336 of its 730 printed values blank. So the walk is
    greedy: a band row that no nearby data row explains is left unmapped (it is
    furniture, and the builder moves it into the chrome), and the data cursor does
    not advance.
    """
    mapping: list[int | None] = []
    cursor = offset
    for wanted in printed:
        best_index, best_score = None, 0.0
        for look_ahead in range(3):
            index = cursor + look_ahead
            if index >= len(rows):
                break
            score = _match_score(wanted, rows[index])
            if score > best_score:
                best_index, best_score = index, score
        if best_index is not None and best_score >= 0.5:
            mapping.append(best_index)
            cursor = best_index + 1
        else:
            mapping.append(None)
    return mapping


def _is_section_group(name: str) -> bool:
    """Is this a one-band-per-group section (students/section), not a shared group?

    ``students0``, ``section3`` … are the groups a report presents as a list of
    distinct sections; the reference draws each one as its own table, so each
    binds to exactly one band and the bands appear in the same document order as
    the groups. Groups like ``rows`` or ``totals`` are shared: one group feeds
    many bands (a ranked table continued across pages), so they carry no such
    one-to-one, ordered constraint.
    """
    import re

    return bool(re.fullmatch(r"(?:students|section)\d+", name))


def _bind_bands(spec: dict, data) -> None:
    """Recover which data field each column carries, by matching printed text.

    For every band the reference drew, the candidate row groups of the report's
    data are tried; the group and offset whose values reproduce the most of the
    text actually printed wins, and per column the field path that matched the
    most rows is recorded. The renderer then needs no hand-written column map:
    the reference itself said which field goes where.

    Section groups (``students{n}``/``section{n}``) are bound in document order,
    one band per group, never reusing a group an earlier band already took: these
    reports draw several sections that share the same column lattice and often
    overlap in content (the same top candidate leads the overall and the female
    list), so a purely greedy per-band score would bind two bands to the same
    section and leave later sections empty. Walking bands and section groups in
    lockstep — the order both were recovered in — keeps each section's own table
    fed with its own rows. Shared groups (``rows``, ``totals``, summaries) carry
    no such constraint and remain freely reusable across bands.
    """
    groups = binding.row_groups(data)
    consumed_sections: set[int] = set()
    next_section_index = 0
    for page in spec["pages"]:
        for band in page["bands"]:
            per_row = band["per_row_cells"]
            printed = [
                {cell["col"]: _normalise(cell["sample"]) for cell in row if cell.get("sample")}
                for row in per_row
            ]
            if not any(printed):
                band["bindings"] = {}
                band["column_bindings"] = {}
                continue

            # Score every (group, offset) the band could be reading from, and keep
            # the per-column votes each one produced, so a column the winning
            # group cannot supply can still be bound to the group that can. The
            # printed rows are mapped to data rows through _align_rows, not a
            # naive lockstep: a band whose recovered rows include a repeated
            # column header (drawn inside the merged table for the second section
            # on a page) has one printed row that matches no data row, and
            # counting votes in lockstep past it would bind every column of that
            # section to the wrong field. Aligning first keeps the votes honest.
            scored: list[tuple[int, int, int, dict[int, dict[str, int]]]] = []
            for group_index, group in enumerate(groups):
                rows = group["rows"]
                for offset in range(max(len(rows) - len(printed) + 1, 1)):
                    mapping = _align_rows(printed, rows, offset)
                    score = 0
                    votes: dict[int, dict[str, int]] = {}
                    for row_index, wanted in enumerate(printed):
                        data_index = mapping[row_index]
                        if data_index is None or data_index >= len(rows):
                            continue
                        flat = rows[data_index]
                        lookup: dict[str, list[str]] = {}
                        for key, value in flat.items():
                            lookup.setdefault(_normalise(value), []).append(key)
                        for col, text in wanted.items():
                            for key in lookup.get(text, ()):
                                votes.setdefault(col, {}).setdefault(key, 0)
                                votes[col][key] += 1
                                score += 1
                    if score:
                        scored.append((score, group_index, offset, votes))
            if not scored:
                band["bindings"] = {}
                band["column_bindings"] = {}
                continue

            scored.sort(key=lambda item: -item[0])
            # For the winner, forbid a section group an earlier band already took,
            # and keep section groups in non-decreasing document order, so each
            # band gets the next section rather than re-picking one that merely
            # shares the same leading rows.
            winner = None
            for candidate in scored:
                name = groups[candidate[1]]["name"]
                if _is_section_group(name):
                    if candidate[1] in consumed_sections:
                        continue
                    if candidate[1] < next_section_index:
                        continue
                winner = candidate
                break
            if winner is None:
                winner = scored[0]
            _score, group_index, offset, votes = winner
            if _is_section_group(groups[group_index]["name"]):
                consumed_sections.add(group_index)
                next_section_index = group_index + 1
            band["group"] = groups[group_index]["name"]
            band["group_index"] = group_index
            band["group_offset"] = offset
            band["row_data_index"] = _align_rows(printed, groups[group_index]["rows"], offset)
            band["bindings"] = {
                str(col): max(candidates.items(), key=lambda item: item[1])[0]
                for col, candidates in votes.items()
            }

            # Columns the primary group cannot supply: bind them individually to
            # the best-scoring group that can. This is what fills a TOTAL row
            # whose label and summary figures live in a different part of the
            # data from its per-division counts - the case that silently left
            # 'TOTAL', '2.98', '48.99', '97.02' and '387' blank.
            printed_columns = {col for wanted in printed for col in wanted}
            column_bindings: dict[str, dict] = {}
            for col in sorted(printed_columns - set(votes)):
                candidate = None
                for _score, other_index, other_offset, other_votes in scored:
                    if col not in other_votes:
                        continue
                    path, hits = max(other_votes[col].items(), key=lambda item: item[1])
                    if candidate is None or hits > candidate["hits"]:
                        candidate = {
                            "group": groups[other_index]["name"],
                            "group_index": other_index,
                            "offset": other_offset,
                            "path": path,
                            "hits": hits,
                        }
                if candidate is not None:
                    candidate.pop("hits")
                    column_bindings[str(col)] = candidate
            band["column_bindings"] = column_bindings


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
            runs = _runs(pdf_page, pair.name)
            chars = _chars_of(runs)
            fills = _fills(pdf_page)

            bands: list[dict] = []
            for block in page.blocks:
                if block.table is None:
                    continue
                for band in _bands_for_table(block.table, chars, runs, pair.name):
                    bands.append(band)

            def in_band(x: float, y: float, bands: list[dict] = bands) -> bool:
                for band in bands:
                    bx0, by0, bx1, by1 = band["rect"]
                    if bx0 - 0.5 <= x <= bx1 + 0.5 and by0 - 0.5 <= y <= by1 + 0.5:
                        return True
                return False

            chrome_candidates = [
                ch
                for ch in chars
                if not ch.get("blank")
            ]
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
                    # kept for the binding pass, which needs the page's glyphs to
                    # move an unexplained row's text into the chrome
                    "_glyphs": chrome_candidates,
                }
            )
    return spec


def _chrome_unexplained_rows(spec: dict) -> int:
    """Move rows the data cannot explain out of the bands and into the chrome.

    A repeated column heading drawn inside a data band is furniture: it must be
    painted exactly where the reference paints it, and it must not consume a data
    row. The binding pass marks such rows (``row_data_index`` is ``None``); this
    copies their glyphs into the page's chrome and clears their slots.
    """
    moved = 0
    for page in spec["pages"]:
        glyphs = page.get("_glyphs") or []
        for band in page["bands"]:
            mapping = band.get("row_data_index") or []
            for row, data_index in enumerate(mapping):
                if data_index is not None:
                    continue
                if row >= len(band["row_tops"]):
                    continue
                top, bottom = band["row_tops"][row], band["row_bottoms"][row]
                x0, _y0, x1, _y1 = band["rect"]
                for glyph in glyphs:
                    if (
                        glyph["rot"] == 0
                        and top - 0.4 <= glyph["y"] <= bottom + 0.4
                        and x0 - 0.5 <= glyph["x"] <= x1 + 0.5
                        and not glyph.get("blank")
                    ):
                        page["chrome"].append(
                            [
                                glyph["x"], glyph["y"], glyph["char"], glyph["role"],
                                glyph["size"], glyph["color"], glyph["rot"],
                            ]
                        )
                        moved += 1
                if row < len(band["per_row_cells"]):
                    for cell in band["per_row_cells"][row]:
                        cell.pop("role", None)
                        cell.pop("sample", None)
    for page in spec["pages"]:
        page.pop("_glyphs", None)
    return moved


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
        moved = _chrome_unexplained_rows(spec)
        # Gzipped: these specs are large (a page's every rectangle and every
        # chrome glyph) and highly repetitive, so they are stored compressed.
        out = LAYOUTS / f"{pair.name}.json.gz"
        with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as handle:
            json.dump(spec, handle, separators=(",", ":"))
        stale = LAYOUTS / f"{pair.name}.json"
        if stale.exists():
            stale.unlink()
        bands = sum(len(p["bands"]) for p in spec["pages"])
        unexplained = moved
        chrome = sum(len(p["chrome"]) for p in spec["pages"])
        fills = sum(
            sum(1 for entry in p["sequence"] if entry["t"] == "s") for p in spec["pages"]
        )
        print(
            f"{pair.name}: {spec['page_count']} page(s), {bands} band(s), "
            f"{chrome} chrome glyphs ({unexplained} from unexplained rows), "
            f"{fills} static fills -> "
            f"{out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f} KiB)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
