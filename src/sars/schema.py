"""Report data schemas: the *data* recovered from a report, minus the chrome.

A rendered Mwanza mock report is made of two very different things:

* **chrome** - fixed text that is identical across every instance of a report
  type: the ministry banner (``THE PRIME MINISTER'S OFFICE`` ...), the column
  headings (``NUMBER OF CANDIDATES`` -> ``REGISTERED`` -> ``F`` / ``M`` / ``T``),
  and the *labels* of aggregate rows (``TOTAL``, ``% PASS``). This belongs in a
  template (FEAT-004), not in the data.
* **data** - everything that varies from one report to the next: the region and
  council names, the exam name, the school / student / subject rows, the GPA and
  competency values, the ranks, and the *numbers* on the summary rows.

The dataclasses below capture only the data. Each is a plain
:func:`dataclasses.dataclass`, so :func:`dataclasses.asdict` + :func:`json.dumps`
serialises it losslessly and :func:`from_dict` reconstructs it - see
:func:`to_json` / :func:`from_json`.

**DATA IS DATA, NOT STYLES.** The schema carries only the report's *data*
(figures, names, ranks, counts, GPA, competency *labels*) and its *structure*
(column-header label paths, colspan/rowspan grouping, section titles, and which
rows are totals). Presentation - font family / size / weight / slant, text
colour, cell background fill, alignment, row pitch - is **not** data and is
never stored here; it belongs to each report type's own self-contained
template. The competency *colour* in particular is intentionally **not** stored:
it is a deterministic function of the competency label / GPA
(:mod:`sars.competency`), computed at render time, so only the label and GPA are
data.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any


# --------------------------------------------------------------------------- #
# Shared value objects
# --------------------------------------------------------------------------- #
@dataclass
class ReportMeta:
    """Identifying data shared by every report (no fixed chrome)."""

    #: Source document name this data was extracted from.
    name: str
    #: Report-type family id from :mod:`sars.reports` (e.g. ``schools_rank``).
    report_type: str
    #: Hierarchy level: ``school`` | ``council`` | ``region``.
    level: str
    #: Flavour within the family (``overall`` / ``government`` / ...).
    variant: str
    #: Region name, e.g. ``Mwanza``.
    region: str = ""
    #: Council name where applicable, e.g. ``Mwanza CC``.
    council: str = ""
    #: The exam / assessment name, e.g. the July 2026 mock results line.
    exam_name: str = ""
    #: The report's own section title (``TOP TEN BEST SCHOOLS ...``); this is a
    #: heading, retained here because it names *which* report this is.
    title: str = ""


@dataclass
class GenderCounts:
    """A female / male / total triple as printed under ``F`` / ``M`` / ``T``."""

    f: str = ""
    m: str = ""
    t: str = ""


# --------------------------------------------------------------------------- #
# School result slip
# --------------------------------------------------------------------------- #
@dataclass
class SubjectResult:
    """One subject's mark and grade for a candidate, e.g. ``KISW 42 'D'``."""

    subject: str
    #: The raw mark as printed (may be ``''`` / ``X`` for absent).
    mark: str = ""
    #: The grade letter as printed (``A``..``F``, or ``X``).
    grade: str = ""


@dataclass
class StudentRow:
    """One candidate line on a result slip or best-students list."""

    #: Candidate number, e.g. ``S1051-0001``.
    cno: str = ""
    #: Full name as printed.
    name: str = ""
    #: Sex (``F`` / ``M``).
    sex: str = ""
    #: Aggregate points (``AGGT``) as printed (may be ``ABS``).
    aggregate: str = ""
    #: Division as printed (``I``..``IV`` / ``0`` / ``ABS``).
    division: str = ""
    #: Overall position / ranking as printed.
    position: str = ""
    #: Owning school name (present on best-students lists, blank on a slip).
    school_name: str = ""
    #: Parsed per-subject results from the ``DETAILED SUBJECTS`` column.
    subjects: list[SubjectResult] = field(default_factory=list)
    #: The raw ``DETAILED SUBJECTS`` text, kept verbatim for lossless round-trip.
    detailed_subjects: str = ""

    # -- fields used by the *subjectwise* best-students lists -------------- #
    # Those reports rank candidates within a single subject, so instead of an
    # aggregate/division they carry that subject's mark, grade and competency.
    #: Serial number within the section as printed (``S/NO.``).
    sno: str = ""
    #: Owning council (region-level lists name the council per row).
    council: str = ""
    #: Candidate id as printed on subjectwise lists (``ID NO.``).
    id_no: str = ""
    #: School ownership / category (``GOVERNMENT`` / ``PRIVATE``).
    category: str = ""
    #: The subject mark as printed (subjectwise lists).
    marks: str = ""
    #: The subject grade letter as printed (subjectwise lists).
    grade: str = ""
    #: Competency level label as printed; its colour is derived, never stored.
    competency: str = ""


@dataclass
class DivisionSummaryRow:
    """A row of the slip's division-performance summary (``F`` / ``M`` / ``T``)."""

    #: Row label as printed (``F`` / ``M`` / ``T``).
    sex: str = ""
    #: Division counts keyed by division label (``I``, ``II``, ``III``, ``IV``,
    #: ``0``) in printed order.
    divisions: dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceRow:
    """A generic performance-summary row, values keyed by column header.

    Used for the slip's school-level registration summary and its per-subject
    performance / ranking tables, whose columns vary by report but are always
    header-labelled. The header labels (chrome) are the dict keys; the numbers
    are the data.
    """

    values: dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceTable:
    """A titled block of performance-summary rows on a result slip."""

    #: Flattened column header labels in column order (chrome, kept as keys).
    column_headers: list[str] = field(default_factory=list)
    rows: list[PerformanceRow] = field(default_factory=list)


@dataclass
class SchoolResultSlip:
    """A single school's candidate result slip."""

    meta: ReportMeta
    #: Centre number, e.g. ``S1051``.
    centre_no: str = ""
    #: School name, e.g. ``MKOLANI SECONDARY SCHOOL``.
    school_name: str = ""
    #: Division-performance summary rows (data only; the ``SEX`` / division
    #: headings are chrome).
    division_summary: list[DivisionSummaryRow] = field(default_factory=list)
    #: Every candidate on the slip.
    students: list[StudentRow] = field(default_factory=list)
    #: School- and subject-level performance summary tables printed below the
    #: candidate list (registration counts, per-subject grade breakdown, subject
    #: ranking). Captured header-driven so all figures survive round-trip.
    performance: list[PerformanceTable] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Best students
# --------------------------------------------------------------------------- #
@dataclass
class BestStudentsSection:
    """One titled block of a best-students report (overall / female / male)."""

    #: Section title (``TOP TEN BEST FEMALE STUDENTS ...``); a heading, kept so
    #: the block can be re-titled when rendered.
    title: str = ""
    students: list[StudentRow] = field(default_factory=list)


@dataclass
class BestStudentsReport:
    """Top-ten best candidates, possibly split into titled sections."""

    meta: ReportMeta
    sections: list[BestStudentsSection] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Schools rank / top schools
# --------------------------------------------------------------------------- #
@dataclass
class SchoolRankRow:
    """One school's line in a schools-rank or top-schools report."""

    #: Serial number as printed.
    sno: str = ""
    #: Ward name (present in council schools-rank; blank otherwise).
    ward: str = ""
    #: Council name (present in region-level / top-schools reports).
    council: str = ""
    #: School name.
    school_name: str = ""
    #: Ownership category (``PRIVATE`` / ``GOVERNMENT``) where printed.
    ownership: str = ""
    #: Registered candidate counts (F/M/T).
    registered: GenderCounts = field(default_factory=GenderCounts)
    #: Sat candidate counts (F/M/T).
    sat: GenderCounts = field(default_factory=GenderCounts)
    #: Percentage that sat, as printed.
    sat_pct: str = ""
    #: Division-performance counts, keyed by division label (``I``, ``II``,
    #: ``III``, ``IV``, ``0``, ``I-III``, ``I-IV``) -> F/M/T triple. Percentage
    #: columns are stored under ``<label>%`` keys.
    division: dict[str, Any] = field(default_factory=dict)
    #: GPA as printed.
    gpa: str = ""
    #: Competency label as printed (``Grade C (Good)`` etc.). Colour is derived.
    competency: str = ""
    #: Council rank as printed.
    council_rank: str = ""
    #: Regional rank as printed.
    regional_rank: str = ""


@dataclass
class SchoolsRankReport:
    """Schools ranked by performance (council or region level)."""

    meta: ReportMeta
    rows: list[SchoolRankRow] = field(default_factory=list)
    #: The DATA of any TOTAL / summary rows, keyed row-label -> ordered cell
    #: values. Only the numbers are data; the label itself is chrome but is kept
    #: as the key so the numbers can be placed back on the right summary line.
    totals: dict[str, list[str]] = field(default_factory=dict)
    #: The council/region SUMMARY PERFORMANCE block printed above the ranked
    #: table (its own small header + the aggregate figures + the ``% PASS`` row).
    #: Captured header-driven so its figures survive; empty when a report has no
    #: such block. Stored as a list so at most one table is kept, matching the
    #: lossless :class:`PerformanceTable` capture used by the result slip.
    summary: list[PerformanceTable] = field(default_factory=list)
    #: The report's own column captions in printed order, as chrome (see
    #: :attr:`SubjectsRankReport.column_headers`).
    column_headers: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Subjects rank / subject-school rank
# --------------------------------------------------------------------------- #
@dataclass
class SubjectRankRow:
    """One subject's line in a subjects-rank report."""

    sno: str = ""
    subject_name: str = ""
    #: Grade counts keyed by grade label (``A``..``F``, ``TOTAL``, ``A-C``,
    #: ``%A-C``, ``A-D``, ``%A-D``) in printed order.
    grades: dict[str, str] = field(default_factory=dict)
    gpa: str = ""
    competency: str = ""
    rank: str = ""


@dataclass
class SubjectsRankReport:
    """Subjects ranked by grade performance and GPA."""

    meta: ReportMeta
    rows: list[SubjectRankRow] = field(default_factory=list)
    totals: dict[str, list[str]] = field(default_factory=dict)
    #: The report's own column captions in printed order, as chrome. Headings are
    #: not data, but individual reports spell them differently (``RANK`` vs
    #: ``R/RANK``, and the ``COMPENTENCY LEVEL`` spelling the source PDFs use), so
    #: capturing them lets a template reproduce a given report exactly while
    #: still defaulting to canonical captions when it is handed fresh data.
    column_headers: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Generic tabular fallback
# --------------------------------------------------------------------------- #
@dataclass
class TabularRow:
    """A generic data row: values keyed by their column header label.

    Used for report types without a bespoke schema. The header labels are the
    report's own column headings (chrome), retained here as keys purely so each
    value can be identified; the values are the data.
    """

    values: dict[str, str] = field(default_factory=dict)


@dataclass
class TabularSection:
    """One self-contained table block of a generic report.

    A report can print several *different* tables under one title - the district
    performance report, for instance, splits into blocks with different column
    counts. Each such block is a section with its own header band, rows and
    totals, so nothing is dropped when the blocks do not share a shape.
    """

    #: Flattened header labels in column order (chrome, kept for field naming).
    column_headers: list[str] = field(default_factory=list)
    rows: list[TabularRow] = field(default_factory=list)
    #: DATA of TOTAL / summary rows keyed by their printed label.
    totals: dict[str, list[str]] = field(default_factory=dict)
    #: Section heading as printed, when the block carries one.
    title: str = ""


@dataclass
class GenericTabularReport:
    """Any tabular report captured header-driven, losslessly, as rows of cells.

    This guarantees no report is left unextracted even when it has no bespoke
    schema (wards pivot, district performance, mock mobility, single-subject
    school ranks). ``column_headers`` records the flattened header labels in
    column order; ``rows`` and ``totals`` carry the data.

    ``sections`` holds every table block in reading order. The top-level
    ``column_headers`` / ``rows`` / ``totals`` mirror the *first* (main) section,
    so single-block reports - the common case - can be read without indexing
    into ``sections``.
    """

    meta: ReportMeta
    #: Flattened header labels in column order (chrome, kept for field naming).
    column_headers: list[str] = field(default_factory=list)
    rows: list[TabularRow] = field(default_factory=list)
    #: DATA of TOTAL / summary rows keyed by their printed label.
    totals: dict[str, list[str]] = field(default_factory=dict)
    #: Every table block of the report, in reading order (see class docstring).
    sections: list[TabularSection] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# JSON (de)serialisation - lossless round-trip
# --------------------------------------------------------------------------- #
#: report_type id -> schema class, for :func:`from_dict` reconstruction.
SCHEMA_BY_TYPE: dict[str, type] = {
    "school_result_slip": SchoolResultSlip,
    "best_students": BestStudentsReport,
    "schools_rank": SchoolsRankReport,
    "top_schools": SchoolsRankReport,
    "subjects_rank": SubjectsRankReport,
    "subject_school_rank": GenericTabularReport,
    "wards_rank": GenericTabularReport,
    "district_performance": GenericTabularReport,
    "mock_mobility": GenericTabularReport,
    "generic": GenericTabularReport,
}


def to_dict(obj: Any) -> dict[str, Any]:
    """Serialise a schema dataclass instance to a plain ``dict``."""
    return asdict(obj)


def _build(cls: type, data: Any) -> Any:
    """Recursively reconstruct a dataclass ``cls`` from ``data``."""
    if not is_dataclass(cls) or not isinstance(data, dict):
        return data
    kwargs: dict[str, Any] = {}
    hints = {f.name: f for f in fields(cls)}
    for name, f in hints.items():
        if name not in data:
            continue
        kwargs[name] = _coerce(f.type, data[name])
    return cls(**kwargs)


def _coerce(type_hint: Any, value: Any) -> Any:
    """Coerce ``value`` toward ``type_hint`` for known nested schema types."""
    # Map string annotations (from ``__future__`` annotations) to real classes.
    nested = {
        "ReportMeta": ReportMeta,
        "GenderCounts": GenderCounts,
        "SubjectResult": SubjectResult,
        "StudentRow": StudentRow,
        "DivisionSummaryRow": DivisionSummaryRow,
        "BestStudentsSection": BestStudentsSection,
        "SchoolRankRow": SchoolRankRow,
        "SubjectRankRow": SubjectRankRow,
        "TabularRow": TabularRow,
        "TabularSection": TabularSection,
        "PerformanceRow": PerformanceRow,
        "PerformanceTable": PerformanceTable,
    }
    hint = type_hint if isinstance(type_hint, str) else getattr(type_hint, "__name__", "")
    if hint in nested and isinstance(value, dict):
        return _build(nested[hint], value)
    # dict carriers of nested dataclasses (e.g. ``dict[str, ReportMeta]``).
    if isinstance(value, dict) and isinstance(type_hint, str):
        for key, cls in nested.items():
            if f"dict[str, {key}]" in type_hint:
                return {k: _build(cls, v) for k, v in value.items()}
    # list[X] of nested dataclasses.
    if isinstance(value, list):
        for key, cls in nested.items():
            if isinstance(type_hint, str) and f"[{key}]" in type_hint:
                return [_build(cls, item) for item in value]
    return value


def from_dict(data: dict[str, Any], report_type: str | None = None) -> Any:
    """Reconstruct a schema instance from a ``dict`` produced by :func:`to_dict`.

    The report type is taken from ``data['meta']['report_type']`` when not given
    explicitly, and used to pick the schema class from :data:`SCHEMA_BY_TYPE`.
    """
    if report_type is None:
        report_type = data.get("meta", {}).get("report_type", "generic")
    cls = SCHEMA_BY_TYPE.get(report_type, GenericTabularReport)
    return _build(cls, data)


def to_json(obj: Any, *, indent: int = 2) -> str:
    """Serialise a schema instance to a JSON string."""
    return json.dumps(to_dict(obj), indent=indent, ensure_ascii=False)


def from_json(text: str, report_type: str | None = None) -> Any:
    """Reconstruct a schema instance from a JSON string."""
    return from_dict(json.loads(text), report_type=report_type)
