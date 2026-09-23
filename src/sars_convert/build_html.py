"""Turn the recovered IR (FEAT-003) into pure, clean, style-preserving HTML+CSS.

This is the FEAT-004 core deliverable. It reads the per-document intermediate
representation produced by :mod:`sars_convert.extract` (``output/ir/<stem>.json``)
and emits one clean semantic HTML file per unique document into
``output/html/<stem>.html`` plus a shared stylesheet ``output/html/styles.css``.

The output is **pure semantic HTML**: real ``<table>``/``<thead>``/``<tbody>``/
``<tr>``/``<th>``/``<td>`` with grouped spanned headers (``colspan``/``rowspan``
taken straight from the IR ``header_rows``), and ``<h1>``/``<h2>``/``<h3>`` for
the banner / section captions. There is **no** absolute positioning, **no** CSS
``transform:matrix`` run placement, and **no** pooled ``.cN`` positional classes
(those belong to the messy ``pdf2html`` source we are replacing).

Styling is chosen to reproduce the *appearance* of the reference PDFs, not a
generic re-theme:

* **S1051 student report** - pale cyan page, purple bold centred banner, a
  purple section caption, a yellow-tinted pivot header, and the main student
  table with a cream header row, blue CNO text, thin borders on a faint cyan
  body, and a left-wrapped free-text ``DETAILED SUBJECTS`` column.
* **council / region reports** - white page, black bold centred banner and
  section captions, a pale-yellow ``NUMBER OF CANDIDATES`` super-header, the
  rotated ``C/RANK`` header rendered upright-vertical with CSS
  ``writing-mode``, and conditional shading on the percentage cells the IR
  flags (``percent_cells``): green near 100, amber in the middle, red/pink low.

``@page`` is set to ``A4 landscape`` or ``A4 portrait`` per the IR
``orientation`` field, and ``thead { display: table-header-group; }`` makes
WeasyPrint repeat the header on every page of a multi-page table (e.g. the
S1051 student roster).
"""

from __future__ import annotations

import json
import os
from html import escape

IR_DIR = os.path.join("output", "ir")
HTML_DIR = os.path.join("output", "html")
STYLESHEET = "styles.css"


# ---------------------------------------------------------------------------
# Rotated / garbled header label repair
# ---------------------------------------------------------------------------
# pdfplumber reads vertically-set header glyphs (C/RANK, SEX, POSITION, ...) as
# reversed / space-joined runs. We map every observed garbled spelling back to
# its correct upright label. Rendering the *correct* label (optionally rotated
# by CSS) is styling, not fixed-layout positioning of source text runs.
_ROTATED_LABELS = {
    # C/RANK (council/region rank column, set vertically)
    "K N A R /C": "C/RANK",
    "R /C": "C/RANK",
    "KNAR": "C/RANK",
    "KNA": "C/RANK",
    "K N A": "C/RANK",
    "K N": "C/RANK",
    "KN": "C/RANK",
    "K": "C/RANK",
    # SEX
    "X E S": "SEX",
    "XES": "SEX",
    # AGGT
    "T G G A": "AGGT",
    "TGGA": "AGGT",
    # DIVISION
    "N O IS IV ID": "DIVISION",
    "NOISIVID": "DIVISION",
    # POSITION / POS
    "N O IT IS O P": "POSITION",
    "NOITISOP": "POSITION",
    "O IT IS O P": "POSITION",
    "IT IS O P": "POSITION",
    "SOP": "POS",
    # MARKS / GRADE (subjectwise student tables)
    "S K R A M": "MARKS",
    "SKRAM": "MARKS",
    "E D A R G": "GRADE",
    "EDARG": "GRADE",
}

# Labels that should be rendered with a vertical (rotated) orientation to match
# the reference PDF's tall single-glyph-wide header cell.
_VERTICAL_LABELS = {"C/RANK"}


def repair_label(label: str) -> str:
    """Return the upright, human-readable form of a (possibly rotated) label."""
    text = " ".join(label.split())
    if text in _ROTATED_LABELS:
        return _ROTATED_LABELS[text]
    # collapsed vertical form with no spaces, e.g. 'NOISIVID'
    if text in _ROTATED_LABELS:
        return _ROTATED_LABELS[text]
    return text


# ---------------------------------------------------------------------------
# Conditional percentage shading
# ---------------------------------------------------------------------------
def percent_class(value: str) -> str:
    """Map a percentage value to a graded shading class.

    Reproduces the reference PDFs' conditional colouring of ``%`` cells:
    ~100 -> green, mid -> amber, low -> red/pink. Non-numeric values get no
    class.
    """
    text = value.strip().rstrip("%")
    try:
        pct = float(text)
    except ValueError:
        return ""
    if pct >= 99.5:
        return "pct-hi"
    if pct >= 75:
        return "pct-good"
    if pct >= 50:
        return "pct-mid"
    if pct >= 25:
        return "pct-low"
    return "pct-min"


# ---------------------------------------------------------------------------
# Cell classification for alignment
# ---------------------------------------------------------------------------
# Column labels whose data is left-aligned free text (everything else that is
# not numeric is centred like the reference tables).
_LEFT_LABELS = {
    "SCHOOL NAME",
    "CANDIDATE FULL NAME",
    "DETAILED SUBJECTS",
    "COMPETENCY LEVEL",
    "COMPENTENCY LEVEL",
    "SCHOOL",
    "COUNCIL",
    "DISTRICT",
    "SUBJECT NAME",
    "CATEGORY",
    "HALI YA",
}


def _is_numeric(text: str) -> bool:
    t = text.strip().rstrip("%'\"")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _cell_align(text: str, col_label: str) -> str:
    label = col_label.strip().upper()
    if label in {lbl.upper() for lbl in _LEFT_LABELS}:
        return "left"
    if _is_numeric(text):
        return "center"
    # short codes / ordinals centre; longer prose lefts
    if len(text) > 24:
        return "left"
    return "center"


# ---------------------------------------------------------------------------
# Header rendering
# ---------------------------------------------------------------------------
def _column_labels(header_rows: list[list[dict]], n_cols: int) -> list[str]:
    """Resolve the effective (bottom-most) label for each column."""
    labels = [""] * n_cols
    for row in header_rows:
        for cell in row:
            lbl = repair_label(cell["label"])
            for c in range(cell["col"], min(cell["col"] + cell["colspan"], n_cols)):
                labels[c] = lbl
    return labels


def _header_group_class(label: str) -> str:
    """Return a tint class for a known super-header group."""
    up = label.upper()
    if up == "NUMBER OF CANDIDATES":
        return "grp-cand"
    if up == "DIVISION PERFORMANCE":
        return "grp-div"
    if up in {"GPA PERFORMANCE", "GRADE PERFORMANCE", "GRADING PERFORMANCE"}:
        return "grp-gpa"
    return ""


def render_thead(header_rows: list[list[dict]], n_cols: int) -> str:
    """Emit a grouped ``<thead>`` from the IR header spans."""
    if not header_rows:
        return ""
    out = ["<thead>"]
    for row in header_rows:
        cells = sorted(row, key=lambda c: c["col"])
        tr = ["<tr>"]
        for cell in cells:
            label = repair_label(cell["label"])
            attrs = []
            if cell["colspan"] > 1:
                attrs.append(f'colspan="{cell["colspan"]}"')
            if cell["rowspan"] > 1:
                attrs.append(f'rowspan="{cell["rowspan"]}"')
            classes = []
            grp = _header_group_class(label)
            if grp:
                classes.append(grp)
            if label in _VERTICAL_LABELS:
                classes.append("vhead")
            if label == "%":
                classes.append("pct-head")
            if classes:
                attrs.append(f'class="{" ".join(classes)}"')
            attr_str = (" " + " ".join(attrs)) if attrs else ""
            out.append(f"<th{attr_str}>{escape(label)}</th>")
        tr.append("</tr>")
        out.append("".join(tr))
    out.append("</thead>")
    return "\n".join(out)


def render_tbody(table: dict, col_labels: list[str]) -> str:
    """Emit ``<tbody>`` with per-cell alignment, CNO colouring and % shading."""
    n_cols = table["n_cols"]
    percent = table.get("percent_cells", [])
    out = ["<tbody>"]
    for ri, row in enumerate(table["body"]):
        cells = list(row) + [""] * (n_cols - len(row))
        pct_row = percent[ri] if ri < len(percent) else [False] * n_cols
        tds = []
        for ci in range(n_cols):
            text = cells[ci]
            label = col_labels[ci] if ci < len(col_labels) else ""
            classes = [f"al-{_cell_align(text, label)}"]
            if label in {"CNO", "C/NO", "ID NO."} and text:
                classes.append("cno")
            if ci < len(pct_row) and pct_row[ci]:
                pc = percent_class(text)
                if pc:
                    classes.append(pc)
            cls = f' class="{" ".join(classes)}"'
            tds.append(f"<td{cls}>{escape(text)}</td>")
        out.append(f"<tr>{''.join(tds)}</tr>")
    out.append("</tbody>")
    return "\n".join(out)


def render_table(table: dict) -> str:
    """Render one IR table as a clean semantic ``<table>``."""
    n_cols = table["n_cols"]
    col_labels = _column_labels(table.get("header_rows", []), n_cols)
    kind = table.get("kind", "table")
    table_class = "report pivot" if kind == "pivot" else "report"
    parts = [f'<table class="{table_class}">']
    thead = render_thead(table.get("header_rows", []), n_cols)
    if thead:
        parts.append(thead)
    parts.append(render_tbody(table, col_labels))
    parts.append("</table>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Section merging
# ---------------------------------------------------------------------------
def _same_header(a: dict, b: dict) -> bool:
    return a.get("header_rows") == b.get("header_rows") and a["n_cols"] == b["n_cols"]


def merge_continuations(tables: list[dict]) -> list[dict]:
    """Merge headerless continuation tables into the preceding table.

    Multi-page region reports (e.g. school-rank) emit the full grouped header on
    page 1 and headerless continuation grids on later pages. We fold a
    header-less table's body into the previous table so the clean output is one
    continuous table with a single repeated header, rather than a broken table
    with a missing head.
    """
    merged: list[dict] = []
    for tbl in tables:
        if merged and not tbl.get("header_rows") and tbl["n_cols"] == merged[-1]["n_cols"]:
            prev = merged[-1]
            prev["body"].extend(tbl["body"])
            prev["percent_cells"].extend(tbl.get("percent_cells", []))
            continue
        merged.append(json.loads(json.dumps(tbl)))  # copy so we can extend
    return merged


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------
def _category_class(category: str) -> str:
    return {"student": "doc-student", "council": "doc-office", "region": "doc-office"}.get(
        category, "doc-office"
    )


def build_document_html(ir: dict) -> str:
    """Assemble the full clean HTML document for one IR."""
    stem = ir["stem"]
    category = ir.get("category", "region")
    orientation = ir.get("orientation", "landscape")
    doc_class = _category_class(category)

    body: list[str] = []
    # Banner heading lines.
    title_lines = ir.get("title_lines", [])
    if title_lines:
        body.append('<header class="banner">')
        for i, line in enumerate(title_lines):
            tag = "h1" if i == 0 else "h2"
            body.append(f"<{tag}>{escape(line)}</{tag}>")
        body.append("</header>")

    # Standalone captions (those not attached to a specific table).
    caption_list = list(ir.get("captions", []))

    tables = merge_continuations(ir.get("tables", []))
    for ti, table in enumerate(tables):
        caption = table.get("caption", "")
        if not caption and ti < len(caption_list):
            caption = caption_list[ti]
        if caption:
            body.append(f'<h3 class="section-caption">{escape(caption)}</h3>')
        body.append(render_table(table))

    head = (
        "<!DOCTYPE html>\n"
        '<html lang="en-US">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{escape(stem)}</title>\n"
        f'<link rel="stylesheet" href="{STYLESHEET}">\n'
        f"<style>@page {{ size: A4 {orientation}; margin: 10mm 8mm; }}</style>\n"
        "</head>\n"
        f'<body class="{doc_class}">\n'
    )
    return head + "\n".join(body) + "\n</body>\n</html>\n"


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------
STYLES_CSS = """\
/* sars-convert clean output stylesheet (FEAT-004).
   Reproduces the reference PDF appearance: no absolute positioning, no
   transforms, no pooled .cN classes -- only semantic tables + print CSS. */

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 8px;
  color: #000000;
}

/* Repeat the table header on every printed page (WeasyPrint). */
thead { display: table-header-group; }
tr { page-break-inside: avoid; }

/* ---- banner + captions ---- */
.banner { text-align: center; margin: 0 0 6px; }
.banner h1, .banner h2 {
  margin: 1px 0;
  font-weight: 700;
  line-height: 1.15;
}
.banner h1 { font-size: 11px; }
.banner h2 { font-size: 10px; }

.section-caption {
  font-weight: 700;
  margin: 8px 0 3px;
  font-size: 10px;
}

/* ---- tables ---- */
table.report {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 6px;
  table-layout: auto;
}
table.report th,
table.report td {
  border: 0.5px solid #555;
  padding: 0.5px 2px;
  vertical-align: middle;
  overflow-wrap: break-word;
}
/* keep the numeric grid columns tight so the wide entity-name column can
   breathe, matching the reference PDF proportions */
table.report td.al-center { white-space: nowrap; }
table.report thead th {
  font-weight: 700;
  text-align: center;
  background: #f2f2f2;
}

.al-left { text-align: left; }
.al-center { text-align: center; }
.al-right { text-align: right; }

/* rotated single-column header (C/RANK) */
th.vhead {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  white-space: nowrap;
  padding: 2px 0;
  width: 12px;
}

/* header group tints (match the reference PDF) */
th.grp-cand { background: #fffbcc; }        /* NUMBER OF CANDIDATES: pale yellow */
th.grp-div  { background: #eef2f7; }        /* DIVISION PERFORMANCE */
th.grp-gpa  { background: #eaf6ea; }        /* GPA/GRADE PERFORMANCE */
th.pct-head { background: #f4cccc; }        /* the '%' sub-header cells */

/* conditional percentage shading (graded) */
td.pct-hi   { background: #57bb63; color: #06300f; font-weight: 700; }
td.pct-good { background: #a7d7a9; }
td.pct-mid  { background: #ffd28a; }
td.pct-low  { background: #f7b26a; }
td.pct-min  { background: #f4a6a0; }

/* blue candidate numbers, like the reference */
td.cno { color: #1155cc; font-weight: 700; }

/* =====================================================================
   S1051 student report -- pale cyan page, purple banner + caption,
   cream table headers, faint cyan body.
   ===================================================================== */
body.doc-student { background: #cfe9ef; }
body.doc-student .banner h1,
body.doc-student .banner h2 { color: #7030a0; }
body.doc-student .section-caption { color: #7030a0; }
body.doc-student table.report { background: #ffffff; }
body.doc-student table.report th,
body.doc-student table.report td { border-color: #7f7f9f; }
body.doc-student table.report thead th { background: #fff2cc; }
body.doc-student table.report tbody { background: #eaf6f8; }
/* the S1051 student roster is long free text; keep it compact so the roster
   paginates like the reference (small serif-ish free text, single-ish line) */
body.doc-student table.report { font-size: 7px; }
body.doc-student table.report td { padding: 0.5px 3px; line-height: 1.1; }
/* the DIVISION PERFORMANCE SUMMARY pivot is a small centred block, not full
   width -- shrink it to its content like the reference */
body.doc-student table.pivot {
  width: auto;
  min-width: 260px;
  margin: 0 0 8px;
}
body.doc-student table.pivot th,
body.doc-student table.pivot td { padding: 1px 10px; text-align: center; }

/* =====================================================================
   council / region office reports -- white page, black banner.
   ===================================================================== */
body.doc-office { background: #ffffff; }
body.doc-office .banner h1,
body.doc-office .banner h2 { color: #000000; }
body.doc-office .section-caption { color: #000000; text-align: center; }
"""


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _load_ir(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_one(stem: str, ir_dir: str = IR_DIR, out_dir: str = HTML_DIR) -> str:
    """Build the clean HTML for a single document stem."""
    os.makedirs(out_dir, exist_ok=True)
    ir = _load_ir(os.path.join(ir_dir, f"{stem}.json"))
    html = build_document_html(ir)
    out_path = os.path.join(out_dir, f"{stem}.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


def build_all(ir_dir: str = IR_DIR, out_dir: str = HTML_DIR) -> list[str]:
    """Build clean HTML for every IR document into ``out_dir``.

    Byte-identical duplicates (IR files that only carry ``duplicate_of``) are
    materialised by copying the canonical document's HTML so the full set of
    files exists on disk.
    """
    os.makedirs(out_dir, exist_ok=True)
    # write the shared stylesheet
    with open(os.path.join(out_dir, STYLESHEET), "w", encoding="utf-8") as fh:
        fh.write(STYLES_CSS)

    written: list[str] = []
    duplicates: list[tuple[str, str]] = []
    for name in sorted(os.listdir(ir_dir)):
        if not name.endswith(".json"):
            continue
        ir = _load_ir(os.path.join(ir_dir, name))
        stem = ir.get("stem", name[:-5])
        if "tables" not in ir and ir.get("duplicate_of"):
            duplicates.append((stem, ir["duplicate_of"]))
            continue
        html = build_document_html(ir)
        out_path = os.path.join(out_dir, f"{stem}.html")
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        written.append(out_path)

    # materialise duplicates from their canonical HTML
    for dup, canonical in duplicates:
        src = os.path.join(out_dir, f"{canonical}.html")
        dst = os.path.join(out_dir, f"{dup}.html")
        if os.path.exists(src):
            with open(src, encoding="utf-8") as fh:
                content = fh.read()
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write(content)
            written.append(dst)
    return written


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    paths = build_all()
    print(f"Wrote {len(paths)} HTML files to {HTML_DIR}/")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
