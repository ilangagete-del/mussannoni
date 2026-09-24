"""Generic tabular template.

Serves every report captured header-driven into a
:class:`~sars.schema.GenericTabularReport`: the single-subject school ranks
(EDK / English / council subjectwise), the wards pivot, district performance
and mock mobility. It reconstructs the grouped column-header band from the
``column_headers`` label paths (``"DIVISION PERFORMANCE / I / F"``), emits one
data row per :class:`~sars.schema.TabularRow` in header order, then any
``totals`` rows.

Expected data shape: a :class:`~sars.schema.GenericTabularReport` with

* ``meta``            - :class:`~sars.schema.ReportMeta`;
* ``column_headers``  - flattened ``"A / B / C"`` label paths, one per column;
* ``rows``            - ``TabularRow`` objects whose ``values`` map a column
  header path (or a bare leaf label) to its printed value;
* ``totals``          - ``{row_label: [cell, ...]}`` for any summary rows.
"""

from __future__ import annotations

from ..schema import GenericTabularReport, TabularSection
from .base import banner_html, competency_cell, document_html, esc, header_cell

_COMPETENCY_KEYS = ("COMPETENCY LEVEL", "COMPENTENCY LEVEL", "COMPETENCY")


def _header_matrix(paths: list[str]) -> list[list[tuple[str, int]]]:
    """Turn per-column label paths into header rows of ``(text, colspan)``.

    Each path is split on ``" / "``; segment ``r`` of column ``c`` sits in
    header row ``r``. Consecutive columns sharing the same segment prefix are
    merged into one spanning cell. Missing trailing segments repeat the last
    present one downward so a rowspan-style label still lands in every row.
    """
    if not paths:
        return []
    split = [p.split(" / ") if p else [""] for p in paths]
    depth = max(len(s) for s in split)
    # Pad each column's path to full depth by repeating its final segment, so a
    # column with fewer levels (an identity column) fills the band vertically.
    padded = [s + [s[-1]] * (depth - len(s)) for s in split]

    matrix: list[list[tuple[str, int]]] = []
    for r in range(depth):
        row: list[tuple[str, int]] = []
        c = 0
        n = len(padded)
        while c < n:
            # Merge while the label path *up to this row* is identical, so a
            # group heading spans exactly its own sub-columns and no further.
            prefix = padded[c][: r + 1]
            span = 1
            while c + span < n and padded[c + span][: r + 1] == prefix:
                span += 1
            text = padded[c][r]
            # Only show a segment once vertically: blank it if the row above
            # already carried the same text for this same column group.
            if r > 0 and padded[c][r] == padded[c][r - 1]:
                text = ""
            row.append((text, span))
            c += span
        matrix.append(row)
    return matrix


def _thead(paths: list[str]) -> str:
    rows = _header_matrix(paths)
    out: list[str] = []
    for row in rows:
        cells = "".join(header_cell(text, colspan=span) for text, span in row)
        out.append(f"<tr>{cells}</tr>")
    return "<thead>" + "".join(out) + "</thead>"


def _is_text_col(leaf: str) -> bool:
    up = leaf.upper()
    return any(k in up for k in ("NAME", "WARD", "COUNCIL", "SCHOOL", "SUBJECT"))


def _section_table(section: TabularSection) -> str:
    """One table block: grouped header band, data rows, then any totals rows."""
    paths = section.column_headers
    leaves = [p.split(" / ")[-1] if p else "" for p in paths]
    comp_idx = next(
        (i for i, leaf in enumerate(leaves) if leaf.upper() in _COMPETENCY_KEYS),
        None,
    )
    gpa_idx = next((i for i, leaf in enumerate(leaves) if leaf.upper() == "GPA"), None)

    body_rows: list[str] = []
    for trow in section.rows:
        vals = trow.values
        cells: list[str] = []
        for i, path in enumerate(paths):
            leaf = leaves[i]
            value = vals.get(path, vals.get(leaf, ""))
            if i == comp_idx:
                gpa = vals.get(paths[gpa_idx], "") if gpa_idx is not None else ""
                cells.append(competency_cell(value, gpa))
            elif _is_text_col(leaf):
                cells.append(f'<td class="text">{esc(value)}</td>')
            else:
                cells.append(f"<td>{esc(value)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    for _label, values in section.totals.items():
        cells = "".join(f"<td>{esc(v)}</td>" for v in values)
        body_rows.append(f'<tr class="total">{cells}</tr>')

    title = (
        f'<div class="banner"><div class="title">{esc(section.title)}</div></div>'
        if section.title
        else ""
    )
    return (
        title + '<table class="tmpl">'
        f"{_thead(paths)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )


def _sections_of(report: GenericTabularReport) -> list[TabularSection]:
    """Every table block of the report.

    Falls back to the mirrored top-level fields so a report constructed by hand
    (or deserialised from an older JSON payload) without ``sections`` still
    renders.
    """
    if report.sections:
        return list(report.sections)
    return [
        TabularSection(
            column_headers=report.column_headers,
            rows=report.rows,
            totals=report.totals,
        )
    ]


def render_generic(report: GenericTabularReport) -> str:
    """Render a :class:`~sars.schema.GenericTabularReport` to a full HTML doc.

    Every table block in ``sections`` is printed in order; a report whose blocks
    have different column counts (district performance) therefore keeps them all.
    """
    body = banner_html(report.meta)
    body += "".join(_section_table(sec) for sec in _sections_of(report))
    return document_html(report.meta, body)
