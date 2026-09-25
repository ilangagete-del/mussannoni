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

#: ``values(page, band, kind, row) -> the row's values, or None to end the band``
ValueProvider = Callable[[int, int, str, int], "Sequence[str] | dict[int, str] | None"]

#: Safety stop on continuation pages generated for one spec page, so a provider
#: that never signals "no more rows" cannot spin forever. Far above any real
#: report: the largest bundled example is 30 pages in total.
MAX_CONTINUATION_PAGES = 500


class LayoutSpecMissing(FileNotFoundError):
    """Raised when a report has no recovered layout spec yet."""


def _layout_dirs() -> list[Path]:
    """Every education stage's layouts directory, in search order.

    Looking a layout up across stages is what makes a future primary layout
    findable by registering the stage, with no change here. Imported lazily
    because a stage package imports this module.
    """
    from . import stages

    return stages.layout_dirs()


def _spec_path(report: str) -> Path | None:
    """The report's spec file: gzipped by default, plain JSON also accepted."""
    for directory in _layout_dirs():
        for candidate in (directory / f"{report}.json.gz", directory / f"{report}.json"):
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


def available() -> list[str]:
    """Every layout that ships with the package, by spec key (document name)."""
    keys = set()
    for directory in _layout_dirs():
        for path in directory.glob("*.json*"):
            keys.add(path.name.split(".json")[0])
    return sorted(keys)


def catalogue() -> list[dict[str, str]]:
    """Every bundled layout with the descriptor that can select it.

    This is what makes a layout addressable by *what kind of report it is*
    (``report_type`` / ``level`` / ``variant``) instead of only by the exact name
    of the document it was recovered from.
    """
    from . import stages

    out: list[dict[str, str]] = []
    for stage in stages.implemented():
        if not stage.layouts.is_dir():
            continue
        keys = {path.name.split(".json")[0] for path in stage.layouts.glob("*.json*")}
        for key in sorted(keys):
            spec = stage.spec_for(key)
            out.append(
                {
                    "layout": key,
                    "stage": stage.name,
                    "report_type": getattr(spec, "report_type", ""),
                    "level": getattr(spec, "level", ""),
                    "variant": getattr(spec, "variant", ""),
                }
            )
    return out


def resolve(
    name: str | None = None,
    *,
    report_type: str | None = None,
    level: str | None = None,
    variant: str | None = None,
    stage: str | None = None,
) -> str:
    """The layout to render with, for a document name and/or a descriptor.

    A recovered layout is keyed by the name of the document it came from, because
    it *is* that document's geometry. That is exactly right for reproducing a
    supplied report, and useless for rendering data of your own, which has no
    such name. So resolution has two steps:

    1. ``name`` naming a bundled layout wins outright — reproduce that document.
    2. Otherwise the best match for ``report_type`` (then ``level``, then
       ``variant``) is used, so your own data can be printed in the shape of a
       report of that kind.

    Raises :class:`LayoutSpecMissing` listing what *is* available, rather than
    rendering something that silently is not the report that was asked for.
    """
    if name and has_spec(name):
        return name

    entries = catalogue()
    if stage:
        entries = [e for e in entries if e["stage"] == stage]
    if report_type:
        entries = [e for e in entries if e["report_type"] == report_type]
    if level:
        narrowed = [e for e in entries if e["level"] == level]
        entries = narrowed or entries
    if variant:
        narrowed = [e for e in entries if e["variant"] == variant]
        entries = narrowed or entries

    if entries:
        return sorted(e["layout"] for e in entries)[0]

    known = sorted({f"{e['report_type']}/{e['level']}/{e['variant']}" for e in catalogue()})
    raise LayoutSpecMissing(
        f"no bundled layout for name={name!r} report_type={report_type!r} "
        f"level={level!r} variant={variant!r}. Available report_type/level/variant: "
        + ", ".join(known)
    )


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


def _band_last_bottom(band: dict) -> float:
    """The y of the bottom edge of the band's last REFERENCE row."""
    bottoms = band.get("row_bottoms") or []
    if bottoms:
        return float(bottoms[-1])
    tops = band.get("row_tops") or []
    if tops:
        return float(tops[-1]) + float(band["pitch"])
    return float(band["y0"]) + band["reference_rows"] * float(band["pitch"])


def _row_capacity(page: dict, bands: list, band_index: int) -> int:
    """How many rows this band could carry before it would hit something.

    A band may only grow into space that is genuinely empty on the reference
    page. Everything the reference draws *below* the band's last row — a TOTAL
    band, a footer rule, a signature line — is a barrier, because growing past it
    would overprint it. The page bottom is the final barrier. This is what keeps
    "more data" from silently running off the page (``.pg`` clips, so nothing
    would warn) and what keeps it from ever needing another page.
    """
    band = bands[band_index]
    pitch = float(band["pitch"])
    if pitch <= 0:
        return band["reference_rows"]
    last_bottom = _band_last_bottom(band)
    barrier = float(page["height"])

    for other_index, other in enumerate(bands):
        if other_index == band_index:
            continue
        top = float(other.get("y0", 0.0))
        if (other.get("row_tops") or []):
            top = float(other["row_tops"][0])
        if top >= last_bottom - 0.5:
            barrier = min(barrier, top)

    for entry in page.get("sequence", ()):
        if entry.get("t") != "s":
            continue
        y = float(entry["r"][1])
        if y >= last_bottom - 0.5:
            barrier = min(barrier, y)

    for chrome in page.get("chrome", ()):
        # (x, y, char, role, size, color, rotation) - y is a baseline, so the
        # glyph's top is roughly one em above it.
        top = float(chrome[1]) - float(chrome[4])
        if top >= last_bottom - 0.5:
            barrier = min(barrier, top)

    extra = int((barrier - last_bottom) // pitch)
    return band["reference_rows"] + max(0, extra)


def _terminal_bands(spec: dict) -> set[tuple[int, int]]:
    """The last band, in document order, consuming each bound row group.

    Only these may grow. A table that the reference continued across pages has a
    band per page, and every band after the first takes its offset into the data
    from the row counts of the bands before it; growing an EARLIER band would
    make the next one repeat rows it already drew. The band where the reference's
    data ran out is the one place extra rows belong.
    """
    last: dict[str, tuple[int, int]] = {}
    for page_index, page in enumerate(spec["pages"]):
        for band_index, band in enumerate(page["bands"]):
            group = band.get("group")
            if not group or band["kind"] == "total":
                continue
            if not (band.get("bindings") or band.get("column_bindings")):
                continue
            last[str(group)] = (page_index, band_index)
    return set(last.values())


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
    """Is this the value the reference printed here, ignoring whitespace?

    Whitespace is compared as *insignificant*, not merely collapsed. The
    extractor rebuilds a value from the reference's text runs, and where the
    reference drew two runs in one cell — ``GPA`` and ``2.2969`` at their own x
    positions — the rebuilt value carries a separator the reference's own sample
    string does not (``"GPA 2.2969"`` vs ``"GPA2.2969"``). Those are the same
    value, printed by the same cell, so matching them lets the cell replay the
    reference's own glyph origins instead of re-deriving an alignment: exactly
    what the reference drew, pixel for pixel.
    """
    return "".join(str(text).split()) == "".join(str(sample).split())


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
    from . import stages

    background_for = stages.get().background_for

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
    grow: bool = False,
) -> str:
    """Render *report* from its spec, taking each band's values from *values*.

    ``rows_per_band`` may override how many rows a ``(page, band)`` carries when
    the data is longer or shorter than the reference; by default every band
    carries exactly the number of rows the reference had.

    ``grow`` chooses between the two jobs this renderer does:

    ``grow=False`` (default) — **reproduce the reference.** The document gets
    exactly the pages, and each band exactly the rows, that the reference had.
    This is what the fidelity gate measures, and it must stay that way: a
    recovered spec is not a promise that the data extracted from a document has
    the same number of rows the document printed. ``MWANZA CC SCHOOLS RANK
    SUBJECTWISE`` is the proof — its extracted ``section0`` carries 65 rows while
    the reference page prints 54 — so growing by "the provider still has rows"
    would silently turn a faithful 24-page reproduction into 30 pages.

    ``grow=True`` — **render all of the supplied data.** A band that fills up
    continues onto further instances of its own page, so no supplied row is ever
    dropped. This is the mode for feeding the templates data of your own, where
    the row count is whatever your data says and there is no reference to match.
    """
    spec = load(report)
    engine = engine or printing.engine_for(report)
    rows_per_band = rows_per_band or {}
    pages: list[Canvas] = []
    book = StyleBook()
    growable = _terminal_bands(spec)

    def render_page(
        page_index: int, page: dict, offsets: dict[int, int], final: bool = True
    ) -> tuple[Canvas, dict[int, int]]:
        """Draw one instance of a spec page.

        ``offsets`` shifts a band's window into the data, which is how a
        continuation page carries on from where the previous instance stopped.
        Returns the canvas and, per band, how many rows this instance consumed
        when there is still data left after it.

        ``final`` is False on every instance but the last. A ``total`` band is
        drawn only on the final one: a TOTAL is a total *of the table*, so
        repeating it under each continuation page would assert something untrue
        seven times over and once correctly.
        """
        canvas = Canvas(report, page["width"], page["height"], engine=engine, book=book)
        bands = page["bands"]
        leftover: dict[int, int] = {}

        # The values first: a band's fills may depend on them (the competency
        # band's colour is DERIVED from the competency label / GPA, never stored).
        supplied_rows: dict[int, list] = {}
        painted: dict[int, int] = {}
        for band_index, band in enumerate(bands):
            if not final and band["kind"] == "total":
                # Held back for the last instance (see ``final`` above). Zero
                # painted rows makes the paint sequence skip the band's own
                # rules and washes too, so nothing of it is drawn here.
                supplied_rows[band_index] = []
                painted[band_index] = 0
                continue
            count = _row_count(band, rows_per_band.get((page_index, band_index)))
            # Data longer than the reference extends the band where the
            # reference's own data ran out, as far as the page's empty space
            # allows. The provider decides when to stop, so reference-length data
            # stops at exactly the reference row count and nothing here changes.
            limit = count
            if (
                grow
                and (page_index, band_index) in growable
                and (page_index, band_index) not in rows_per_band
            ):
                limit = max(count, _row_capacity(page, bands, band_index))
            offset = offsets.get(band_index, 0)
            mapping = band.get("row_data_index")
            rows: list = []
            for row in range(limit):
                supplied = values(page_index, band_index, band["kind"], row + offset)
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
            # What the band PAINTS: never fewer rows than the reference (shorter
            # data still shows the reference's empty ruled rows) and never fewer
            # than the data actually filled.
            painted[band_index] = max(
                _row_count(band, rows_per_band.get((page_index, band_index))), len(rows)
            )
            # Data still waiting after this instance filled the band: the page is
            # full, so the remainder belongs on a continuation page. Only asked of
            # a growable band, and only when the band actually filled up — so a
            # reference-length document never reaches this branch.
            if (
                grow
                and (page_index, band_index) in growable
                and limit > 0
                and len(rows) == limit
                and values(page_index, band_index, band["kind"], limit + offset) is not None
            ):
                leftover[band_index] = limit

        # 1. the paint sequence, rectangle by rectangle, in the reference's order
        for entry in page["sequence"]:
            if entry["t"] == "s":
                x, y, w, h, color = entry["r"]
                canvas.fill(Box(x, y, w, h), color)
                continue
            band_index = entry["band"]
            band = bands[band_index]
            count = painted[band_index]
            row = entry["row"]
            if row >= count:
                continue
            x, dy, w, h, color = entry["d"]
            canvas.fill(Box(x, _row_top(band, row) + dy, w, h), color)

        # Rows the reference never had (longer data): paint the template row,
        # with the washes that are a function of the value derived.
        for band_index, band in enumerate(bands):
            count = painted[band_index]
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
                        sample=sample,
                    )

        # 3. the chrome, glyph by glyph at the reference's own origins
        for x, y, char, role, size, color, rotation in page["chrome"]:
            canvas.text(x, y, char, role=role, size=size, color=color, rotation=rotation)

        return canvas, leftover

    for page_index, page in enumerate(spec["pages"]):
        # Data longer than the reference: continue the full band onto further
        # instances of this same page, so no supplied row is ever dropped. A
        # reference-length document produces no leftover and therefore exactly
        # the reference's own page count — the page count is data-driven only
        # upwards, never for the documents the fidelity gate measures.
        #
        # Rendered as a dry run first, purely to learn how many instances the
        # data needs, because a ``total`` band has to know whether it is on the
        # last one. The dry canvases are discarded; only the offsets matter.
        plan: list[dict[int, int]] = [{}]
        offsets: dict[int, int] = {}
        guard = 0
        while guard < MAX_CONTINUATION_PAGES:
            _, leftover = render_page(page_index, page, offsets, final=False)
            if not leftover:
                break
            guard += 1
            offsets = {
                band_index: offsets.get(band_index, 0) + consumed
                for band_index, consumed in leftover.items()
            }
            plan.append(dict(offsets))

        for position, carried in enumerate(plan):
            canvas, _ = render_page(
                page_index, page, carried, final=position == len(plan) - 1
            )
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


def data_contract(report: str) -> list[dict[str, Any]]:
    """The field paths a layout will actually read, per band.

    A layout's bindings were recovered from the reference document, so they name
    data by the reference's own field paths — and for the header-driven reports
    that path *is* the column's header label, with ``/`` between header levels
    (``'DIVISION PERFORMANCE / I-III / TOTAL'``). A caller supplying their own
    data needs those exact keys, so this returns them instead of leaving them to
    be guessed:

    >>> from sars import layout_spec
    >>> contract = layout_spec.data_contract("MWANZA CC Wards Rank")
    >>> contract[0]["fields"][1]
    'NO. OF / WARDS IN / COUNCIL'

    Use it with :func:`sars.binding.row_groups` to see the paths a schema
    instance actually offers, which is how a mismatch is diagnosed.
    """
    spec = load(report)
    out: list[dict[str, Any]] = []
    for page_index, page in enumerate(spec["pages"]):
        for band_index, band in enumerate(page["bands"]):
            bindings = band.get("bindings") or {}
            if not bindings:
                continue
            out.append(
                {
                    "page": page_index,
                    "band": band_index,
                    "kind": band["kind"],
                    "group": band.get("group", ""),
                    "reference_rows": band["reference_rows"],
                    "fields": {int(col): path for col, path in bindings.items()},
                }
            )
    return out


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
