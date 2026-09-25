"""Generic tabular template - SELF-CONTAINED and FAITHFUL.

Serves every report captured header-driven into a
:class:`~sars.schema.GenericTabularReport`: the single-subject school ranks
(EDK / English / council subjectwise), the wards pivot, district performance and
mock mobility. It reconstructs the grouped column-header band from the
``column_headers`` label paths, emits one data row per
:class:`~sars.schema.TabularRow` in header order, then any ``totals`` rows.

This template OWNS its own structure and its own complete inline styling: its
``@page`` orientation, its table rules, its fonts and row heights (authored at
the reference's true recovered point sizes and scaled to A4), and the
deterministic competency-band wash. It shares no cross-report CSS constant; its
``<style>`` is inlined into its own ``<head>``.

DATA IS DATA: nothing here reads presentation from the data; the only
data-derived colour is the competency band (:mod:`sars.competency`).
"""

from __future__ import annotations

from ...schema import GenericTabularReport, TabularSection
from .base import banner_html, competency_background, orientation_for
from .styling import Sheet, document, esc, fit_scale

_COMPETENCY_KEYS = ("COMPETENCY LEVEL", "COMPENTENCY LEVEL", "COMPETENCY")

#: A generic report wider than this many columns prints denser (smaller font) so
#: its narrow fixed columns do not overlap and merge two adjacent values into one
#: token. This is a structure-derived layout decision (column count), not stored
#: presentation.
_WIDE_COLUMN_THRESHOLD = 20

# True recovered point sizes (pre-scale). Portrait single-subject / pivot reports
# print ~6-7pt; the wide landscape district report ~5.2pt. Multiplied by the
# fit-to-A4 scale so they print at the reference size.
_PT_NORMAL = 6.7
_PT_DENSE = 5.2
_PT_BANNER = 7.5


def _style(orientation: str, dense: bool) -> Sheet:
    """Build THIS report's own complete inline stylesheet."""
    s = fit_scale(orientation)
    body_pt = _PT_DENSE if dense else _PT_NORMAL
    row_pt = body_pt * 1.35
    px = lambda pt: f"{pt * s:.2f}pt"  # noqa: E731
    sheet = Sheet()
    sheet.extend(f"""
body{{margin:0;color:#000;font-family:Arial, Helvetica, sans-serif}}
.report{{padding:{px(4)} {px(6)}}}
.banner{{text-align:center;font-weight:700;font-size:{px(_PT_BANNER)};
        line-height:1.4}}
.banner .title{{margin-top:{px(6)};font-size:{px(_PT_BANNER)}}}
table.gt{{border-collapse:collapse;table-layout:fixed;width:100%;
        border-spacing:0;margin-top:{px(6)}}}
table.gt th,table.gt td{{border:0.4pt solid #000;padding:0 0.8pt;
        text-align:center;vertical-align:middle;overflow:visible;
        font-size:{px(body_pt)};line-height:{px(row_pt)};
        white-space:normal;overflow-wrap:normal;word-break:keep-all}}
table.gt th{{font-weight:700}}
table.gt td.text,table.gt th.text{{text-align:left}}
table.gt th.nw,table.gt td.nw{{white-space:nowrap}}
table.gt tr.total th,table.gt tr.total td{{font-weight:700}}
""")
    return sheet


def _header_matrix(paths: list[str]) -> list[list[tuple[str, int]]]:
    """Turn per-column label paths into header rows of ``(text, colspan)``."""
    if not paths:
        return []
    split = [p.split(" / ") if p else [""] for p in paths]
    depth = max(len(s) for s in split)
    padded = [s + [s[-1]] * (depth - len(s)) for s in split]

    matrix: list[list[tuple[str, int]]] = []
    for r in range(depth):
        row: list[tuple[str, int]] = []
        c = 0
        n = len(padded)
        while c < n:
            prefix = padded[c][: r + 1]
            span = 1
            while c + span < n and padded[c + span][: r + 1] == prefix:
                span += 1
            text = padded[c][r]
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
        cells = "".join(
            f'<th colspan="{span}">{esc(text)}</th>' if span > 1 else f"<th>{esc(text)}</th>"
            for text, span in row
        )
        out.append(f"<tr>{cells}</tr>")
    return "<thead>" + "".join(out) + "</thead>"


def _is_text_col(leaf: str) -> bool:
    up = leaf.upper()
    return any(k in up for k in ("NAME", "WARD", "COUNCIL", "SCHOOL", "SUBJECT"))


def _td(value: str, *, text: bool = False, style: str = "") -> str:
    cls = ' class="text"' if text else ""
    st = f' style="{style}"' if style else ""
    return f"<td{cls}{st}>{esc(value)}</td>"


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
                bg = competency_background(value, gpa)
                cells.append(_td(value, text=True, style=f"background-color:{bg}" if bg else ""))
            else:
                cells.append(_td(value, text=_is_text_col(leaf)))
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
        title + '<table class="gt">'
        f"{_thead(paths)}"
        "<tbody>" + "".join(body_rows) + "</tbody>"
        "</table>"
    )


def _sections_of(report: GenericTabularReport) -> list[TabularSection]:
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
    """Render a :class:`~sars.schema.GenericTabularReport` to a standalone doc."""
    sections = _sections_of(report)
    widest = max((len(sec.column_headers) for sec in sections), default=0)
    orientation = orientation_for(report.meta)
    sheet = _style(orientation, dense=widest > _WIDE_COLUMN_THRESHOLD)
    body = '<section class="report">'
    body += banner_html(report.meta)
    body += "".join(_section_table(sec) for sec in sections)
    body += "</section>"
    return document(
        title=report.meta.title or report.meta.name,
        orientation=orientation,
        sheet=sheet,
        body=body,
    )
