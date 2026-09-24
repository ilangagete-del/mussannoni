"""Turn a recovered, classified :class:`~sars.model.Document` into report data.

This is the bridge from the *presentation* model (geometry, fonts, colours -
everything needed to redraw the PDF) to the *data* schemas in
:mod:`sars.schema`. It walks the classified tables, uses the ``row_kinds`` set
by :mod:`sars.classify` to skip banner / header / total *chrome* rows, and maps
each data row's columns to schema fields using the header labels.

The main report families (school result slip, schools rank / top schools, best
students, subjects rank) get bespoke, typed schemas. Every other family is
captured header-driven into a :class:`~sars.schema.GenericTabularReport`, so no
document is ever left unextracted; the header labels become the field keys.
"""

from __future__ import annotations

import re

from .classify import classify, is_total_text
from .model import Cell, Document, Table
from .reports import DEFAULT_COUNCIL, DEFAULT_REGION, ReportSpec, spec_for
from .schema import (
    BestStudentsReport,
    BestStudentsSection,
    CellStyle,
    DivisionSummaryRow,
    GenderCounts,
    GenericTabularReport,
    PerformanceRow,
    PerformanceTable,
    ReportMeta,
    SchoolRankRow,
    SchoolResultSlip,
    SchoolsRankReport,
    StudentRow,
    SubjectRankRow,
    SubjectResult,
    SubjectsRankReport,
    TabularRow,
    TabularSection,
)

# A ``SUBJECT - 42'D'`` / ``KISW - 'X'`` chunk in the DETAILED SUBJECTS column.
_SUBJECT_CHUNK = re.compile(
    r"([A-Z][A-Z/&.\- ]*?)\s*-\s*(\d+)?\s*'([A-FX])'",
)


# --------------------------------------------------------------------------- #
# Table walking helpers
# --------------------------------------------------------------------------- #
def _rows_map(table: Table) -> dict[int, dict[int, Cell]]:
    """Map row index -> {col index -> cell} for quick lattice lookups."""
    out: dict[int, dict[int, Cell]] = {}
    for cell in table.cells:
        out.setdefault(cell.row, {})[cell.col] = cell
    return out


def _column_headers(table: Table) -> list[str]:
    """Flatten the header band into one label path per physical column.

    Each header cell's text is broadcast across the columns it spans and down
    the rows it spans, so column ``11`` of a schools-rank table resolves to
    ``DIVISION PERFORMANCE / I / F``. Empty segments are dropped.
    """
    n_cols = table.n_cols
    band = max(table.header_rows, 0)
    segments: list[list[str]] = [[] for _ in range(n_cols)]
    for cell in table.cells:
        if cell.row >= band:
            continue
        text = cell.text.strip()
        if not text:
            continue
        for col in range(cell.col, min(cell.col + cell.colspan, n_cols)):
            segments[col].append(text)
    return [" / ".join(seg) for seg in segments]


def _ordered_values(row: dict[int, Cell], n_cols: int) -> list[str]:
    """Values for a row as a list indexed by physical column (blanks kept)."""
    return [row[c].text.strip() if c in row else "" for c in range(n_cols)]


def _leaf_headers(headers: list[str]) -> list[str]:
    """Return only the final segment of each column header path."""
    return [h.split(" / ")[-1] if h else "" for h in headers]


def _total_rows(table: Table) -> dict[str, list[str]]:
    """Collect DATA of every ``total`` row keyed by its printed label.

    The label is CHROME; it is retained purely as the dict key so the numbers
    can later be placed back on the correct summary line. When a total row has
    no obvious label cell, a positional ``total_<row>`` key is used.
    """
    return {label: values for label, values, _s, _p in _total_rows_full(table)}


def _total_rows_full(table: Table):
    """Yield ``(label, values, styles, pitch)`` for every ``total`` row.

    ``styles`` is a per-column list of :class:`CellStyle` aligned with
    ``values`` (blanks default), and ``pitch`` is the row's recovered height in
    points, so the total rows carry the same recovered presentation as the data
    rows. Used by :func:`_total_rows` (values only) and
    :func:`_group_total_styles` (styles + pitch).
    """
    rows = _rows_map(table)
    n_cols = table.n_cols
    out: list[tuple[str, list[str], list[CellStyle], float]] = []
    for r, kind in enumerate(table.row_kinds):
        if kind != "total":
            continue
        row = rows.get(r, {})
        label = ""
        for c in sorted(row):
            text = row[c].text.strip()
            if text and (is_total_text(text) or not _is_number(text)):
                label = text
                break
        key = label or f"total_{r}"
        values = _ordered_values(row, n_cols)
        styles = [_cell_style(row.get(c)) for c in range(n_cols)]
        out.append((key, values, styles, _row_pitch(table, r)))
    return out


_NUM = re.compile(r"^-?[\d,]+(\.\d+)?%?$")


def _is_number(text: str) -> bool:
    return bool(_NUM.match(text.strip()))


# --------------------------------------------------------------------------- #
# Banner / metadata
# --------------------------------------------------------------------------- #
def _banner_lines(doc: Document) -> list[str]:
    """Free text lines (ministry banner + section title) in reading order."""
    lines: list[str] = []
    for page in doc.pages:
        for block in page.blocks:
            if block.text is not None:
                text = block.text.text.strip()
                if text:
                    lines.append(text)
        if lines:
            break  # banner lives on the first page
    return lines


def _build_meta(doc: Document, spec: ReportSpec) -> ReportMeta:
    """Assemble :class:`ReportMeta` from the banner lines and the catalogue."""
    lines = _banner_lines(doc)
    region = DEFAULT_REGION
    council = DEFAULT_COUNCIL if spec.level == "council" else ""
    exam_name = ""
    title = ""
    for line in lines:
        up = line.upper()
        if "REGION" in up and "ADMINISTRATION" not in up and len(line.split()) <= 3:
            region = line.replace("REGION", "").strip().title() or region
        elif "ASSESSMENT RESULTS" in up or "MOCK ASSESSMENT" in up:
            exam_name = line
    # The section title is the last banner line that is not part of the fixed
    # ministry masthead - it names which report this is.
    masthead = {
        "THE PRIME MINISTER'S OFFICE",
        "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
    }
    for line in reversed(lines):
        up = line.upper()
        if up in masthead or "REGION" == up.replace("MWANZA", "").strip():
            continue
        if "ASSESSMENT RESULTS" in up:
            continue
        title = line
        break
    if spec.report_type == "school_result_slip":
        council = council or DEFAULT_COUNCIL
    return ReportMeta(
        name=doc.name,
        report_type=spec.report_type,
        level=spec.level,
        variant=spec.variant,
        region=region,
        council=council,
        exam_name=exam_name,
        title=title,
    )


# --------------------------------------------------------------------------- #
# Per-family extractors
# --------------------------------------------------------------------------- #
def _iter_data_rows(table: Table):
    """Yield ``(row_index, {col: cell})`` for every ``data`` row of a table."""
    rows = _rows_map(table)
    for r, kind in enumerate(table.row_kinds):
        if kind == "data":
            yield r, rows.get(r, {})


def _tables(doc: Document) -> list[Table]:
    """All classified tables in the document, in reading order."""
    out: list[Table] = []
    for page in doc.pages:
        for block in page.blocks:
            if block.table is not None:
                out.append(block.table)
    return out


def _cell(row: dict[int, Cell], col: int) -> str:
    cell = row.get(col)
    return cell.text.strip() if cell is not None else ""


def _cell_style(cell: Cell | None) -> CellStyle:
    """Snapshot the recovered presentation of *cell* as a :class:`CellStyle`.

    Mirrors the meaningful subset of :class:`sars.model.Style` the conversion
    path already recovered for this cell (font family / size / weight / slant,
    text colour, cell *background* fill, alignment, rotation), so the style can
    travel with the value into the data schema. A missing cell yields a default
    :class:`CellStyle`, which renders exactly as the old hardcoded path did.

    The recovered ``background`` fill is captured verbatim; for competency cells
    this means the source colour takes precedence over the deterministic
    :func:`sars.competency.background_for` fallback, matching the conversion
    path's rule that the recovered colour always wins.
    """
    if cell is None:
        return CellStyle()
    st = cell.style
    return CellStyle(
        family=st.family,
        size_pt=st.size_pt,
        bold=st.bold,
        italic=st.italic,
        color=st.color,
        background=st.background,
        align=st.align,
        rotation=st.rotation,
    )


def _row_styles(row: dict[int, Cell], n_cols: int) -> dict[str, CellStyle]:
    """Recovered style for every occupied cell of a row, keyed by column index.

    Only columns that actually carry a cell are recorded (blanks default when
    looked up), keeping the JSON lean while every emitted ``<td>`` can still
    resolve the exact style recovered for its column.
    """
    out: dict[str, CellStyle] = {}
    for c in range(n_cols):
        cell = row.get(c)
        if cell is not None:
            out[str(c)] = _cell_style(cell)
    return out


def _row_pitch(table: Table, row_index: int) -> float:
    """Recovered pitch (true row height in points) of a lattice row.

    Returns ``0.0`` when the row index is out of range, so fresh data with no
    geometry simply carries the default and renders as before.
    """
    heights = table.row_heights()
    if 0 <= row_index < len(heights):
        return round(heights[row_index], 3)
    return 0.0


def _parse_subjects(text: str) -> list[SubjectResult]:
    """Parse a ``DETAILED SUBJECTS`` string into structured subject results."""
    out: list[SubjectResult] = []
    for m in _SUBJECT_CHUNK.finditer(text):
        subject = m.group(1).strip()
        mark = (m.group(2) or "").strip()
        grade = m.group(3).strip()
        if subject:
            out.append(SubjectResult(subject=subject, mark=mark, grade=grade))
    return out


_CANDIDATE_ID = re.compile(r"^[A-Z]\d{3,6}-\d{1,5}$", re.IGNORECASE)


def _candidate_col(row: dict[int, Cell]) -> int | None:
    """Column holding a ``S1051-0001`` candidate id in this data row, if any."""
    for c in sorted(row):
        if _CANDIDATE_ID.match(row[c].text.strip()):
            return c
    return None


_SEX_TOKENS = {"F", "M"}


def _student_from_row(
    row: dict[int, Cell], base: int, table: Table | None = None, row_index: int = -1
) -> StudentRow:
    """Build a :class:`StudentRow` from a candidate row whose id is at ``base``.

    The slip's candidate columns run ``CNO, NAME, SEX, AGGT, DIV, POS, DETAILED
    SUBJECTS``. The ``NAME`` cell may span one or two lattice columns depending
    on the page, so the ``SEX`` column is located dynamically (the first single
    ``F`` / ``M`` after the id); the remaining fields follow it in fixed order.
    ``DETAILED SUBJECTS`` is taken as the last non-empty cell so its own
    column-span never matters.
    """
    cols = sorted(c for c in row if c >= base)
    name = _cell(row, base + 1)
    sex_col = None
    for c in cols:
        if c <= base:
            continue
        if _cell(row, c).upper() in _SEX_TOKENS:
            sex_col = c
            break
    detailed = ""
    for c in reversed(cols):
        text = _cell(row, c)
        if "'" in text or " - " in text:
            detailed = text
            break
    n_cols = table.n_cols if table is not None else (max(row) + 1 if row else 0)
    styles = _row_styles(row, n_cols)
    pitch = _row_pitch(table, row_index) if table is not None else 0.0
    if sex_col is None:
        return StudentRow(
            cno=_cell(row, base),
            name=name,
            detailed_subjects=detailed,
            subjects=_parse_subjects(detailed),
            styles=styles,
            pitch=pitch,
        )
    return StudentRow(
        cno=_cell(row, base),
        name=name,
        sex=_cell(row, sex_col),
        aggregate=_cell(row, sex_col + 1),
        division=_cell(row, sex_col + 2),
        position=_cell(row, sex_col + 3),
        detailed_subjects=detailed,
        subjects=_parse_subjects(detailed),
        styles=styles,
        pitch=pitch,
    )


def _extract_school_slip(doc: Document, meta: ReportMeta) -> SchoolResultSlip:
    slip = SchoolResultSlip(meta=meta)
    # The masthead includes a ``S1051 - MKOLANI SECONDARY SCHOOL`` line.
    for line in _banner_lines(doc):
        m = re.match(r"^\s*([A-Z]\d{3,6})\s*-\s*(.+)$", line)
        if m:
            slip.centre_no = m.group(1)
            slip.school_name = m.group(2).strip()
            break

    for table in _tables(doc):
        headers = _leaf_headers(_column_headers(table))
        upper = [h.upper() for h in headers]
        joined = " ".join(upper)
        is_candidate = ("CNO" in upper) or ("CANDIDATE FULL NAME" in joined)
        # A continuation page has no header but its data rows carry candidate ids.
        if not is_candidate:
            for _, row in _iter_data_rows(table):
                if _candidate_col(row) is not None:
                    is_candidate = True
                break

        if is_candidate:
            for r, row in _iter_data_rows(table):
                base = _candidate_col(row)
                if base is None:
                    continue
                slip.students.append(_student_from_row(row, base, table, r))
        elif "SEX" in upper and any(h in ("I", "II", "III", "IV", "0") for h in upper):
            div_labels = [h for h in headers[1:] if h]
            for r, row in _iter_data_rows(table):
                sex = _cell(row, 0)
                divisions = {label: _cell(row, i + 1) for i, label in enumerate(div_labels)}
                styles: dict[str, CellStyle] = {}
                if 0 in row:
                    styles["sex"] = _cell_style(row.get(0))
                for i, label in enumerate(div_labels):
                    if (i + 1) in row:
                        styles[label] = _cell_style(row.get(i + 1))
                slip.division_summary.append(
                    DivisionSummaryRow(
                        sex=sex, divisions=divisions, styles=styles, pitch=_row_pitch(table, r)
                    )
                )
        else:
            # School / subject performance summaries below the candidate list.
            perf = _performance_table(table)
            if perf is not None:
                slip.performance.append(perf)
    return slip


def _normalise_header_paths(headers: list[str]) -> list[str]:
    """Give sibling columns a consistent group prefix.

    The header flattener occasionally records a group heading on only some of
    the columns it spans (e.g. ``NUMBER OF CANDIDATES / REGISTERED / T`` on one
    column but ``REGISTERED / F`` on its neighbours). When the header band is
    rebuilt for the template this makes the group label appear twice. Here a
    sub-group label that is a proper suffix-prefix of a fuller sibling path
    inherits that sibling's missing leading segment, so the group heading is
    emitted exactly once - matching the reference token count.
    """
    split = [h.split(" / ") if h else [] for h in headers]
    out: list[list[str]] = [list(s) for s in split]
    for i, parts in enumerate(out):
        if len(parts) < 2:
            continue
        head = parts[0]
        # Find a sibling whose path contains ``head`` as a non-leading segment;
        # if so, prepend the segment(s) that precede ``head`` there.
        for other in split:
            if len(other) > len(parts) and head in other[1:]:
                idx = other.index(head)
                prefix = other[:idx]
                if prefix and out[i][:1] != prefix[-1:]:
                    out[i] = prefix + out[i]
                break
    return [" / ".join(p) for p in out]


def _full_capture(table: Table) -> PerformanceTable | None:
    """Capture a whole small table (header band + every body/total row).

    Unlike :func:`_performance_table` this keeps *all* non-header rows (so a
    ``% PASS`` total row survives) and keys each row's values by *column index*
    (as a string), because summary blocks repeat leaf labels (many ``F`` / ``M``
    / ``T``) that would collide in a header-keyed dict. The flattened header
    paths are still stored in ``column_headers`` so the template can rebuild the
    grouped header band and place the values back by column.
    """
    headers = _normalise_header_paths(_column_headers(table))
    rows_map = _rows_map(table)
    band = max(table.header_rows, 0)
    body: list[PerformanceRow] = []
    for r in range(table.n_rows):
        if r < band:
            continue
        row = rows_map.get(r, {})
        values: dict[str, str] = {}
        styles: dict[str, CellStyle] = {}
        for c, cell in row.items():
            text = cell.text.strip()
            if text:
                # Encode span so the template can re-merge cells: ``col`` -> text
                # and ``col.span`` -> colspan when the cell spans >1 column.
                values[str(c)] = text
                styles[str(c)] = _cell_style(cell)
                if cell.colspan > 1:
                    values[f"{c}.span"] = str(cell.colspan)
        if values:
            body.append(PerformanceRow(values=values, styles=styles, pitch=_row_pitch(table, r)))
    if not body:
        return None
    return PerformanceTable(column_headers=headers, rows=body)


def _performance_table(table: Table) -> PerformanceTable | None:
    """Capture a slip performance-summary table header-driven, or ``None``."""
    headers = _column_headers(table)
    rows: list[PerformanceRow] = []
    n_cols = table.n_cols
    for r, row in _iter_data_rows(table):
        values: dict[str, str] = {}
        styles: dict[str, CellStyle] = {}
        for col in range(n_cols):
            key = headers[col] if col < len(headers) and headers[col] else f"col_{col}"
            text = _cell(row, col)
            if text:
                values[key] = text
                styles[key] = _cell_style(row.get(col))
        if values:
            rows.append(PerformanceRow(values=values, styles=styles, pitch=_row_pitch(table, r)))
    if not rows:
        return None
    return PerformanceTable(column_headers=headers, rows=rows)


def _extract_best_students(doc: Document, meta: ReportMeta) -> BestStudentsReport:
    report = BestStudentsReport(meta=meta)

    # These reports are a sequence of titled blocks - one per subject on a
    # subjectwise list, overall / female / male on an overall one - and the
    # heading is printed as a free-standing line *above* each block's table
    # rather than as a row inside it, so the titled-section walk is what keeps
    # each heading with its own candidates.
    for section_title, tables in _titled_table_sections(doc, meta):
        current = BestStudentsSection(title=section_title or meta.title)
        for table in tables:
            rows = _rows_map(table)
            # Column positions come from this table's own header band. The family
            # spans two genuinely different layouts (an overall list carrying
            # AGGT / DIVISION / DETAILED SUBJECTS, and a subjectwise list carrying
            # MARKS / GRADE / COMPETENCY LEVEL), and the council and region
            # variants of each differ again by a leading S/NO. and COUNCIL
            # column. Reading the header per table covers all four.
            idx = _student_columns(_column_headers(table))

            for r, kind in enumerate(table.row_kinds):
                row = rows.get(r, {})
                if kind == "banner":
                    # A banner row inside the table opens a further block.
                    if current.students:
                        report.sections.append(current)
                    title = " ".join(c.text for c in row.values() if c.text).strip()
                    current = BestStudentsSection(title=title or section_title)
                    continue
                if kind != "data":
                    continue
                student = _student_row(row, idx, table, r)
                # ``None`` is a repeated in-table header row, or a row with no
                # identifying value at all.
                if student is not None:
                    current.students.append(student)

        if current.students:
            report.sections.append(current)
    return report


#: Leaf header names for each :class:`StudentRow` field, in match priority.
_STUDENT_COLUMNS: dict[str, tuple[str, ...]] = {
    "sno": ("S/NO.", "S/NO", "SNO", "S/N"),
    "council": ("COUNCIL",),
    "cno": ("C/NO", "CNO", "CAND NO", "CANDIDATE NO"),
    "id_no": ("ID NO.", "ID NO", "IDNO"),
    "school_name": ("SCHOOL NAME", "SCHOOL"),
    "category": ("CATEGORY", "OWNERSHIP"),
    "name": ("CANDIDATE FULL  NAME", "CANDIDATE FULL NAME", "CANDIDATE NAME", "NAME"),
    "sex": ("SEX",),
    "aggregate": ("AGGT", "AGGREGATE"),
    "division": ("DIVISION", "DIV"),
    "marks": ("MARKS", "MARK"),
    "grade": ("GRADE",),
    "position": ("POSITION", "POS"),
    "competency": ("COMPETENCY LEVEL", "COMPENTENCY LEVEL", "COMPETENCY"),
    "detailed_subjects": ("DETAILED SUBJECTS", "DETAILED SUBJECT"),
}


def _student_columns(headers: list[str]) -> dict[str, int]:
    """Map :class:`StudentRow` field -> column index, from a header band.

    Only fields the table actually has are present, so the same routine serves
    the overall and subjectwise layouts at both council and region level.
    """
    leaves = [h.upper() for h in _leaf_headers(headers)]
    found: dict[str, int] = {}
    taken: set[int] = set()
    for field_name, names in _STUDENT_COLUMNS.items():
        for want in names:
            if want in leaves:
                col = leaves.index(want)
                if col in taken:
                    continue
                found[field_name] = col
                taken.add(col)
                break
    return found


def _student_row(
    row: dict[int, Cell], idx: dict[str, int], table: Table | None = None, row_index: int = -1
) -> StudentRow | None:
    """Build a :class:`StudentRow` from one data row, or ``None`` to skip it.

    A row is skipped when it is a repeated header band rendered as data, or when
    it carries no identifying value (no candidate number, id or name).
    """
    values = {name: _cell(row, col) for name, col in idx.items()}

    # A repeated in-table header row echoes its own column captions.
    for field_name, names in _STUDENT_COLUMNS.items():
        text = values.get(field_name, "").upper()
        if text and text in {n.upper() for n in names}:
            return None

    if not any(values.get(k) for k in ("cno", "id_no", "name")):
        return None

    detailed = values.get("detailed_subjects", "")
    student = StudentRow(
        cno=values.get("cno", ""),
        name=values.get("name", ""),
        sex=values.get("sex", ""),
        aggregate=values.get("aggregate", ""),
        division=values.get("division", ""),
        position=values.get("position", ""),
        school_name=values.get("school_name", ""),
        detailed_subjects=detailed,
        subjects=_parse_subjects(detailed),
        sno=values.get("sno", ""),
        council=values.get("council", ""),
        id_no=values.get("id_no", ""),
        category=values.get("category", ""),
        marks=values.get("marks", ""),
        grade=values.get("grade", ""),
        competency=values.get("competency", ""),
    )
    # Carry the recovered presentation keyed by the StudentRow field name, so
    # each field's cell keeps its own font / colour / background (the competency
    # cell's recovered fill thus takes precedence over the derived colour).
    student.styles = {name: _cell_style(row.get(col)) for name, col in idx.items() if col in row}
    student.pitch = _row_pitch(table, row_index) if table is not None else 0.0
    return student


def _index_of(headers: list[str], *names: str) -> int | None:
    """First column whose leaf header matches one of ``names`` (case-insensitive)."""
    leaves = [h.upper() for h in _leaf_headers(headers)]
    for name in names:
        if name.upper() in leaves:
            return leaves.index(name.upper())
    return None


def _extract_schools_rank(doc: Document, meta: ReportMeta) -> SchoolsRankReport:
    report = SchoolsRankReport(meta=meta)
    group = _main_table_group(doc)
    if not group:
        return report
    # The SUMMARY PERFORMANCE block is a small table on the first page, distinct
    # from the main ranked table; capture it in full (header + aggregate row +
    # the % PASS row) so the whole report - not just the ranks - can be
    # regenerated from data alone by the template path.
    for table in _tables(doc):
        if table in group:
            continue
        joined = " ".join(c.text.upper() for c in table.cells)
        if "SUMMARY" in joined or "% PASS" in joined or "NO. OF SCHOOLS" in joined:
            perf = _full_capture(table)
            if perf is not None:
                report.summary.append(perf)
                break
    headers = _group_headers(group)
    leaves = _leaf_headers(headers)

    def col(*names: str) -> int | None:
        return _index_of(headers, *names)

    i_sno = col("S/NO.", "S/NO", "SNO", "S/N")
    i_ward = col("WARD")
    i_council = col("COUNCIL")
    i_school = col("SCHOOL NAME", "SCHOOL")
    i_own = col("OWNERSHIP", "CATEGORY")
    i_gpa = col("GPA")
    i_comp = col("COMPETENCY LEVEL", "COMPETENCY", "COMPENTENCY LEVEL")
    i_crank = col("C/RANK")
    i_rrank = col("R/RANK")

    # Group the F/M/T (and %) columns under their parent header segment.
    groups = _fmt_groups(headers)

    n_cols = _group_cols(group)
    for table, r, row in _group_data_rows_ctx(group):
        rank_row = SchoolRankRow(
            sno=_cell(row, i_sno) if i_sno is not None else "",
            ward=_cell(row, i_ward) if i_ward is not None else "",
            council=_cell(row, i_council) if i_council is not None else "",
            school_name=_cell(row, i_school) if i_school is not None else "",
            ownership=_cell(row, i_own) if i_own is not None else "",
            gpa=_cell(row, i_gpa) if i_gpa is not None else "",
            competency=_cell(row, i_comp) if i_comp is not None else "",
            council_rank=_cell(row, i_crank) if i_crank is not None else "",
            regional_rank=_cell(row, i_rrank) if i_rrank is not None else "",
        )
        reg = groups.get("REGISTERED")
        if reg:
            rank_row.registered = _gender(row, reg)
        sat = groups.get("SAT")
        if sat:
            rank_row.sat = _gender(row, sat)
            pct = sat.get("%")
            if pct is not None:
                rank_row.sat_pct = _cell(row, pct)
        rank_row.division = _division_map(row, headers, leaves)
        rank_row.styles = _row_styles(row, n_cols)
        rank_row.pitch = _row_pitch(table, r)
        report.rows.append(rank_row)

    report.totals = _group_totals(group)
    report.total_styles, report.total_pitch = _group_total_styles(group, n_cols)
    report.column_headers = leaves
    return report


def _fmt_groups(headers: list[str]) -> dict[str, dict[str, int]]:
    """Map each header group (parent segment) -> {F/M/T/%: column index}."""
    groups: dict[str, dict[str, int]] = {}
    for col, path in enumerate(headers):
        if not path:
            continue
        parts = path.split(" / ")
        leaf = parts[-1]
        parent = parts[-2] if len(parts) >= 2 else ""
        if leaf in ("F", "M", "T", "%"):
            groups.setdefault(parent, {})[leaf] = col
    return groups


def _gender(row: dict[int, Cell], group: dict[str, int]) -> GenderCounts:
    return GenderCounts(
        f=_cell(row, group["F"]) if "F" in group else "",
        m=_cell(row, group["M"]) if "M" in group else "",
        t=_cell(row, group["T"]) if "T" in group else "",
    )


_DIVISION_LABELS = ("I", "II", "III", "IV", "0", "I-III", "I-IV")


def _division_map(row: dict[int, Cell], headers: list[str], leaves: list[str]) -> dict:
    """Extract the DIVISION PERFORMANCE block into ``{label: {f,m,t}, label%}``."""
    groups = _fmt_groups(headers)
    out: dict = {}
    for label in _DIVISION_LABELS:
        grp = groups.get(label)
        if grp:
            out[label] = {
                "f": _cell(row, grp["F"]) if "F" in grp else "",
                "m": _cell(row, grp["M"]) if "M" in grp else "",
                "t": _cell(row, grp["T"]) if "T" in grp else "",
            }
            if "%" in grp:
                out[f"{label}%"] = _cell(row, grp["%"])
    return out


def _extract_subjects_rank(doc: Document, meta: ReportMeta) -> SubjectsRankReport:
    report = SubjectsRankReport(meta=meta)
    group = _main_table_group(doc)
    if not group:
        return report
    headers = _leaf_headers(_group_headers(group))

    def col(*names: str) -> int | None:
        up = [h.upper() for h in headers]
        for name in names:
            if name.upper() in up:
                return up.index(name.upper())
        return None

    i_sno = col("S/NO.", "S/NO", "SNO")
    i_subject = col("SUBJECT NAME", "SUBJECT")
    i_gpa = col("GPA")
    i_comp = col("COMPETENCY LEVEL", "COMPETENCY", "COMPENTENCY LEVEL")
    i_rank = col("RANK", "R/RANK", "C/RANK")
    grade_cols = {
        label: col(label)
        for label in ("A", "B", "C", "D", "F", "TOTAL", "A-C", "%A-C", "A-D", "%A-D")
    }

    n_cols = _group_cols(group)
    for table, r, row in _group_data_rows_ctx(group):
        grades = {label: _cell(row, idx) for label, idx in grade_cols.items() if idx is not None}
        report.rows.append(
            SubjectRankRow(
                sno=_cell(row, i_sno) if i_sno is not None else "",
                subject_name=_cell(row, i_subject) if i_subject is not None else "",
                grades=grades,
                gpa=_cell(row, i_gpa) if i_gpa is not None else "",
                competency=_cell(row, i_comp) if i_comp is not None else "",
                rank=_cell(row, i_rank) if i_rank is not None else "",
                styles=_row_styles(row, n_cols),
                pitch=_row_pitch(table, r),
            )
        )
    report.totals = _group_totals(group)
    report.total_styles, report.total_pitch = _group_total_styles(group, n_cols)
    report.column_headers = headers
    return report


def _extract_generic(doc: Document, meta: ReportMeta) -> GenericTabularReport:
    report = GenericTabularReport(meta=meta)

    # A generic report may print several distinct table blocks, and those blocks
    # need not share a column count (the district report splits into a 37-column
    # and a 34-column block) nor a meaning (all schools, then government, then
    # private, each closed by its own TOTAL row; or one block per subject on the
    # subjectwise school ranks). Capturing only one would silently drop the rest,
    # so every block becomes a section, carrying the heading printed above it.
    for block, title in _generic_blocks(doc, meta):
        headers = _group_headers(block)
        n_cols = block[0].n_cols
        group_cols = _group_cols(block)
        block_totals = _group_totals(block)
        total_styles, total_pitch = _group_total_styles(block, group_cols)
        section = TabularSection(
            column_headers=headers,
            totals=block_totals,
            total_styles=total_styles,
            total_pitch=total_pitch,
            title=title,
        )
        group = block
        for table, r, row in _group_data_rows_ctx(group):
            values: dict[str, str] = {}
            styles: dict[str, CellStyle] = {}
            for col in range(n_cols):
                key = headers[col] if col < len(headers) and headers[col] else f"col_{col}"
                text = _cell(row, col)
                if text:
                    values[key] = text
                    styles[key] = _cell_style(row.get(col))
            if values:
                section.rows.append(
                    TabularRow(values=values, styles=styles, pitch=_row_pitch(table, r))
                )
        if section.rows or section.totals:
            report.sections.append(section)

    if report.sections:
        main = report.sections[0]
        report.column_headers = main.column_headers
        report.rows = main.rows
        report.totals = main.totals
        report.total_styles = main.total_styles
        report.total_pitch = main.total_pitch
    return report


def _largest_table(doc: Document) -> Table | None:
    """The document's main results table (most data rows).

    Kept for callers that only need a single representative table; the
    data extractors use :func:`_main_table_group` so that a report split
    across pages is captured in full.
    """
    group = _main_table_group(doc)
    return group[0] if group else None


def _data_row_count(table: Table) -> int:
    return sum(1 for k in table.row_kinds if k == "data")


def _main_table_group(doc: Document) -> list[Table]:
    """The main results table *and its continuation tables*, in reading order.

    A report longer than one page is drawn as one table per page: the first
    carries the full stacked header band, and each continuation repeats a
    reduced header and then goes on with the data. They all share the same
    column count, because they are the same logical table.

    Selecting a single table here (previously the one with the most data rows)
    silently dropped every continuation page *and* tended to pick a
    continuation, whose repeated header band does not resolve to usable leaf
    names - so the column mapping failed as well. Grouping by column count and
    taking the group with the most data rows keeps the whole report together.
    """
    groups = _table_groups(doc)
    return groups[0] if groups else []


def _table_groups(doc: Document) -> list[list[Table]]:
    """Every table group in the document, richest first.

    Tables are grouped by column count - the signature of one logical table
    continued across pages - and the groups are ordered by how much data they
    carry, so ``[0]`` is the main block and the rest are the report's further
    blocks in descending significance.
    """
    tables = [t for t in _tables(doc) if t.n_cols > 0]
    by_cols: dict[int, list[Table]] = {}
    for table in tables:
        by_cols.setdefault(table.n_cols, []).append(table)
    groups = list(by_cols.values())
    groups.sort(key=lambda g: (sum(_data_row_count(t) for t in g), len(g)), reverse=True)
    return groups


def _group_headers(group: list[Table]) -> list[str]:
    """Column header paths for a table *group*.

    The continuation pages repeat a reduced header band, so the richest header
    in the group - the one resolving the most distinct non-empty leaf names - is
    the authoritative one. That is normally the first page's table.
    """
    best: list[str] = []
    best_score = -1
    for table in group:
        headers = _column_headers(table)
        score = len({h for h in _leaf_headers(headers) if h})
        if score > best_score:
            best_score = score
            best = headers
    return best


def _group_cols(group: list[Table]) -> int:
    """The physical column count of a table *group* (its widest table)."""
    return max((t.n_cols for t in group), default=0)


def _group_data_rows(group: list[Table]):
    """Yield ``{col: cell}`` for every data row across a table *group*."""
    for table in group:
        for _, row in _iter_data_rows(table):
            yield row


def _group_data_rows_ctx(group: list[Table]):
    """Yield ``(table, row_index, {col: cell})`` for every data row of a group.

    Same walk as :func:`_group_data_rows`, but also hands back the owning table
    and lattice row index so the caller can recover the row's geometry
    (:func:`_row_pitch`) alongside its cell styles.
    """
    for table in group:
        for r, row in _iter_data_rows(table):
            yield table, r, row


def _group_totals(group: list[Table]) -> dict[str, list[str]]:
    """Merge the total/summary rows found anywhere in a table *group*.

    Several tables in one group can each carry their own ``TOTAL`` row holding
    genuinely different figures (the district report totals all schools, then
    government, then private). Keeping only the first would discard the rest, so
    a repeated label is disambiguated with an ordinal suffix - ``TOTAL``,
    ``TOTAL (2)``, ``TOTAL (3)`` - preserving every row's data.
    """
    merged: dict[str, list[str]] = {}
    for table in group:
        for label, values in _total_rows(table).items():
            if label not in merged:
                merged[label] = values
                continue
            if any(existing == values for existing in merged.values()):
                continue  # an identical row repeated as chrome, not new data
            n = 2
            while f"{label} ({n})" in merged:
                n += 1
            merged[f"{label} ({n})"] = values
    return merged


def _group_total_styles(
    group: list[Table], n_cols: int
) -> tuple[dict[str, list[CellStyle]], dict[str, float]]:
    """Recovered style + pitch for each merged total row of a table *group*.

    Mirrors :func:`_group_totals`' label keying and ordinal disambiguation so
    the returned dicts are keyed by exactly the same labels, letting the
    template look up the recovered presentation of every total cell. Each style
    list is padded / trimmed to ``n_cols`` so it aligns with the table's columns
    even when a continuation total row has a different width.
    """
    styles: dict[str, list[CellStyle]] = {}
    pitch: dict[str, float] = {}
    values_by_label: dict[str, list[str]] = {}
    for table in group:
        for label, values, row_styles, row_pitch in _total_rows_full(table):
            padded = (row_styles + [CellStyle()] * n_cols)[:n_cols]
            if label not in values_by_label:
                values_by_label[label] = values
                styles[label] = padded
                pitch[label] = row_pitch
                continue
            if any(existing == values for existing in values_by_label.values()):
                continue  # an identical row repeated as chrome, not new data
            n = 2
            while f"{label} ({n})" in values_by_label:
                n += 1
            key = f"{label} ({n})"
            values_by_label[key] = values
            styles[key] = padded
            pitch[key] = row_pitch
    return styles, pitch


#: Report-level chrome lines that are never a *section* title. Matched after
#: upper-casing and whitespace collapsing.
_CHROME_LINES: frozenset[str] = frozenset(
    {
        "THE PRIME MINISTER'S OFFICE",
        "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
        "PRESIDENT'S OFFICE",
    }
)


def _norm_line(text: str) -> str:
    return " ".join((text or "").upper().split())


def _is_section_title(text: str, meta: ReportMeta) -> bool:
    """True when a free-standing text line names a *block* of the report.

    The reports print each block's heading as a line above its table ("TOP TEN
    BEST STUDENTS IN HTM SUBJECT DISTRICTWISE"). The masthead, the region line,
    the exam name and the report's own title are report-level chrome, not block
    headings, so they are excluded.
    """
    line = _norm_line(text)
    if len(line) < 4:
        return False
    if line in _CHROME_LINES:
        return False
    for chrome in (meta.title, meta.exam_name, meta.name):
        if chrome and _norm_line(chrome) == line:
            return False
    region = _norm_line(meta.region)
    if region and line in (region, f"{region} REGION"):
        return False
    council = _norm_line(meta.council)
    if council and line == council:
        return False
    return True


def _titled_table_sections(doc: Document, meta: ReportMeta) -> list[tuple[str, list[Table]]]:
    """Group the document's tables into ``(title, tables)`` sections.

    Walks page blocks in reading order. A free-standing text line that names a
    block (see :func:`_is_section_title`) opens a new section; each table then
    joins the section currently open. Reports that print no such headings yield a
    single untitled section holding every table, which is the continuation case.
    """
    sections: list[tuple[str, list[Table]]] = []
    current_title = ""
    current: list[Table] = []

    for page in doc.pages:
        for block in page.blocks:
            if block.table is not None:
                current.append(block.table)
            elif block.text is not None and _is_section_title(block.text.text, meta):
                if current:
                    sections.append((current_title, current))
                    current = []
                current_title = block.text.text.strip()

    if current:
        sections.append((current_title, current))
    return sections


def _generic_blocks(doc: Document, meta: ReportMeta) -> list[tuple[list[Table], str]]:
    """Table blocks of a generic report, each with the heading printed above it.

    Sections named by a free-standing heading (one per subject on the subjectwise
    school ranks) are split on those headings. Within an untitled run the tables
    are split further by :func:`_table_blocks`, which separates blocks closed by
    their own ``TOTAL`` row from mere continuation pages.
    """
    out: list[tuple[list[Table], str]] = []
    for title, tables in _titled_table_sections(doc, meta):
        if title:
            out.append((tables, title))
            continue
        for block in _split_blocks(tables):
            out.append((block, _block_title(block)))
    return out


def _block_title(block: list[Table]) -> str:
    """The heading a table block prints above its header band, if any.

    Blocks that split a report by ownership or scope name themselves in a banner
    row ("... FOR PRIVATE SCHOOLS"). That heading is the only thing telling the
    blocks apart, so it is captured as the section title.
    """
    for table in block:
        rows = _rows_map(table)
        for r, kind in enumerate(table.row_kinds):
            if kind != "banner":
                continue
            text = " ".join(c.text for c in rows.get(r, {}).values() if c.text).strip()
            if text:
                return text
    return ""


def _table_blocks(doc: Document) -> list[list[Table]]:
    """Split the document's tables into logical blocks, in reading order.

    Two different things look alike at the table level, and telling them apart
    is what keeps both kinds of report intact:

    * a long report *continued* across pages - each page's table carries no
      total row, and the final one closes the report with it; and
    * a report made of several *distinct* blocks that happen to share a column
      count - the district report prints an all-schools block, then a government
      block, then a private one, each closed by its own ``TOTAL`` row.

    A table ending in a total row therefore completes its block; a table without
    one is a continuation and accumulates into the next. A change of column count
    also starts a new block, since that is a different table shape.
    """
    return _split_blocks(_tables(doc))


def _split_blocks(tables: list[Table]) -> list[list[Table]]:
    """Split a run of tables into logical blocks (see :func:`_table_blocks`)."""
    blocks: list[list[Table]] = []
    current: list[Table] = []
    for table in tables:
        if table.n_cols <= 0:
            continue
        if current and table.n_cols != current[-1].n_cols:
            blocks.append(current)
            current = []
        current.append(table)
        if any(kind == "total" for kind in table.row_kinds):
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


_EXTRACTORS = {
    "school_result_slip": _extract_school_slip,
    "best_students": _extract_best_students,
    "schools_rank": _extract_schools_rank,
    "top_schools": _extract_schools_rank,
    "subjects_rank": _extract_subjects_rank,
}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def ensure_classified(doc: Document) -> Document:
    """Classify every table in *doc* if it has not been classified yet."""
    for page in doc.pages:
        for block in page.blocks:
            if block.table is not None and not block.table.row_kinds:
                classify(block.table)
    return doc


def extract_report(doc: Document, name: str | None = None):
    """Extract the appropriate schema instance from a recovered document.

    ``doc`` may be freshly extracted; tables are classified on demand. The
    report type is looked up from the catalogue by ``name`` (defaulting to
    ``doc.name``), and the matching family extractor is used - falling back to
    the generic header-driven extractor for any type without a bespoke one.
    """
    ensure_classified(doc)
    spec = spec_for(name or doc.name)
    meta = _build_meta(doc, spec)
    extractor = _EXTRACTORS.get(spec.report_type, _extract_generic)
    return extractor(doc, meta)
