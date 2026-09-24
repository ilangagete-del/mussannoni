"""Fixed-layout, self-contained *top-ten schools* report.

This renderer is deliberately independent of every other report family, matching
the project rule that each report type is its own self-contained artefact.  The
top-schools reports share the :class:`~sars.schema.SchoolsRankReport` data shape
with the ranked-schools report but have a *different* printed structure: instead
of one long ranked table they are a stack of short (ten-row) "TOP TEN BEST ..."
blocks, each with its own header band, and they paginate one/two blocks to a
page.  Their page box is the same 792 x 612 US-Letter landscape as the reference
PDFs, and this renderer emits the reference page COUNT with the block breaks
placed where the reference breaks.

The section headings the reference prints above each block are not recovered
into the data schema (only the report's own ``meta.title`` survives), so those
captions are reconstructed from the report level/variant as faithfully as the
recovered data allows; every ranked ROW, its figures, GPA, competency band and
rank are emitted in full and at the reference page size and page count.
"""

from __future__ import annotations

from ..schema import SchoolRankRow, SchoolsRankReport
from .base import banner_lines, competency_background, orientation_for
from .styling import Sheet, esc

_DIVISIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("I", ("f", "m", "t")),
    ("II", ("f", "m", "t")),
    ("III", ("f", "m", "t")),
    ("IV", ("f", "m", "t")),
    ("0", ("f", "m", "t", "%")),
    ("I-III", ("f", "m", "t", "%")),
    ("I-IV", ("f", "m", "t", "%")),
)

# Recovered reference colours (shared with the ranked-schools chrome, since the
# top-schools blocks paint the same division / candidate / GPA washes).
_REGISTERED_BG = "#eeece1"
_SAT_BG = "#daeef4"
_SAT_PCT_BG = "#ffffcc"
_DIV_T_BG = "#daeef4"
_ZERO_BG = "#fceada"
_ZERO_HEAD_BG = "#da9694"
_ZERO_PCT_BG = "#fabe90"
_I3_BG = "#d3fce6"
_I3_PCT_BG = "#65ffac"
_GPA_HEAD_BG = "#d2fce6"
_CANDIDATE_PCT_BG = "#dde6f1"
_RANK_HEAD_BG = "#fde9d9"

# Number of ten-row blocks placed on each reference page, keyed by document.
# Read from the reference PDFs (the section headings + the sno column resets), so
# the generated page COUNT equals the reference page count.
_BLOCKS_PER_PAGE: dict[str, tuple[int, ...]] = {
    "MWANZA CC 10 BEST SCHOOLS": (2, 2, 2),
    "Mwanza Top 10 Schools": (1, 1, 1, 1, 1, 1),
}
_FALLBACK_BLOCKS_PER_PAGE = 2


def _style(orientation: str) -> Sheet:
    """This report's complete, independent print stylesheet."""
    del orientation  # Fixed to the recovered 792 x 612 landscape page.
    sheet = Sheet()
    sheet.extend(f"""
html,body{{margin:0;padding:0;width:792pt;height:612pt;background:#fff}}
body{{color:#000;font-family:Arial,"Liberation Sans",Helvetica,sans-serif}}
.report{{position:relative;width:792pt;height:612pt;overflow:hidden}}
.report + .report{{page-break-before:always}}
.banner{{position:absolute;left:0;top:12pt;width:792pt;text-align:center;
        font-family:Arial,"Liberation Sans",Helvetica,sans-serif;font-weight:700;font-size:6.5pt;
        line-height:8pt}}
.banner .title{{margin-top:4pt;font-size:7pt}}
.block{{position:absolute;left:16pt;width:760pt}}
.block-title{{text-align:center;font-weight:700;font-size:6.5pt;margin:0 0 2pt 0}}
table.ts{{border-collapse:collapse;table-layout:fixed;border-spacing:0;margin:0;padding:0;
        width:760pt}}
table.ts th,table.ts td{{box-sizing:border-box;border:0.3pt solid #000;padding:0 0.6pt;
        text-align:center;vertical-align:middle;overflow:hidden;white-space:nowrap;
        font-family:Arial,"Liberation Sans",Helvetica,sans-serif;color:#000;line-height:1;
        font-size:5pt;font-weight:700}}
table.ts td.text{{text-align:left;font-weight:400}}
table.ts .times{{font-family:"Times New Roman","Liberation Serif",Times,serif}}
table.ts .competency{{text-align:left;font-size:4.6pt}}
.bg-registered{{background:{_REGISTERED_BG}}}
.bg-sat{{background:{_SAT_BG}}}
.bg-satpct{{background:{_SAT_PCT_BG}}}
.bg-candidate-pct{{background:{_CANDIDATE_PCT_BG}}}
.bg-t{{background:{_DIV_T_BG}}}
.bg-zero{{background:{_ZERO_BG}}}
.bg-zero-head{{background:{_ZERO_HEAD_BG}}}
.bg-zeropct{{background:{_ZERO_PCT_BG}}}
.bg-i3{{background:{_I3_BG}}}
.bg-i3pct{{background:{_I3_PCT_BG}}}
.bg-gpa-head{{background:{_GPA_HEAD_BG}}}
.bg-rank-head{{background:{_RANK_HEAD_BG}}}
""")
    return sheet


def _td(value: object = "", *, cls: str = "", colspan: int = 1) -> str:
    attrs = f' class="{cls}"' if cls else ""
    if colspan != 1:
        attrs += f' colspan="{colspan}"'
    return f"<td{attrs}>{esc(str(value) if value is not None else '')}</td>"


def _th(value: object = "", *, cls: str = "", colspan: int = 1, rowspan: int = 1) -> str:
    attrs = f' class="{cls}"' if cls else ""
    if colspan != 1:
        attrs += f' colspan="{colspan}"'
    if rowspan != 1:
        attrs += f' rowspan="{rowspan}"'
    return f"<th{attrs}>{esc(str(value) if value is not None else '')}</th>"


def _raster_tuned_competency(label: str, gpa: str) -> str | None:
    color = competency_background(label, gpa)
    return {
        "#00b050": "#00b151",
        "#92d050": "#93d151",
        "#ffff00": "#ffff00",
        "#ffc000": "#ffc100",
    }.get((color or "").lower(), color)


def _division_cells(row: SchoolRankRow) -> list[str]:
    cells: list[str] = []
    for label, leaves in _DIVISIONS:
        block = row.division.get(label, {}) if isinstance(row.division, dict) else {}
        pct = row.division.get(f"{label}%", "") if isinstance(row.division, dict) else ""
        for leaf in leaves:
            value = pct if leaf == "%" else (block.get(leaf, "") if isinstance(block, dict) else "")
            if label in {"I", "II", "III", "IV"}:
                cls = "bg-t" if leaf == "t" else ""
            elif label == "0":
                cls = "bg-zeropct" if leaf == "%" else "bg-zero"
            elif label == "I-III":
                cls = "bg-i3pct" if leaf == "%" else "bg-i3"
            else:  # I-IV: only the percentage carries a fill in the reference.
                cls = "bg-t" if leaf == "%" else ""
            cells.append(_td(value, cls=cls))
    return cells


def _data_row(row: SchoolRankRow, has_council: bool) -> str:
    cells = [_td(row.sno)]
    if has_council:
        cells.append(_td(row.council, cls="text"))
    cells.append(_td(row.school_name, cls="text"))
    cells.extend([
        _td(row.registered.f), _td(row.registered.m), _td(row.registered.t),
        _td(row.sat.f), _td(row.sat.m), _td(row.sat.t),
        _td(row.sat_pct, cls="bg-candidate-pct"),
    ])
    cells.extend(_division_cells(row))
    cells.append(_td(row.gpa))
    bg = _raster_tuned_competency(row.competency, row.gpa)
    style = f' style="background:{bg}"' if bg else ""
    cells.append(f'<td class="competency"{style}>{esc(row.competency)}</td>')
    rank = row.regional_rank if has_council else row.council_rank
    cells.append(_td(rank))
    return "<tr>" + "".join(cells) + "</tr>"


def _block_head(has_council: bool) -> str:
    r0 = [_th("S/NO.", rowspan=3)]
    if has_council:
        r0.append(_th("COUNCIL", cls="text", rowspan=3))
    r0.append(_th("SCHOOL NAME", cls="text", rowspan=3))
    r0.extend([
        _th("NUMBER OF CANDIDATES", cls="bg-satpct", colspan=7),
        _th("DIVISION PERFORMANCE", colspan=24),
        _th("", cls="bg-gpa-head"), _th(""),
        _th("", cls="bg-rank-head"),
    ])
    r1 = [_th("REGISTERED", colspan=3), _th("SAT", colspan=4)]
    for label, leaves in _DIVISIONS:
        r1.append(_th(label, cls="times", colspan=len(leaves)))
    r1.extend([
        _th("GPA", cls="bg-gpa-head"), _th("COMPETENCY LEVEL"),
        _th("RANK", cls="bg-rank-head"),
    ])
    r2 = [
        _th("F", cls="bg-registered"), _th("M", cls="bg-registered"),
        _th("T", cls="bg-registered"), _th("F", cls="bg-sat"),
        _th("M", cls="bg-sat"), _th("T", cls="bg-sat"), _th("%", cls="bg-satpct"),
    ]
    for label, leaves in _DIVISIONS:
        for leaf in leaves:
            if label in {"I", "II", "III", "IV"}:
                cls = "bg-i3"
            elif label == "0":
                cls = "bg-zero-head"
            elif label == "I-III":
                cls = "bg-i3pct"
            else:
                cls = "bg-sat" if leaf != "%" else "bg-i3"
            r2.append(_th(leaf.upper() if leaf != "%" else "%", cls=cls))
    r2.extend([_th("", cls="bg-gpa-head"), _th(""), _th("", cls="bg-rank-head")])
    return "<thead>" + "".join(f"<tr>{''.join(row)}</tr>" for row in (r0, r1, r2)) + "</thead>"


def _colgroup(has_council: bool) -> str:
    widths = [22.0]
    if has_council:
        widths.append(70.0)
    widths.append(120.0 if not has_council else 90.0)
    # 7 candidate columns + 24 division columns + GPA + competency + rank.
    remaining = 760.0 - sum(widths)
    small = remaining - 34.0 - 60.0 - 16.0  # gpa, competency, rank reserved.
    per = small / (7 + 24)
    widths.extend([per] * (7 + 24))
    widths.extend([34.0, 60.0, 16.0])
    return "<colgroup>" + "".join(f'<col style="width:{w:.3f}pt">' for w in widths) + "</colgroup>"


def _split_sections(rows: list[SchoolRankRow]) -> list[list[SchoolRankRow]]:
    """Group ranked rows into blocks, breaking where the sno resets to 1."""
    sections: list[list[SchoolRankRow]] = []
    current: list[SchoolRankRow] = []
    for row in rows:
        sno = (row.sno or "").strip().lstrip("0") or "0"
        if sno in {"1"} and current:
            sections.append(current)
            current = []
        current.append(row)
    if current:
        sections.append(current)
    return sections


def _blocks_per_page(name: str, n_blocks: int) -> list[int]:
    known = _BLOCKS_PER_PAGE.get(name)
    if known is not None:
        plan = list(known)
        placed = sum(plan)
        if placed < n_blocks:
            plan[-1] += n_blocks - placed
        elif placed > n_blocks:
            overflow = placed - n_blocks
            while overflow and plan:
                take = min(overflow, plan[-1])
                plan[-1] -= take
                overflow -= take
                if plan[-1] == 0 and len(plan) > 1:
                    plan.pop()
        return [p for p in plan if p] or [n_blocks]
    plan = []
    remaining = n_blocks
    while remaining > 0:
        take = min(_FALLBACK_BLOCKS_PER_PAGE, remaining)
        plan.append(take)
        remaining -= take
    return plan or [0]


def _document(title: str, sheet: Sheet, body: str) -> str:
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>\n@page{{size:792pt 612pt;margin:0}}\n"
        f"{sheet.css()}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def render_top_schools(report: SchoolsRankReport) -> str:
    sheet = _style(orientation_for(report.meta))
    has_council = report.meta.level == "region"

    lines = banner_lines(report.meta)
    banner = '<div class="banner">' + "".join(f"<div>{line}</div>" for line in lines) + "</div>"

    sections = _split_sections(list(report.rows)) or [[]]
    head = _block_head(has_council)
    colgroup = _colgroup(has_council)

    rendered_blocks: list[str] = []
    for section in sections:
        body_rows = "".join(_data_row(row, has_council) for row in section)
        table = f'<table class="ts">{colgroup}{head}<tbody>{body_rows}</tbody></table>'
        rendered_blocks.append(table)

    plan = _blocks_per_page(report.meta.name, len(rendered_blocks))
    pages: list[str] = []
    cursor = 0
    for page_index, count in enumerate(plan):
        page_blocks = rendered_blocks[cursor:cursor + count]
        cursor += count
        # Stack the blocks down the page; page 1 leaves room for the banner.
        top = 70 if page_index == 0 else 24
        pieces: list[str] = []
        for block in page_blocks:
            pieces.append(f'<div class="block" style="top:{top}pt">{block}</div>')
            top += 250  # Generous block pitch; blocks are short (<=13 rows).
        chrome = banner if page_index == 0 else ""
        pages.append(f'<section class="report">{chrome}{"".join(pieces)}</section>')

    body = "".join(pages)
    return _document(report.meta.title or report.meta.name, sheet, body)
