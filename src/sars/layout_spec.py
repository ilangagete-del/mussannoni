"""Draw a report from its own recovered layout spec plus fresh data.

``tools/build_layout_specs.py`` recovers a report's chrome from its reference PDF
into ``src/sars/templates/layouts/<report>.json``: the page box, the paint
sequence of every rectangle, every fixed caption at its exact origin, and — for
the bands that carry values — the column boxes, row pitch, fills, fonts, sizes,
alignment and baseline offset of a data row.

This module renders that spec with data supplied by the caller. It is a
*mechanism*: it holds no colours, sizes, fonts or geometry of its own, and each
report keeps its own spec file and its own data mapping, so no report's look is
shared with another's. What it guarantees is placement: a value lands in its
column, on the reference's baseline, measured with the reference's own font
advances, and painted over the reference's own fills.

The data contract is one callback::

    values(band_index, band_kind, row_index) -> list[str] | dict[int, str] | None

returning the values for one row of one band (``None`` ends the band early).
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import printing
from .layout import Box, Canvas, StyleBook, document

LAYOUTS = Path(__file__).resolve().parent / "templates" / "layouts"

#: ``values(page, band, kind, row) -> the row's values, or None to end the band``
ValueProvider = Callable[[int, int, str, int], "Sequence[str] | dict[int, str] | None"]


class LayoutSpecMissing(FileNotFoundError):
    """Raised when a report has no recovered layout spec yet."""


def _spec_path(report: str) -> Path | None:
    """The report's spec file: gzipped by default, plain JSON also accepted."""
    for candidate in (LAYOUTS / f"{report}.json.gz", LAYOUTS / f"{report}.json"):
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=32)
def load(report: str) -> dict:
    path = _spec_path(report)
    if path is None:
        raise LayoutSpecMissing(
            f"no layout spec for {report!r} — run "
            f"`uv run python tools/build_layout_specs.py --only {report!r}`"
        )
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(path.read_text(encoding="utf-8"))


def has_spec(report: str) -> bool:
    return _spec_path(report) is not None


def _row_count(band: dict, rows: int | None) -> int:
    return band["reference_rows"] if rows is None else rows


def _row_top(band: dict, row: int) -> float:
    """The row's top edge: the reference's own, or extrapolated by its pitch.

    Reference row heights vary by hundredths of a point, so the recovered edges
    are used verbatim where they exist; only rows beyond what the reference had
    (longer data) are extrapolated from the pitch.
    """
    tops = band.get("row_tops") or []
    if row < len(tops):
        return float(tops[row])
    if tops:
        return float(tops[-1]) + (row - len(tops) + 1) * band["pitch"]
    return band["y0"] + row * band["pitch"]


def _row_fills(band: dict, row: int) -> list:
    per_row = band.get("per_row_fills") or []
    if row < len(per_row):
        return per_row[row]
    return band.get("row_fills") or []


def _data_index(band: dict, row: int) -> int | None:
    """Which data row a band row shows, honouring the recovered row alignment."""
    mapping = band.get("row_data_index")
    if mapping is None:
        return band.get("group_offset", 0) + row
    if row < len(mapping):
        return mapping[row]
    last = next((value for value in reversed(mapping) if value is not None), None)
    if last is None:
        return None
    return last + 1 + (row - len(mapping))


def _row_cells(band: dict, row: int) -> list:
    per_row = band.get("per_row_cells") or []
    if row < len(per_row):
        return per_row[row]
    return band["cells"]


def _same_value(text: str, sample: str) -> bool:
    """Is this the value the reference printed here, ignoring whitespace runs?"""
    return " ".join(str(text).split()) == " ".join(str(sample).split())


def _value_at(supplied, column: int) -> str:
    if supplied is None:
        return ""
    if isinstance(supplied, dict):
        return str(supplied.get(column, "") or "")
    return str(supplied[column] or "") if column < len(supplied) else ""


def _derived_fills(band: dict, row: int, rows: list | None) -> list[tuple[float, float, str]]:
    """Cell washes that must be COMPUTED from the value, not replayed.

    The competency band is the one colour in these reports that is a function of
    the data (the GPA band behind ``Grade C (Good)``), so for a row the reference
    never had — longer data — it is computed from the value via
    :mod:`sars.competency`. For the rows the reference did have, the recovered
    wash wins: several documents tint a band differently from the standard
    mapping (see ``sars.competency.KNOWN_VARIANTS``) and the reference is the
    authority on its own page.
    """
    if not rows or row >= len(rows):
        return []
    if row < len(band.get("per_row_fills") or []):
        return []
    from .competency import background_for

    supplied = rows[row]
    out: list[tuple[float, float, str]] = []
    for cell in _row_cells(band, row):
        path = str((band.get("bindings") or {}).get(str(cell["col"]), ""))
        if "competency" not in path.casefold() and "compentency" not in path.casefold():
            continue
        label = _value_at(supplied, cell["col"]).strip()
        if not label:
            continue
        colour = background_for(label=label, gpa=None)
        if colour:
            out.append((cell["x"], cell["w"], colour))
    return out


def _recolour(derived: list[tuple[float, float, str]], x: float, w: float, color: str) -> str:
    """Use a derived wash for a fill that covers a derived cell's box."""
    for cell_x, cell_w, colour in derived:
        if abs(x - cell_x) <= 1.0 and abs(w - cell_w) <= 1.5:
            return colour
    return color


def render_html(
    report: str,
    values: ValueProvider,
    *,
    rows_per_band: dict[tuple[int, int], int] | None = None,
    engine: str | None = None,
    title: str | None = None,
) -> str:
    """Render *report* from its spec, taking each band's values from *values*.

    ``rows_per_band`` may override how many rows a ``(page, band)`` carries when
    the data is longer or shorter than the reference; by default every band
    carries exactly the number of rows the reference had.
    """
    spec = load(report)
    engine = engine or printing.engine_for(report)
    rows_per_band = rows_per_band or {}
    pages: list[Canvas] = []
    book = StyleBook()

    for page_index, page in enumerate(spec["pages"]):
        canvas = Canvas(report, page["width"], page["height"], engine=engine, book=book)
        bands = page["bands"]

        # The values first: a band's fills may depend on them (the competency
        # band's colour is DERIVED from the competency label / GPA, never stored).
        supplied_rows: dict[int, list] = {}
        for band_index, band in enumerate(bands):
            count = _row_count(band, rows_per_band.get((page_index, band_index)))
            mapping = band.get("row_data_index")
            rows: list = []
            for row in range(count):
                supplied = values(page_index, band_index, band["kind"], row)
                if supplied is None:
                    # A ``None`` from a row the reference recovered as an
                    # unexplained/chrome row (a repeated column header drawn
                    # inside the band) is a gap to SKIP, not the end of the band:
                    # the rows after it are real data. Preserve the row position
                    # with an empty placeholder so fills and baselines still land
                    # by absolute row index. A ``None`` past the reference rows
                    # (data ran out) genuinely ends the band.
                    if (
                        mapping is not None
                        and row < len(mapping)
                        and mapping[row] is None
                    ):
                        rows.append(None)
                        continue
                    break
                rows.append(supplied)
            supplied_rows[band_index] = rows

        # 1. the paint sequence, rectangle by rectangle, in the reference's order
        for entry in page["sequence"]:
            if entry["t"] == "s":
                x, y, w, h, color = entry["r"]
                canvas.fill(Box(x, y, w, h), color)
                continue
            band_index = entry["band"]
            band = bands[band_index]
            count = _row_count(band, rows_per_band.get((page_index, band_index)))
            row = entry["row"]
            if row >= count:
                continue
            x, dy, w, h, color = entry["d"]
            canvas.fill(Box(x, _row_top(band, row) + dy, w, h), color)

        # Rows the reference never had (longer data): paint the template row,
        # with the washes that are a function of the value derived.
        for band_index, band in enumerate(bands):
            count = _row_count(band, rows_per_band.get((page_index, band_index)))
            for row in range(len(band.get("row_tops") or []), count):
                top = _row_top(band, row)
                derived = _derived_fills(band, row, supplied_rows.get(band_index))
                for x, dy, w, h, color in _row_fills(band, row):
                    canvas.fill(Box(x, top + dy, w, h), _recolour(derived, x, w, color))

        # 2. the values, band by band
        for band_index, band in enumerate(bands):
            for row, supplied in enumerate(supplied_rows.get(band_index, [])):
                if supplied is None:
                    continue
                top = _row_top(band, row)
                for cell in _row_cells(band, row):
                    if "role" not in cell:
                        continue
                    column = cell["col"]
                    if isinstance(supplied, dict):
                        text = supplied.get(column, "")
                    else:
                        text = supplied[column] if column < len(supplied) else ""
                    if text is None:
                        continue
                    text = str(text).strip()
                    if not text:
                        continue
                    height = band["pitch"]
                    bottoms = band.get("row_bottoms") or []
                    if row < len(bottoms):
                        height = float(bottoms[row]) - top
                    # When the value is the string the reference printed in this
                    # cell, start it exactly where the reference started it — and
                    # print it with the reference's own spacing. Comparing
                    # whitespace-insensitively matters: a value the extractor
                    # rebuilt with single spaces ("ENG 65 B") is the same value
                    # the reference padded differently, and falling back to
                    # computed alignment for it cost ~0.4pt on every such cell.
                    sample = str(cell.get("sample") or "").strip()
                    pieces = cell.get("pieces") or []
                    glyphs = cell.get("glyphs") or []
                    if sample and _same_value(text, sample) and glyphs:
                        # The value the reference printed here: replay its glyphs
                        # at the exact x the reference drew each one, so a long
                        # cell does not drift by the accumulated difference
                        # between the font's advances and the reference's own
                        # device grid. Pixel-identical to the reference, and still
                        # chosen by the data.
                        baseline = top + cell["dy"]
                        for glyph_char, glyph_x in glyphs:
                            canvas.text(
                                float(glyph_x),
                                baseline,
                                str(glyph_char),
                                role=cell["role"],
                                size=cell["size"],
                                color=cell.get("color", "#000000"),
                            )
                        continue
                    if sample and _same_value(text, sample) and pieces:
                        # Older specs without per-glyph positions: draw each of
                        # the reference's own runs at its own x.
                        for piece_text, piece_x in pieces:
                            canvas.text(
                                float(piece_x),
                                top + cell["dy"],
                                str(piece_text),
                                role=cell["role"],
                                size=cell["size"],
                                color=cell.get("color", "#000000"),
                            )
                        continue
                    canvas.cell_text(
                        Box(cell["x"], top, cell["w"], height),
                        text,
                        role=cell["role"],
                        size=cell["size"],
                        baseline=top + cell["dy"],
                        align=cell.get("align", "center"),
                        pad=cell.get("pad", 0.0),
                        color=cell.get("color", "#000000"),
                        xfix=cell.get("xfix", 0.0),
                    )

        # 3. the chrome, glyph by glyph at the reference's own origins
        for x, y, char, role, size, color, rotation in page["chrome"]:
            canvas.text(x, y, char, role=role, size=size, color=color, rotation=rotation)

        pages.append(canvas)

    return document(
        title=title or report,
        width=spec["page_width"],
        height=spec["page_height"],
        pages=pages,
    )


def section_provider(report: str, sections: list[Any]) -> ValueProvider:
    """Feed a spec's bands from header-keyed data sections, in document order.

    The reports whose data is a list of sections (each with ``column_headers``,
    ``rows`` and ``totals``) map onto their spec mechanically: a band carries the
    section whose column count matches, consuming rows in order — so a table that
    the reference continued across pages simply continues consuming, and a
    ``TOTAL`` band takes its section's totals. Values are addressed by column
    index, which is the order the section's ``column_headers`` are in, because
    both were recovered from the same column lattice.
    """
    spec = load(report)
    plan: dict[tuple[int, int], tuple[int, int]] = {}  # (page, band) -> (section, row offset)
    consumed = [0] * len(sections)
    current: int | None = None

    for page_index, page in enumerate(spec["pages"]):
        for band_index, band in enumerate(page["bands"]):
            columns = band.get("columns") or len(band["cells"])
            if band["kind"] == "total":
                if current is not None:
                    plan[(page_index, band_index)] = (current, -1)
                continue
            candidate = None
            if (
                current is not None
                and len(sections[current].column_headers) == columns
                and consumed[current] < len(sections[current].rows)
            ):
                candidate = current
            if candidate is None:
                for index, section in enumerate(sections):
                    if (
                        len(section.column_headers) == columns
                        and consumed[index] < len(section.rows)
                    ):
                        candidate = index
                        break
            if candidate is None:
                continue
            current = candidate
            plan[(page_index, band_index)] = (candidate, consumed[candidate])
            consumed[candidate] += band["reference_rows"]

    def provider(page_index: int, band_index: int, kind: str, row_index: int):
        entry = plan.get((page_index, band_index))
        if entry is None:
            return None
        section_index, offset = entry
        section = sections[section_index]
        headers = list(section.column_headers)
        if offset < 0 or kind == "total":
            totals = list(section.totals.values())
            if row_index >= len(totals):
                return None
            row = totals[row_index]
            if isinstance(row, dict):
                return [row.get(header, "") for header in headers]
            return list(row)
        position = offset + row_index
        if position >= len(section.rows):
            return None
        values = section.rows[position].values
        return [values.get(header, "") for header in headers]

    return provider


def binding_provider(report: str, data: Any) -> ValueProvider:
    """Feed a spec's bands using the bindings recovered into the spec.

    Works for every report family, because the binding — which data field each
    column carries — was recovered from the reference itself at spec-build time
    (see :mod:`sars.binding`). A band names the row group it consumes, the offset
    it starts at, and the field path per column; this walks the data with that
    map. Bands whose columns could not be bound fall back to nothing, so a value
    is never invented.
    """
    from . import binding

    spec = load(report)
    groups = binding.row_groups(data)
    by_name = {group["name"]: group["rows"] for group in groups}

    def rows_of(name: str, index: int | None) -> list | None:
        rows = by_name.get(name)
        if rows is not None:
            return rows
        if index is not None and index < len(groups):
            return groups[index]["rows"]
        return None

    def provider(page_index: int, band_index: int, kind: str, row_index: int):
        band = spec["pages"][page_index]["bands"][band_index]
        bindings = band.get("bindings") or {}
        extra = band.get("column_bindings") or {}
        if not bindings and not extra:
            return None

        values: dict[int, str] = {}
        rows = rows_of(band.get("group", ""), band.get("group_index"))
        if rows is not None:
            position = _data_index(band, row_index)
            if position is None:
                # A row the data does not explain: a repeated column heading,
                # drawn as chrome. Nothing is filled into it.
                return None
            if position < len(rows):
                flat = rows[position]
                values.update({int(col): flat.get(path, "") for col, path in bindings.items()})
            elif not extra:
                return None

        # Columns bound to a different part of the data than the band's primary
        # group - a TOTAL row whose label and summary figures come from the
        # summary block while its counts come from the ranked rows.
        for col, entry in extra.items():
            other = rows_of(entry.get("group", ""), entry.get("group_index"))
            if other is None:
                continue
            position = entry.get("offset", 0) + row_index
            if position >= len(other):
                continue
            values[int(col)] = other[position].get(entry.get("path", ""), "")

        # Rows whose values all came back empty carry no data (an unexplained
        # row that the spec kept as chrome); returning None stops the band.
        if not any(str(value).strip() for value in values.values()):
            return {} if row_index + 1 < band["reference_rows"] else None

        return values or None

    return provider


def band_summary(report: str) -> list[dict[str, Any]]:
    """Diagnostic: the bands a report's spec defines, per page."""
    spec = load(report)
    return [
        {
            "page": index + 1,
            "bands": [
                {
                    "band": position,
                    "kind": band["kind"],
                    "rows": band["reference_rows"],
                    "columns": len(band["cells"]),
                    "slots": sum(1 for cell in band["cells"] if "role" in cell),
                }
                for position, band in enumerate(page["bands"])
            ],
        }
        for index, page in enumerate(spec["pages"])
    ]
