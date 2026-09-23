"""Recover exact tabular data and grid structure from the ORIGINAL PDFs.

This is the FEAT-003 core deliverable. Per the user's decisive direction and
``DECISION.md``, the tabular *truth* for every report is recovered directly
from the reference PDFs with `pdfplumber` -- **not** guessed from the messy
`pdf2html` HTML geometry (which shatters the grouped multi-row headers). The
messy HTML is only used here for a cross-check that no rows/values were dropped.

The output is a domain-labelled **intermediate representation** (IR) written to
``output/ir/<stem>.json`` that :mod:`sars_convert.build_html` (FEAT-004) turns
into clean HTML+CSS. The IR captures, per document:

* ``pages`` / ``orientation`` (A4 landscape or portrait, per README section 6);
* the centred title/banner lines as ordered heading lines (NOT table rows);
* section captions (e.g. ``TOP TEN BEST SCHOOLS OVERALL COUNCILWISE``,
  ``DIVISION PERFORMANCE SUMMARY``);
* each real data table as a grid with its multi-row grouped header preserved as
  ``(label, colspan, rowspan)`` spans, its body rows, and per-cell hints
  (numeric-percentage cells the reference PDF colour-codes) so FEAT-004 can
  reproduce the conditional shading and emit a correct spanned ``<thead>``;
* the raw recovered grid (nothing is discarded), so reviewers can see exactly
  what pdfplumber returned.

This is a **data-recovery library, not a generic auto-detector**. The reports
are highly regular within a category (S1051 student-list; council multi-table;
region single-table), so extraction is organised as a small set of
per-category *profiles* keyed by document stem. The grouped-header
reconstruction is geometric (a merged cell emits its label once then ``None``
for the columns/rows it spans), which is a faithful, deterministic reading of
the PDF's own cell-merge structure rather than a heuristic guess.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

import pdfplumber

try:  # pragma: no cover - import shim; only needed for the HTML cross-check
    from bs4 import BeautifulSoup

    from .converter import parse_font_classes, parse_runs
except ImportError:  # pragma: no cover
    BeautifulSoup = None  # type: ignore[assignment]
    parse_font_classes = parse_runs = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Document registry (per-category profiles keyed by stem)
# ---------------------------------------------------------------------------
DATA_ROOT = "data/sars"
IR_DIR = os.path.join("output", "ir")

# Portrait sources are 612x792 pt; everything else is landscape 792x612 pt.
PORTRAIT_STEMS = {
    "Mwanza f2 Mock Mobility 2026",
    "Mwanza School Rank-EDK",
    "Mwanza School Rank-English Language",
    "MWANZA CC SCHOOLS RANK SUBJECTWISE",
}

COUNCIL_STEMS = [
    "MWANZA CC 10 BEST SCHOOLS",
    "MWANZA CC 10 BEST STUDENTS",
    "MWANZA CC 10 BEST STUDENTS SUBJECTWISE",
    "MWANZA CC SCHOOLS RANK",
    "MWANZA CC SCHOOLS RANK SUBJECTWISE",
    "MWANZA CC SUBJECTS RANK",
    "MWANZA CC Wards Rank",
]

REGION_STEMS = [
    "Mwanza Best Students-Overall",
    "Mwanza Best students-Subjectwise",
    "Mwanza f2 District Performance",
    "Mwanza f2 Mock Mobility 2026",
    "Mwanza Overall Subjects Performance",
    "Mwanza School Rank-EDK",
    "Mwanza School Rank-English Language",
    "Mwanza Schools Rank For Governments",
    "Mwanza schools rank Overall",
    "Mwanza Top 10 Schools",
]

# 'Mwanza Schools Rank For Governments (1)' is byte-identical to the non-(1)
# copy (verified md5 abcc1c77...); it is deduped with a note rather than
# extracted twice, giving 18 unique documents.
DUPLICATE_STEMS = {
    "Mwanza Schools Rank For Governments (1)": "Mwanza Schools Rank For Governments",
}

# The five (or six) centred banner lines every report opens with. These are
# collapsed by pdfplumber into a single top-left cell; we split them back into
# ordered heading lines and never treat them as table data.
_BANNER_PREFIXES = (
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
    "MWANZA REGION",
    "REGIONAL FORM TWO MOCK ASSESSMENT RESULTS",
)

# The four centred banner lines are CONSTANT across every report (the fourth
# reads 'REGIONAL FORM TWO ASSESSMENT RESULTS, JULY 2026' -- no 'MOCK' -- for
# the two subject-rank docs). pdfplumber sometimes collapses them into a single
# top-left table cell (the good docs) but for other layouts it emits them as
# free page text above/around the grid, so ``page.extract_tables()`` alone
# misses them and ``title_lines`` comes back empty. ``_recover_banner_lines``
# reads the top region of page 0 as words, clusters them into lines, and pulls
# these known banner lines + the report subtitle line(s) precisely, for EVERY
# document. This is a precise per-template recovery of known-constant text, not
# a fragile generic heading detector.
_STANDARD_BANNER_LINES = (
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
    "MWANZA REGION",
)
# Recognise line 4 in either the 'MOCK' or the plain phrasing.
_BANNER_LINE4_RE = re.compile(r"^REGIONAL FORM TWO (MOCK )?ASSESSMENT RESULTS, JULY 2026$")

# Y-coordinate ceiling (PDF points from the page top) within which the banner
# and report subtitle always sit on page 0 of every report.
_BANNER_TOP_MAX = 135.0
# Section captions on a fresh section page sit just below the banner but can
# nudge past ``_BANNER_TOP_MAX`` by a point or two (e.g. the GEOGRAPHY subject
# page lands the caption at top=135.2). We scan a wider top region for the
# per-section caption and rely on the header-band terminator (not a hard
# y-cutoff) to know where the caption region ends.
_CAPTION_TOP_MAX = 175.0
# Tokens that signal the start of the table header band (never a subtitle) so
# banner recovery stops before swallowing grouped-header text.
_HEADER_BAND_TOKENS = (
    "NUMBER OF CANDIDATES",
    "DIVISION PERFORMANCE",
    "GPA PERFORMANCE",
    "GRADE PERFORMANCE",
    "GRADING PERFORMANCE",
    "NUMBER OF",
    # column-header labels that can share a line with caption keywords
    "GPA",
    "COMPETENCY",
    "COMPENTENCY",
    "SCHOOL NAME",
    "CANDIDATE FULL NAME",
    "SUBJECT NAME",
    "TOTAL",
    "REGISTERED",
    # ordinal / serial column heads and rotated-rank glyph fragments
    "S/NO.",
    "S/NO",
    "S/N",
    "C/NO.",
    "C/NO",
    "CNAM",
    "NOISIVID",
    "KNAR",
    "ID O",
)

# Captions that introduce a table (as opposed to titling the whole report).
_CAPTION_MARKERS = (
    "DIVISION PERFORMANCE SUMMARY",
    "EXAMINATION CENTRE SUBJECTS GRADING PERFORMANCE SUMMARY",
)

_PERCENT_RE = re.compile(r"^\d{1,3}(\.\d+)?$")
# A body row's leading cell is an ordinal/rank ('01', '10'), a serial ('001'),
# or a candidate number ('S5344-0004'). This is the strongest data-row signal.
_ORDINAL_RE = re.compile(r"^\d{1,4}$")
_CNO_RE = re.compile(r"^S\d+-\d+$")


@dataclass
class HeaderCell:
    """One spanned header cell for a ``<thead>`` (label, colspan, rowspan)."""

    label: str
    colspan: int = 1
    rowspan: int = 1
    col: int = 0
    row: int = 0


@dataclass
class Table:
    """A recovered data table with grouped header, body and per-cell hints."""

    caption: str = ""
    n_cols: int = 0
    header_rows: list[list[HeaderCell]] = field(default_factory=list)
    body: list[list[str]] = field(default_factory=list)
    # per body cell: True where the value is a percentage the PDF colour-codes.
    percent_cells: list[list[bool]] = field(default_factory=list)
    raw: list[list[str | None]] = field(default_factory=list)
    kind: str = "table"  # table | pivot | student-list


@dataclass
class DocumentIR:
    """The full intermediate representation for one report document."""

    stem: str
    category: str
    orientation: str
    pages: int
    page_size: list[float]
    title_lines: list[str] = field(default_factory=list)
    captions: list[str] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    crosscheck: dict = field(default_factory=dict)
    duplicate_of: str | None = None


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------
def _clean(value: str | None) -> str:
    """Normalise a raw pdfplumber cell to a single-line, stripped string.

    Rotated headers arrive as vertical text (``'K\\nN\\nA\\nR\\n/C'`` for
    ``C/RANK``); we keep the glyphs but drop the newlines so the label is
    readable and matchable.
    """
    if value is None:
        return ""
    return " ".join(value.split())


def _is_banner_cell(value: str | None) -> bool:
    if not value:
        return False
    first = value.split("\n", 1)[0].strip()
    return any(first.startswith(p) for p in _BANNER_PREFIXES)


def split_banner(value: str) -> list[str]:
    """Split the collapsed banner cell into ordered non-empty heading lines."""
    return [ln.strip() for ln in value.split("\n") if ln.strip()]


def _top_lines(page, y_max: float) -> list[str]:
    """Cluster page words with ``top < y_max`` into ordered text lines.

    Words on the same visual line share (approximately) a ``top`` coordinate;
    we group within a small tolerance and join left-to-right so a centred
    banner line comes back as one string in reading order (which
    ``page.extract_text`` does not guarantee when a wide table header outranks
    the centred banner).
    """
    words = [w for w in page.extract_words() if w["top"] < y_max]
    rows: list[tuple[float, list[dict]]] = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        top = w["top"]
        placed = False
        for row in rows:
            if abs(row[0] - top) <= 3.5:
                row[1].append(w)
                placed = True
                break
        if not placed:
            rows.append((top, [w]))
    lines: list[str] = []
    for _, group in sorted(rows, key=lambda r: r[0]):
        text = " ".join(w["text"] for w in sorted(group, key=lambda w: w["x0"]))
        text = " ".join(text.split())
        if text:
            lines.append(text)
    return lines


def _is_header_band_line(line: str) -> bool:
    """True when ``line`` begins the table header band (not a caption).

    The header band opens with a grouped super-header (``GRADING PERFORMANCE``,
    ``NUMBER OF CANDIDATES`` ...) or the column-label row (``S/N SCHOOL NAME
    A B C ...``). Recognising it lets caption recovery stop cleanly instead of
    relying on a brittle y-coordinate cutoff.
    """
    up = line.upper()
    return any(tok in up for tok in _HEADER_BAND_TOKENS)


def _banner_body_lines(page) -> list[str]:
    """Return top-region lines with the standard banner opening stripped off.

    Leaves the report subtitle / per-page section caption line(s) and whatever
    follows, in reading order, so callers can pick the subtitle (banner) or the
    per-page section caption. We scan the wider caption region (``_CAPTION_TOP_MAX``)
    and stop at the first header-band line so a caption that nudges a point or
    two past ``_BANNER_TOP_MAX`` (e.g. the GEOGRAPHY subject page) is still
    recovered, while header-band text is never mistaken for a caption.
    """
    lines = _top_lines(page, _CAPTION_TOP_MAX)
    idx = 0
    n = len(lines)
    for standard in _STANDARD_BANNER_LINES:
        for j in range(idx, n):
            if lines[j] == standard:
                idx = j + 1
                break
    for j in range(idx, n):
        if _BANNER_LINE4_RE.match(lines[j]):
            idx = j + 1
            break
    # keep only the lines between the banner and the start of the header band.
    body: list[str] = []
    for line in lines[idx:]:
        if _is_header_band_line(line):
            break
        body.append(line)
    return body


# Words that positively identify a report subtitle / per-page section caption
# in these SARS reports (school/council/region result headings). A caption line
# must contain at least one of these and must NOT be a data row or a header
# band fragment. This keeps caption recovery a precise, domain-anchored read.
_CAPTION_KEYWORDS = (
    "PERFORMANCE",
    "SCHOOLS",
    "SCHOOL",
    "STUDENTS",
    "STUDENT",
    "RANK",
    "WARDS",
    "SUBJECT",
    "SUBJECTS",
    "MOBILITY",
    "BEST",
    "LOOSER",
    "TOP",
    "OVERALL",
)


def _looks_like_caption(line: str) -> bool:
    """True when ``line`` reads like a real report subtitle / section title.

    A caption is a centred domain heading (``TOP 10 BEST GOVERNMENT SCHOOLS``,
    ``DISTRICT PERFORMANCE FOR PRIVATE SCHOOLS ONLY``). We reject: rotated
    single-glyph header fragments (``'N N'``, ``'X G IV IS'``); header-band
    label rows (``I II III 0 GPA COMPETENCY LEVEL ...``); and data rows (which
    start with an ordinal/serial/candidate number). The line must carry a known
    section keyword, anchoring the recovery to the report domain rather than a
    fragile generic heuristic.
    """
    up = line.upper()
    if any(tok in up for tok in _HEADER_BAND_TOKENS):
        return False
    tokens = line.split()
    if not tokens:
        return False
    # data rows / header rows start with an ordinal, serial or candidate number.
    if _ORDINAL_RE.match(tokens[0]) or _CNO_RE.match(tokens[0]) or _PERCENT_RE.match(tokens[0]):
        return False
    if not any(kw in up for kw in _CAPTION_KEYWORDS):
        return False
    # reject rotated-glyph strips: mostly one/two-character tokens.
    short = sum(1 for t in tokens if len(t.strip("/.")) <= 2)
    return short < max(2, len(tokens) * 0.5)


def _section_caption(page) -> str:
    """Return the clean section caption for a page (``''`` if none).

    The first caption-like line below the banner names the section (e.g.
    ``TOP 10 BEST GOVERNMENT SCHOOLS``); the header band and its column labels
    that follow are rejected by :func:`_looks_like_caption`.
    """
    for line in _banner_body_lines(page):
        if _looks_like_caption(line):
            return line
    return ""


def _recover_banner_lines(page) -> list[str]:
    """Recover the ordered banner + report-subtitle lines from page 0 words.

    Returns the four constant banner lines followed by the report subtitle
    line(s) that sit between the banner and the table header band. Precise
    recovery of known-constant text: the first four lines are matched against
    the standard banner; subsequent centred lines are kept as subtitles until
    the first line that begins the table header band.
    """
    lines = _top_lines(page, _BANNER_TOP_MAX)
    banner: list[str] = []
    idx = 0
    n = len(lines)

    # 1) the three fixed opening lines, in order (tolerate a missing one).
    for standard in _STANDARD_BANNER_LINES:
        for j in range(idx, n):
            if lines[j] == standard:
                banner.append(standard)
                idx = j + 1
                break

    # 2) line 4 ('REGIONAL FORM TWO [MOCK] ASSESSMENT RESULTS, JULY 2026').
    for j in range(idx, n):
        if _BANNER_LINE4_RE.match(lines[j]):
            banner.append(lines[j])
            idx = j + 1
            break

    # 3) subtitle line(s): centred report titles after line 4, up to the table
    #    header band. Stop at the first line carrying a header-band token or a
    #    rotated glyph strip; keep at most two caption-like subtitle lines.
    for line in lines[idx:]:
        if not _looks_like_caption(line):
            break
        banner.append(line)
        if len(banner) >= len(_STANDARD_BANNER_LINES) + 3:
            break

    return banner


def _row_nonempty(row: list[str | None]) -> int:
    return sum(1 for c in row if _clean(c))


def is_header_row(row: list[str | None]) -> bool:
    """Heuristic: a header band row is mostly non-numeric labels.

    Data rows in these reports are dominated by numbers (counts, GPAs, %),
    ordinals and short codes. Header rows carry words like ``SCHOOL NAME``,
    ``DIVISION PERFORMANCE``, ``REGISTERED``, ``F/M/T``, roman numerals and
    ``%``. We treat a row as a header when a majority of its filled cells are
    non-numeric label tokens.
    """
    filled = [_clean(c) for c in row if _clean(c)]
    if not filled:
        return False
    label_like = 0
    for cell in filled:
        if _PERCENT_RE.match(cell):
            continue  # a bare number -> data-ish
        if re.fullmatch(r"-?\d+(\.\d+)?", cell):
            continue
        label_like += 1
    return label_like >= max(1, len(filled)) * 0.5


def reconstruct_header_spans(header_grid: list[list[str | None]]) -> list[list[HeaderCell]]:
    """Rebuild grouped ``(label, colspan, rowspan)`` cells from a header band.

    pdfplumber represents merged cells by placing the text once (top-left of
    the merge) and ``None`` for every other position it spans. We read that
    directly:

    * **colspan** = the label cell plus the run of trailing ``None`` cells to
      its right, up to the next labelled cell in the same row.
    * **rowspan** = how many following header rows keep that column ``None``
      (i.e. the merge extends downward) *and* have no label starting inside the
      span. A label that only appears on the last header row has rowspan 1.

    The result is a list (one entry per header row) of the spanned cells that
    originate on that row, tagged with their originating ``col``/``row`` so a
    builder can emit a correct multi-row ``<thead>``.
    """
    n_rows = len(header_grid)
    n_cols = max((len(r) for r in header_grid), default=0)
    grid = [[_clean(c) for c in r] + [""] * (n_cols - len(r)) for r in header_grid]

    # occupied[r][c] = True once a span from an earlier cell covers (r, c).
    occupied = [[False] * n_cols for _ in range(n_rows)]
    out: list[list[HeaderCell]] = [[] for _ in range(n_rows)]

    for r in range(n_rows):
        c = 0
        while c < n_cols:
            if occupied[r][c] or not grid[r][c]:
                c += 1
                continue
            label = grid[r][c]
            # colspan: extend right over blank, unoccupied cells.
            colspan = 1
            cc = c + 1
            while cc < n_cols and not grid[r][cc] and not occupied[r][cc]:
                colspan += 1
                cc += 1
            # rowspan: extend down while the covered columns stay blank.
            rowspan = 1
            rr = r + 1
            while rr < n_rows:
                block_blank = all(
                    not grid[rr][k] and not occupied[rr][k] for k in range(c, c + colspan)
                )
                if not block_blank:
                    break
                rowspan += 1
                rr += 1
            for ri in range(r, r + rowspan):
                for ci in range(c, c + colspan):
                    occupied[ri][ci] = True
            out[r].append(HeaderCell(label=label, colspan=colspan, rowspan=rowspan, col=c, row=r))
            c = cc
    return out


def _percent_hint(cell: str, col_label: str) -> bool:
    """True when a body cell is a percentage value the PDF colour-codes.

    The reference PDFs shade the ``%`` columns (SAT %, I-III %, I-IV %, % PASS)
    green near 100 and orange/red for lower values. We flag any bare numeric
    value sitting under a ``%`` header so FEAT-004 can reproduce that shading.
    """
    text = cell.strip()
    if not _PERCENT_RE.match(text):
        return False
    return col_label.strip() == "%" or "%" in col_label


def _split_head_and_body(
    rows: list[list[str | None]],
) -> tuple[list[list[str | None]], list[list[str | None]]]:
    """Split a table's rows into the leading header band and the body."""
    head: list[list[str | None]] = []
    body_start = 0
    for i, row in enumerate(rows):
        filled = [_clean(c) for c in row if _clean(c)]
        # A leading ordinal/serial/CNO is an unambiguous data row -> the header
        # band ends here even if the row carries many text cells (COUNCIL,
        # SCHOOL NAME, candidate names, DIV) that would otherwise look
        # 'label-like'.
        if filled and (_ORDINAL_RE.match(filled[0]) or _CNO_RE.match(filled[0])):
            break
        # A single-cell caption row (e.g. a repeated sub-section title inside a
        # multi-section report) is not part of the grouped header band; stop.
        if _is_caption_row(row):
            break
        if is_header_row(row) and _row_nonempty(row) > 1:
            head.append(row)
            body_start = i + 1
        else:
            # allow a single blank spacer row before the header without
            # ending the band.
            if _row_nonempty(row) == 0 and not head:
                body_start = i + 1
                continue
            break
    return head, rows[body_start:]


def _last_header_labels(header_rows: list[list[HeaderCell]], n_cols: int) -> list[str]:
    """Resolve the effective label for each column (the bottom-most header)."""
    labels = [""] * n_cols
    for row in header_rows:
        for cell in row:
            for c in range(cell.col, cell.col + cell.colspan):
                if c < n_cols:
                    labels[c] = cell.label
    return labels


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def _table_from_grid(grid: list[list[str | None]], caption: str = "", kind: str = "table") -> Table:
    """Turn one raw pdfplumber grid (no banner row) into a labelled Table."""
    n_cols = max((len(r) for r in grid), default=0)
    grid = [list(r) + [None] * (n_cols - len(r)) for r in grid]
    head_grid, body_grid = _split_head_and_body(grid)
    header_rows = reconstruct_header_spans(head_grid)
    col_labels = _last_header_labels(header_rows, n_cols)

    body: list[list[str]] = []
    percent_cells: list[list[bool]] = []
    for row in body_grid:
        cleaned = [_clean(c) for c in row]
        if not any(cleaned):
            continue  # drop fully blank spacer rows
        body.append(cleaned)
        percent_cells.append(
            [_percent_hint(cleaned[c], col_labels[c] if c < n_cols else "") for c in range(n_cols)]
        )

    return Table(
        caption=caption,
        n_cols=n_cols,
        header_rows=header_rows,
        body=body,
        percent_cells=percent_cells,
        raw=[[_clean(c) for c in r] for r in grid],
        kind=kind,
    )


def _is_caption_row(row: list[str | None]) -> str:
    """Return the caption text if ``row`` is a single-cell section caption.

    Section captions (e.g. ``MWANZA CC TOP TEN BEST STUDENTS OVERALL
    COUNCILWISE``, ``SCHOOL RANK IN ELIMU YA DINI YA KIISLAMU SUBJECT
    REGIONALWISE``) sit on their own row with exactly one populated,
    non-numeric cell above the header band.
    """
    filled = [_clean(c) for c in row if _clean(c)]
    if len(filled) != 1:
        return ""
    text = filled[0]
    if _PERCENT_RE.match(text) or len(text) < 8:
        return ""
    return text


def _extract_page_tables(page) -> list[list[list[str | None]]]:
    """Return raw grids for a page, stripping the collapsed banner cell.

    The banner (title lines) is collapsed into the top-left cell of the first
    table; we detect and remove that row so it is handled as heading text, not
    as a data table. Leading single-cell caption rows are also removed here and
    surfaced separately via :func:`_page_captions`.
    """
    grids: list[list[list[str | None]]] = []
    for tbl in page.extract_tables():
        rows = [r for r in tbl if r is not None]
        cleaned: list[list[str | None]] = []
        for row in rows:
            at_top = not any(_row_nonempty(r) for r in cleaned)
            if _is_banner_cell(row[0]) and _row_nonempty(row) <= 1:
                continue
            if at_top and _row_nonempty(row) == 0:
                # skip leading blank spacer rows so a caption below them is
                # still recognised as sitting at the top of the grid.
                continue
            if _is_caption_row(row) and at_top:
                # a caption above the header band -> handled as a caption, not
                # a data row (only strip while still at the top of the grid).
                continue
            cleaned.append(row)
        if any(_row_nonempty(r) for r in cleaned):
            grids.append(cleaned)
    return grids


# Vertical gap (PDF points) within which a caption line sitting ABOVE a grid is
# taken to introduce that grid. Subject captions sit ~12pt above their header
# band; 60pt tolerates the inter-section whitespace without reaching the
# previous section's data.
_CAPTION_GRID_GAP = 60.0


def _caption_lines_with_y(page) -> list[tuple[float, str]]:
    """Return ``(top, text)`` for every caption-like line anywhere on a page.

    Unlike :func:`_section_caption` (which only inspects the top banner region),
    this scans the WHOLE page so section captions that sit mid-page -- the case
    where a report packs several subject sections onto one page -- are found and
    can be matched to the grid each one introduces.
    """
    words = page.extract_words()
    rows: list[tuple[float, list[dict]]] = []
    for w in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        placed = False
        for row in rows:
            if abs(row[0] - w["top"]) <= 3.5:
                row[1].append(w)
                placed = True
                break
        if not placed:
            rows.append((w["top"], [w]))
    out: list[tuple[float, str]] = []
    for top, group in sorted(rows, key=lambda r: r[0]):
        text = " ".join(w["text"] for w in sorted(group, key=lambda w: w["x0"]))
        text = " ".join(text.split())
        if text and _looks_like_caption(text):
            out.append((top, text))
    return out


def _grid_is_new_section(grid: list[list[str | None]]) -> bool:
    """True when a grid begins with a header band (a fresh section start).

    A continuation grid (paginated overflow of the previous section) begins
    directly with a data row (leading ordinal/serial/CNO). A fresh section
    begins with its grouped header band, so its first non-empty row is NOT a
    data row.
    """
    for row in grid:
        cells = _compact(row)
        if not cells:
            continue
        return not (_ORDINAL_RE.match(cells[0]) or _CNO_RE.match(cells[0]))
    return False


def _page_grids_with_captions(
    page, carried_caption: str = ""
) -> tuple[list[tuple[list[list[str | None]], str]], str]:
    """Return ``[(grid, caption)]`` for a page plus any caption carried forward.

    Each recovered grid is matched to the caption line that sits immediately
    above it (within :data:`_CAPTION_GRID_GAP`), so a page that stacks several
    subject sections gets ONE caption PER SECTION rather than a single caption
    for the whole page. A caption at the bottom of a page with no grid below it
    introduces the first *new-section* grid on the following page, returned as
    ``carried_caption`` for the caller to pass in.
    """
    caption_lines = _caption_lines_with_y(page)
    tables = page.find_tables()
    grids = _extract_page_tables(page)
    # ``find_tables`` and ``extract_tables`` return grids in the same order; we
    # zip the cleaned grid with the raw table's top coordinate.
    #
    # Two layouts occur. (a) The banner/caption is free page text ABOVE the grid
    # (the packed subjectwise reports): each grid's caption is the caption line
    # sitting just above it. (b) pdfplumber merges the banner + caption INTO the
    # grid's top-left cell (single-section-per-page reports): the grid bbox then
    # starts at the page top and the caption sits *inside* it, so the
    # above-grid match finds nothing -- we fall back to the page's top section
    # caption for the first grid on such a page.
    pairs: list[tuple[list[list[str | None]], str]] = []
    used_caption_y: set[float] = set()
    page_section = _section_caption(page)
    section_used = False
    n = min(len(tables), len(grids))
    for i in range(n):
        grid = grids[i]
        if not grid:
            continue
        gtop = tables[i].bbox[1]
        caption = ""
        best_y = -1.0
        for cy, ctext in caption_lines:
            if cy < gtop and (gtop - cy) < _CAPTION_GRID_GAP and cy > best_y:
                best_y, caption = cy, ctext
        if caption:
            used_caption_y.add(best_y)
        elif carried_caption and _grid_is_new_section(grid):
            # a caption stranded at the bottom of the previous page introduces
            # this page's first new section.
            caption = carried_caption
        elif not section_used and page_section and gtop <= _BANNER_TOP_MAX:
            # banner-absorbed layout: the grid swallowed the page's caption, so
            # attach the page's top section caption to this first grid.
            caption = page_section
            section_used = True
        carried_caption = ""  # only the first grid can consume a carried caption
        pairs.append((grid, caption))
    # if any grids beyond ``n`` exist (rare), keep them uncaptioned.
    for i in range(n, len(grids)):
        if grids[i]:
            pairs.append((grids[i], ""))

    # a caption below the last grid's top, with no grid beneath it on this page,
    # carries to the next page's first new section.
    next_carried = ""
    if tables:
        last_bottom = max(t.bbox[3] for t in tables)
        for cy, ctext in caption_lines:
            if cy > last_bottom and cy not in used_caption_y:
                next_carried = ctext
    return pairs, next_carried


def _page_captions(page) -> list[str]:
    """Return the leading single-cell caption texts on a page (banner aside)."""
    captions: list[str] = []
    for tbl in page.extract_tables():
        for row in tbl:
            if row is None:
                continue
            if _is_banner_cell(row[0]):
                continue
            cap = _is_caption_row(row)
            if cap and cap not in captions:
                captions.append(cap)
            # stop scanning this table once a multi-cell (header/data) row hits.
            if _row_nonempty(row) > 1:
                break
    return captions


def _collect_titles_and_captions(page) -> tuple[list[str], list[str]]:
    """Pull the banner title lines and any table captions from a page."""
    titles: list[str] = []
    captions: list[str] = []
    for tbl in page.extract_tables():
        for row in tbl:
            if row is None:
                continue
            cell = row[0]
            if _is_banner_cell(cell):
                titles.extend(split_banner(cell))
            for value in row:
                text = _clean(value)
                if (
                    text
                    and any(text.startswith(m) for m in _CAPTION_MARKERS)
                    and text not in captions
                ):
                    captions.append(text)
    return titles, captions


# Fixed column set for the S1051 main student results table.
_STUDENT_HEADER = ["CNO", "CANDIDATE FULL NAME", "SEX", "AGGT", "DIV", "POS", "DETAILED SUBJECTS"]


def _row_is_student(cells: list[str]) -> bool:
    """A main student row starts with a ``S<center>-<nnnn>`` candidate number."""
    return bool(cells) and bool(re.match(r"^S\d+-\d+$", cells[0]))


def _compact(row: list[str | None]) -> list[str]:
    """Drop the ``None``/blank padding pdfplumber emits between merged cells."""
    return [_clean(c) for c in row if _clean(c)]


def _extract_s1051(pdf, ir: DocumentIR) -> None:
    """Per-document profile for the S1051 student-list report.

    The page-0 grid merges three logical blocks (banner, the DIVISION
    PERFORMANCE SUMMARY pivot, and the main student results table); pdfplumber
    also repeats fragments of the student header on later pages and appends
    several centre-level summary tables at the end. We split these apart into
    clean, separately-labelled tables so FEAT-004 can render each faithfully.
    """
    # --- pivot (SEX x I/II/III/IV/0) from the top of page 0 ---
    first_grid = _extract_page_tables(pdf.pages[0])[0]
    pivot_rows: list[list[str]] = []
    for row in first_grid:
        cells = _compact(row)
        if not cells:
            continue
        if cells[0] == "SEX" or (
            pivot_rows and cells[0] in {"F", "M", "T"} and len(pivot_rows) < 4
        ):
            pivot_rows.append(cells)
    if pivot_rows:
        pivot = Table(
            caption="DIVISION PERFORMANCE SUMMARY",
            n_cols=len(pivot_rows[0]),
            header_rows=[[HeaderCell(label=lbl, col=i) for i, lbl in enumerate(pivot_rows[0])]],
            body=[r for r in pivot_rows[1:]],
            percent_cells=[[False] * len(pivot_rows[0]) for _ in pivot_rows[1:]],
            raw=pivot_rows,
            kind="pivot",
        )
        ir.tables.append(pivot)

    # --- main student results table (all pages concatenated) ---
    # DETAILED SUBJECTS is the trailing free-text column; everything before it
    # maps to the fixed CNO/NAME/SEX/AGGT/DIV/POS columns.
    student_rows = []
    for page in pdf.pages:
        for grid in _extract_page_tables(page):
            for row in grid:
                cells = _compact(row)
                if not _row_is_student(cells):
                    continue
                fixed = cells[:6]
                detailed = " ".join(cells[6:]) if len(cells) > 6 else ""
                while len(fixed) < 6:
                    fixed.append("")
                student_rows.append(fixed[:6] + [detailed])
    if student_rows:
        student = Table(
            caption="",
            n_cols=len(_STUDENT_HEADER),
            header_rows=[[HeaderCell(label=lbl, col=i) for i, lbl in enumerate(_STUDENT_HEADER)]],
            body=student_rows,
            percent_cells=[[False] * len(_STUDENT_HEADER) for _ in student_rows],
            raw=[list(_STUDENT_HEADER)] + student_rows,
            kind="student-list",
        )
        ir.tables.append(student)

    # --- trailing centre-summary tables (grading, subject performance) ---
    # These live on the last pages and are recovered by the generic engine.
    # Each summary page opens with an ``EXAMINATION CENTRE ...`` heading (e.g.
    # ``EXAMINATION CENTRE OVERALL PERFORMANCE``, ``EXAMINATION CENTRE SUBJECTS
    # GRADING PERFORMANCE SUMMARY``); we carry that heading onto the table so
    # the summary section is labelled rather than rendered caption-less.
    for page in pdf.pages[-2:]:
        caption = _summary_caption(page)
        for grid in _extract_page_tables(page):
            if any(_row_is_student(_compact(r)) for r in grid):
                continue  # already captured as student rows
            table = _table_from_grid(grid, caption=caption, kind="summary")
            if table.body:
                ir.tables.append(table)


# The centre-summary pages of the S1051 report open with one of these headings.
_SUMMARY_CAPTION_RE = re.compile(r"^EXAMINATION CENTRE .+", re.IGNORECASE)


def _summary_caption(page) -> str:
    """Return the ``EXAMINATION CENTRE ...`` heading that titles a summary page.

    The heading is the topmost centred line on the page (``... OVERALL
    PERFORMANCE`` / ``... SUBJECTS GRADING PERFORMANCE SUMMARY``); the
    key-value body rows (``EXAMINATION CENTRE REGION MWANZA`` ...) sit below it.
    """
    for line in _top_lines(page, 92):
        if _SUMMARY_CAPTION_RE.match(line):
            return line
    return ""


def extract_document(stem: str, pdf_path: str, category: str) -> DocumentIR:
    """Extract the full IR for one report document from its reference PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        first = pdf.pages[0]
        page_size = [round(first.width, 2), round(first.height, 2)]
        orientation = "portrait" if stem in PORTRAIT_STEMS else "landscape"
        ir = DocumentIR(
            stem=stem,
            category=category,
            orientation=orientation,
            pages=len(pdf.pages),
            page_size=page_size,
        )
        titles, captions = _collect_titles_and_captions(first)
        # Robust banner recovery: read the top region of page 0 as words so the
        # constant PMO/RALG/MWANZA REGION/REGIONAL FORM TWO... lines + report
        # subtitle are recovered even when pdfplumber does not collapse them
        # into a table cell (which left title_lines empty for some layouts).
        recovered = _recover_banner_lines(first)
        # Prefer the word-recovered banner order, then fold in any extra
        # subtitle text the table-cell scan found; de-duplicate keeping order.
        seen: set[str] = set()
        for line in recovered + titles:
            if line not in seen:
                seen.add(line)
                ir.title_lines.append(line)
        # DIVISION PERFORMANCE SUMMARY is a table caption, not a report title;
        # keep it out of the banner title lines.
        ir.title_lines = [ln for ln in ir.title_lines if ln not in _CAPTION_MARKERS]
        ir.captions = captions

        if category == "student":
            _extract_s1051(pdf, ir)
            return ir

        # Section captions that sit above a header band (in addition to the
        # first-page report subtitle already in title_lines).
        for cap in _page_captions(first):
            if cap not in ir.captions and cap not in ir.title_lines:
                ir.captions.append(cap)

        # Recover ONE caption PER SECTION, not per page. Each grid is matched to
        # the caption line that sits directly above it, so reports that pack
        # several subject sections onto one page (e.g. the SUBJECTWISE rank
        # reports) get every section labelled -- not just the first. A caption
        # stranded at the bottom of a page introduces the first new section on
        # the following page (carried forward).
        page_grids: list[tuple[list[list[str | None]], str]] = []
        carried = ""
        for page in pdf.pages:
            pairs, carried = _page_grids_with_captions(page, carried)
            page_grids.extend(pairs)

    # The first section's caption can be absorbed into the banner ``title_lines``
    # (e.g. ``SCHOOL RANK IN HTM COUNCILWISE`` sits right under the report
    # subtitle on page 0). Once it is attached to the first grid as a section
    # caption, drop it from the banner so it renders as the table's <h3> rather
    # than a report title -- but keep the genuine report subtitle in the banner.
    grid_captions = {section for _, section in page_grids if section}
    ir.title_lines = [ln for ln in ir.title_lines if ln not in grid_captions]

    tables: list[Table] = []
    for grid, section in page_grids:
        table = _table_from_grid(grid, caption=section, kind="table")
        if table.body or table.header_rows:
            tables.append(table)

    ir.tables = _dedup_repeats(tables)
    return ir


def _dedup_repeats(tables: list[Table]) -> list[Table]:
    """Collapse identical repeated tables while keeping distinct sections.

    pdfplumber returns one grid per reference page, and some reports paginate
    the SAME data across pages (e.g. a district table shown again with no new
    section caption). Such a grid is a silent repeat: same header AND identical
    body AND no distinguishing section caption. We drop those. Tables that carry
    a distinct section caption (``DISTRICT PERFORMANCE FOR GOVERNMENT SCHOOLS
    ONLY`` vs ``... OVERALL``) are genuinely different sections and are kept even
    when their body happens to coincide.
    """
    kept: list[Table] = []
    for table in tables:
        dup = False
        for prev in kept:
            same_header = prev.header_rows == table.header_rows
            same_body = prev.body == table.body
            # a repeat is identical structure + data with no NEW caption to
            # distinguish it (blank caption, or the same caption as the match).
            if same_header and same_body and (not table.caption or table.caption == prev.caption):
                dup = True
                break
        if not dup:
            kept.append(table)
    return kept


# ---------------------------------------------------------------------------
# Cross-check against the source pdf2html HTML
# ---------------------------------------------------------------------------
def _html_path_for(stem: str, category: str) -> str:
    if category == "student":
        return os.path.join(DATA_ROOT, f"{stem}.html")
    sub = "council_html" if category == "council" else "region_html"
    return os.path.join(DATA_ROOT, sub, f"{stem}.html")


def _source_html_tokens(html_path: str) -> set[str]:
    """Return the set of text tokens present in the source pdf2html HTML."""
    if BeautifulSoup is None or not os.path.exists(html_path):
        return set()
    with open(html_path, encoding="utf-8") as fh:
        html = fh.read()
    soup = BeautifulSoup(html, "lxml")
    style_text = " ".join(s.get_text() for s in soup.find_all("style"))
    fonts = parse_font_classes(style_text)
    tokens: set[str] = set()
    for page in soup.select("div.page"):
        for run in parse_runs(page, fonts):
            for tok in run.text.split():
                tokens.add(tok)
    return tokens


def crosscheck(ir: DocumentIR, category: str) -> dict:
    """Confirm the recovered IR values also appear in the source HTML text.

    We tokenise every recovered body value and every source-HTML run, then
    report any *significant* IR token (length >= 3, not a lone symbol) that is
    absent from the HTML -- a signal pdfplumber dropped or transposed data.
    """
    html_path = _html_path_for(ir.stem, category)
    src_tokens = _source_html_tokens(html_path)
    if not src_tokens:
        return {"checked": False, "reason": "source HTML unavailable", "missing": []}

    missing: list[str] = []
    checked = 0
    for table in ir.tables:
        for row in table.body:
            for value in row:
                for tok in value.split():
                    tok = tok.strip()
                    if len(tok) < 3 or not re.search(r"[A-Za-z0-9]", tok):
                        continue
                    checked += 1
                    if tok not in src_tokens and tok.rstrip("'\".,") not in src_tokens:
                        missing.append(tok)
    unique_missing = sorted(set(missing))
    return {
        "checked": True,
        "tokens_checked": checked,
        "missing_count": len(unique_missing),
        "missing_sample": unique_missing[:25],
    }


# ---------------------------------------------------------------------------
# Registry + driver
# ---------------------------------------------------------------------------
def documents() -> list[tuple[str, str, str]]:
    """Return ``(stem, pdf_path, category)`` for every unique document."""
    docs: list[tuple[str, str, str]] = [
        (
            "S1051-MKOLANI SECONDARY SCHOOL",
            os.path.join(DATA_ROOT, "S1051-MKOLANI SECONDARY SCHOOL.pdf"),
            "student",
        )
    ]
    for stem in COUNCIL_STEMS:
        docs.append((stem, os.path.join(DATA_ROOT, "council_pdf", f"{stem}.pdf"), "council"))
    for stem in REGION_STEMS:
        docs.append((stem, os.path.join(DATA_ROOT, "region_pdf", f"{stem}.pdf"), "region"))
    return docs


def _ir_to_dict(ir: DocumentIR) -> dict:
    data = asdict(ir)
    return data


def extract_all(out_dir: str = IR_DIR) -> list[str]:
    """Extract every unique document to ``out_dir`` as ``<stem>.json``.

    Also writes a small note for the byte-identical duplicate so reviewers can
    see it was deduped rather than missed.
    """
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    for stem, pdf_path, category in documents():
        ir = extract_document(stem, pdf_path, category)
        ir.crosscheck = crosscheck(ir, category)
        out_path = os.path.join(out_dir, f"{stem}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(_ir_to_dict(ir), fh, indent=2, ensure_ascii=False)
        written.append(out_path)

    for dup, canonical in DUPLICATE_STEMS.items():
        note = {
            "stem": dup,
            "duplicate_of": canonical,
            "note": "Byte-identical to the canonical document (md5 match); deduped.",
        }
        out_path = os.path.join(out_dir, f"{dup}.json")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(note, fh, indent=2, ensure_ascii=False)
        written.append(out_path)
    return written


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    paths = extract_all()
    print(f"Wrote {len(paths)} IR files to {IR_DIR}/")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
