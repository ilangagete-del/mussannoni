"""Tests for :mod:`sars_convert.extract` (FEAT-003 PDF data recovery).

These exercise the *real* pdfplumber extraction against the reference PDFs (no
static fixtures): they open the actual ``data/sars`` PDFs, run the per-document
profiles, and assert concrete recovered values and grouped-header spans. If a
reference PDF is missing (e.g. a checkout without the tracked ``data/sars``
tree) the PDF-backed tests skip rather than fail.
"""

from __future__ import annotations

import os

import pytest

from sars_convert import extract as E
from sars_convert.extract import (
    HeaderCell,
    is_header_row,
    reconstruct_header_spans,
    split_banner,
)

DATA_ROOT = "data/sars"
S1051_PDF = os.path.join(DATA_ROOT, "S1051-MKOLANI SECONDARY SCHOOL.pdf")
COUNCIL_PDF = os.path.join(DATA_ROOT, "council_pdf", "MWANZA CC 10 BEST SCHOOLS.pdf")
# Docs whose banner pdfplumber does NOT collapse into a table cell (so the
# earlier table-cell-only detection left title_lines empty) -- the word-based
# recovery must repopulate them.
DISTRICT_PDF = os.path.join(DATA_ROOT, "region_pdf", "Mwanza f2 District Performance.pdf")
SUBJECTS_RANK_PDF = os.path.join(DATA_ROOT, "council_pdf", "MWANZA CC SUBJECTS RANK.pdf")
TOP10_PDF = os.path.join(DATA_ROOT, "region_pdf", "Mwanza Top 10 Schools.pdf")
# The busiest subjectwise report: 18 subject sections, several packed onto a
# single page. Caption recovery must return ONE caption PER SECTION.
SUBJECTWISE_PDF = os.path.join(DATA_ROOT, "council_pdf", "MWANZA CC SCHOOLS RANK SUBJECTWISE.pdf")

requires_s1051 = pytest.mark.skipif(
    not os.path.exists(S1051_PDF), reason="S1051 reference PDF not present"
)
requires_council = pytest.mark.skipif(
    not os.path.exists(COUNCIL_PDF), reason="council reference PDF not present"
)
requires_district = pytest.mark.skipif(
    not os.path.exists(DISTRICT_PDF), reason="district reference PDF not present"
)
requires_subjects_rank = pytest.mark.skipif(
    not os.path.exists(SUBJECTS_RANK_PDF), reason="subjects-rank reference PDF not present"
)
requires_top10 = pytest.mark.skipif(
    not os.path.exists(TOP10_PDF), reason="top-10 reference PDF not present"
)
requires_subjectwise = pytest.mark.skipif(
    not os.path.exists(SUBJECTWISE_PDF), reason="subjectwise reference PDF not present"
)

_STANDARD_BANNER = [
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
    "MWANZA REGION",
]


# ---------------------------------------------------------------------------
# Pure helpers (no PDF needed)
# ---------------------------------------------------------------------------
def test_split_banner_splits_ordered_heading_lines() -> None:
    cell = "THE PRIME MINISTER'S OFFICE\nMWANZA REGION\n\nS1051 - MKOLANI"
    assert split_banner(cell) == [
        "THE PRIME MINISTER'S OFFICE",
        "MWANZA REGION",
        "S1051 - MKOLANI",
    ]


def test_is_header_row_distinguishes_labels_from_data() -> None:
    assert is_header_row(["S/NO.", "SCHOOL NAME", "NUMBER OF CANDIDATES"])
    # a numeric data row is not a header
    assert not is_header_row(["01", "MUSABE BOYS", "0", "225", "225"])


def test_reconstruct_header_spans_recovers_grouped_grid() -> None:
    """A merged cell emits its label once then ``None`` for the span it covers.

    Model the council grouped header band:

        NUMBER OF CANDIDATES (colspan 3) | DIVISION PERFORMANCE (colspan 3)
        REGISTERED           | SAT       | I    | II    | (bottom row)
    """
    header = [
        ["NUMBER OF CANDIDATES", None, None, "DIVISION PERFORMANCE", None, None],
        ["REGISTERED", None, None, "I", None, None],
        ["F", "M", "T", "F", "M", "T"],
    ]
    spans = reconstruct_header_spans(header)
    top = {c.label: c for c in spans[0]}
    assert top["NUMBER OF CANDIDATES"].colspan == 3
    assert top["DIVISION PERFORMANCE"].colspan == 3
    # the bottom row has six single F/M/T cells
    assert len(spans[2]) == 6
    assert all(c.colspan == 1 for c in spans[2])


def test_reconstruct_header_spans_rowspan_for_stub_columns() -> None:
    """A label that stays over blank cells below it earns a rowspan."""
    header = [
        ["S/NO.", "NUMBER OF CANDIDATES", None],
        [None, "REGISTERED", "SAT"],
        [None, "F", "F"],
    ]
    spans = reconstruct_header_spans(header)
    sno = next(c for c in spans[0] if c.label == "S/NO.")
    assert sno.rowspan == 3
    assert sno.colspan == 1


def test_header_cell_defaults() -> None:
    cell = HeaderCell(label="GPA")
    assert cell.colspan == 1 and cell.rowspan == 1 and cell.col == 0


# ---------------------------------------------------------------------------
# Real extraction: S1051 student-list
# ---------------------------------------------------------------------------
@requires_s1051
def test_extract_s1051_titles_and_pivot() -> None:
    ir = E.extract_document("S1051-MKOLANI SECONDARY SCHOOL", S1051_PDF, "student")
    assert ir.orientation == "landscape"
    assert ir.pages == 13
    # banner title lines are ordered headings, not table rows
    assert ir.title_lines[0] == "THE PRIME MINISTER'S OFFICE"
    assert "S1051 - MKOLANI SECONDARY SCHOOL" in ir.title_lines

    pivot = next(t for t in ir.tables if t.kind == "pivot")
    assert pivot.caption == "DIVISION PERFORMANCE SUMMARY"
    header_labels = [c.label for row in pivot.header_rows for c in row]
    assert header_labels[:6] == ["SEX", "I", "II", "III", "IV", "0"]
    # F/M/T rows with the divisions
    assert pivot.body[0][0] == "F"
    assert pivot.body[-1][0] == "T"


@requires_s1051
def test_extract_s1051_first_student_row() -> None:
    ir = E.extract_document("S1051-MKOLANI SECONDARY SCHOOL", S1051_PDF, "student")
    students = next(t for t in ir.tables if t.kind == "student-list")
    labels = [c.label for c in students.header_rows[0]]
    assert labels == [
        "CNO",
        "CANDIDATE FULL NAME",
        "SEX",
        "AGGT",
        "DIV",
        "POS",
        "DETAILED SUBJECTS",
    ]
    first = students.body[0]
    assert first[0] == "S1051-0001"
    assert first[1] == "ABIGAEL SAMSONI MICHAEL"
    assert first[2] == "F"  # SEX
    assert first[3] == "31"  # AGGT
    assert first[4] == "IV"  # DIV
    assert first[5] == "215"  # POS
    assert "HTM" in first[6]  # DETAILED SUBJECTS free text
    # the full student roster is recovered across all 13 pages
    assert len(students.body) >= 380


# ---------------------------------------------------------------------------
# Real extraction: council MWANZA CC 10 BEST SCHOOLS
# ---------------------------------------------------------------------------
@requires_council
def test_extract_council_grouped_header_spans() -> None:
    ir = E.extract_document("MWANZA CC 10 BEST SCHOOLS", COUNCIL_PDF, "council")
    assert ir.orientation == "landscape"
    # the report banner + the first section caption together carry both centred
    # heading lines the reference prints above the grid (one stays in the
    # banner, the first section's caption is attached to the table it labels).
    all_headings = ir.title_lines + [t.caption for t in ir.tables if t.caption]
    assert "MWANZA CC TOP TEN BEST SCHOOLS" in all_headings

    table = ir.tables[0]
    top = {c.label: c for c in table.header_rows[0]}
    # grouped multi-row header preserved as spans (NOT flattened)
    assert top["NUMBER OF CANDIDATES"].colspan == 7
    assert top["DIVISION PERFORMANCE"].colspan == 27
    # the ordinal and name columns span the whole header band height
    assert top["S/NO."].rowspan == 3
    assert top["SCHOOL NAME"].rowspan == 3
    assert len(table.header_rows) == 3


@requires_council
def test_extract_council_musabe_boys_row() -> None:
    ir = E.extract_document("MWANZA CC 10 BEST SCHOOLS", COUNCIL_PDF, "council")
    table = ir.tables[0]
    musabe = next(r for r in table.body if r[1] == "MUSABE BOYS")
    assert musabe[0] == "01"  # S/NO.
    # REGISTERED F/M/T = 0/225/225 -> T is 225
    assert musabe[4] == "225"
    # SAT % column = 100
    assert musabe[8] == "100"
    # GPA and competency
    assert musabe[33] == "1.4418"
    assert musabe[34] == "Grade A (Excellent)"
    assert musabe[35] == "1"  # C/RANK


@requires_council
def test_extract_council_percent_hints() -> None:
    ir = E.extract_document("MWANZA CC 10 BEST SCHOOLS", COUNCIL_PDF, "council")
    table = ir.tables[0]
    idx = next(i for i, r in enumerate(table.body) if r[1] == "MUSABE BOYS")
    flags = table.percent_cells[idx]
    # the SAT % column (index 8) is flagged as a colour-coded percentage cell
    assert flags[8] is True
    # a plain count column is not
    assert flags[4] is False


@requires_council
def test_extract_council_crosscheck_no_missing() -> None:
    ir = E.extract_document("MWANZA CC 10 BEST SCHOOLS", COUNCIL_PDF, "council")
    result = E.crosscheck(ir, "council")
    assert result["checked"] is True
    # every recovered token is present in the source HTML (no dropped values)
    assert result["missing_count"] == 0


# ---------------------------------------------------------------------------
# Pure helpers: caption vs header/data/rotated-glyph classification
# ---------------------------------------------------------------------------
def test_looks_like_caption_accepts_section_titles() -> None:
    assert E._looks_like_caption("DISTRICT PERFORMANCE FOR GOVERNMENT SCHOOLS ONLY")
    assert E._looks_like_caption("TOP 10 BEST PRIVATE SCHOOLS")
    assert E._looks_like_caption("TEN LOOSER SCHOOLS OVERALL")


def test_looks_like_caption_rejects_headers_data_and_glyphs() -> None:
    # a header band label row (carries GPA/COMPETENCY column heads)
    assert not E._looks_like_caption("S/N DISTRICT SCHOOLS GPA COMPETENCY LEVEL KNAR")
    # a data row (starts with an ordinal)
    assert not E._looks_like_caption("01 ILEMELA MC 61 5369 4400 9769")
    # a rotated single-glyph strip
    assert not E._looks_like_caption("N N O O X G IV IS")
    # bare header group
    assert not E._looks_like_caption("GRADE PERFORMANCE")


# ---------------------------------------------------------------------------
# BUG 1 regression: banner recovery for docs pdfplumber does not collapse into
# a table cell (these previously produced title_lines == []).
# ---------------------------------------------------------------------------
@requires_district
def test_district_performance_banner_recovered() -> None:
    """Previously title_lines == [] (the whole banner was dropped)."""
    ir = E.extract_document("Mwanza f2 District Performance", DISTRICT_PDF, "region")
    # the four constant banner lines are present and in order ...
    assert ir.title_lines[: len(_STANDARD_BANNER)] == _STANDARD_BANNER
    assert "REGIONAL FORM TWO MOCK ASSESSMENT RESULTS, JULY 2026" in ir.title_lines
    # ... and the report subtitle is recovered -- now attached to the first
    # section's table as its caption (per-section labelling) rather than left
    # in the banner, so every district section prints its own heading.
    assert ir.tables[0].caption == "DISTRICT PERFORMANCE OVERALL"


@requires_subjects_rank
def test_subjects_rank_banner_recovered() -> None:
    """Banner sat as page text (not a table cell) -> was dropped before."""
    ir = E.extract_document("MWANZA CC SUBJECTS RANK", SUBJECTS_RANK_PDF, "council")
    assert ir.title_lines[0] == "THE PRIME MINISTER'S OFFICE"
    assert "MWANZA REGION" in ir.title_lines
    # the report subtitle is recovered either in the banner or as the first
    # table's section caption.
    all_headings = ir.title_lines + [t.caption for t in ir.tables if t.caption]
    assert "MWANZA CC ALL SUBJECTS PERFOMANCE" in all_headings


# ---------------------------------------------------------------------------
# BUG 2 regression: distinct sections keep their own captions (not silent
# duplicates), and genuinely-different multi-section docs stay separate.
# ---------------------------------------------------------------------------
@requires_district
def test_district_performance_sections_captioned_not_duplicated() -> None:
    ir = E.extract_document("Mwanza f2 District Performance", DISTRICT_PDF, "region")
    captions = [t.caption for t in ir.tables]
    # every page is a DIFFERENT section and each carries its OWN caption now,
    # including the first ("... OVERALL") which used to render caption-less.
    assert captions[0] == "DISTRICT PERFORMANCE OVERALL"
    # the remaining pages are DIFFERENT sections, each with its own caption
    assert "DISTRICT PERFORMANCE FOR GOVERNMENT SCHOOLS ONLY" in captions
    assert "DISTRICT PERFORMANCE FOR PRIVATE SCHOOLS ONLY" in captions
    assert "DISTRICT PERFORMANCE BY PERCENTAGE" in captions
    assert "DISTRICT PERFORMANCE BY KPI" in captions
    # no two kept tables are a silent duplicate (same header + identical body
    # with no distinguishing caption)
    for i in range(len(ir.tables)):
        for j in range(i + 1, len(ir.tables)):
            a, b = ir.tables[i], ir.tables[j]
            if a.header_rows == b.header_rows and a.body == b.body and a.body:
                assert a.caption != b.caption and (a.caption or b.caption)


@requires_top10
def test_top10_schools_sections_distinct() -> None:
    ir = E.extract_document("Mwanza Top 10 Schools", TOP10_PDF, "region")
    captions = [t.caption for t in ir.tables]
    for expected in (
        "TOP 10 BEST GOVERNMENT SCHOOLS",
        "TOP 10 BEST PRIVATE SCHOOLS",
        "TEN LOOSER SCHOOLS OVERALL",
        "TEN LOOSER GOVERNMENT SCHOOLS",
        "TEN LOOSER PRIVATE SCHOOLS",
    ):
        assert expected in captions


@requires_council
def test_ten_best_schools_keeps_distinct_sections() -> None:
    """The council 10-best doc has multiple DIFFERENT sections; keep them all."""
    ir = E.extract_document("MWANZA CC 10 BEST SCHOOLS", COUNCIL_PDF, "council")
    # five genuinely different tables (OVERALL best, private, looser, ...) -- the
    # de-dup must NOT collapse these distinct sections.
    assert len(ir.tables) == 5
    bodies = [tuple(tuple(r) for r in t.body) for t in ir.tables]
    # the distinct-section bodies are not all identical
    assert len(set(bodies)) == len(bodies)


def test_dedup_drops_identical_captionless_repeat() -> None:
    """A true repeat (same header + body, no new caption) is collapsed."""
    header = [[HeaderCell(label="S/NO."), HeaderCell(label="SCHOOL NAME", col=1)]]
    body = [["01", "MUSABE BOYS"], ["02", "LUCHELELE"]]
    t1 = E.Table(caption="OVERALL", n_cols=2, header_rows=header, body=body)
    repeat = E.Table(caption="", n_cols=2, header_rows=header, body=body)
    distinct = E.Table(
        caption="PRIVATE",
        n_cols=2,
        header_rows=header,
        body=[["01", "ISLAMIYA"]],
    )
    kept = E._dedup_repeats([t1, repeat, distinct])
    assert [t.caption for t in kept] == ["OVERALL", "PRIVATE"]


def test_dedup_keeps_identical_body_with_distinct_caption() -> None:
    """Distinct sections that coincidentally share data are both kept."""
    header = [[HeaderCell(label="S/NO."), HeaderCell(label="NAME", col=1)]]
    body = [["01", "MISUNGWI DC"]]
    a = E.Table(caption="BEST MALE STUDENTS", n_cols=2, header_rows=header, body=body)
    b = E.Table(
        caption="BEST MALE STUDENTS FOR PRIVATE SCHOOLS",
        n_cols=2,
        header_rows=header,
        body=body,
    )
    kept = E._dedup_repeats([a, b])
    assert len(kept) == 2


# ---------------------------------------------------------------------------
# Review regression: caption recovery is ONE-PER-SECTION, not one-per-page.
# The busiest subjectwise report packs several subject sections onto one page;
# every section must recover its own caption (previously 9/18 were dropped and
# rendered as unlabeled tables).
# ---------------------------------------------------------------------------
# The 18 subject sections the reference PDF prints, in order.
_SUBJECTWISE_SECTIONS = [
    "HTM",
    "BUSINESS STUDIES",
    "GEOGRAPHY",
    "KISWAHILI",
    "ENGLISH LANGUAGE",
    "PHYSICS",
    "CHEMISTRY",
    "BIOLOGY",
    "BASIC MATHEMATICS",
    "HISTORY",
    "B/KEEPING",
    "BIBLE KNOWLEDGE",
    "ELIMU YA DINI YA KIISLAMU",
    "CHINES LANGUAGE",
    "FRENCH LANGUAGE",
    "COMPUTER SCIENCE",
    "SPORT STUDIES",
    "FOOD AND NUTRITION",
]


@requires_subjectwise
def test_subjectwise_recovers_every_section_caption() -> None:
    """All 18 subject-section captions are recovered (was 9/18 before).

    Sections that used to render caption-less -- GEOGRAPHY, BIBLE KNOWLEDGE,
    ELIMU YA DINI YA KIISLAMU, CHINES/FRENCH LANGUAGE, COMPUTER SCIENCE, SPORT
    STUDIES, FOOD AND NUTRITION and the first-page HTM -- must now each carry
    their own caption, because the report packs several onto one page.
    """
    ir = E.extract_document("MWANZA CC SCHOOLS RANK SUBJECTWISE", SUBJECTWISE_PDF, "council")
    captions = [t.caption for t in ir.tables if t.caption]
    # every subject section has exactly one "SCHOOL RANK IN <SUBJECT> COUNCILWISE"
    for subject in _SUBJECTWISE_SECTIONS:
        expected = f"SCHOOL RANK IN {subject} COUNCILWISE"
        assert expected in captions, f"missing section caption for {subject!r}"
    # 18 distinct sections recovered (no page's sections collapsed to one)
    assert len({c for c in captions if c.startswith("SCHOOL RANK IN")}) == 18
    # the previously-dropped subject words are now present as captions
    joined = " ".join(captions).upper()
    for token in ("GEOGRAPHY", "BIBLE", "KIISLAMU", "CHINES", "FRENCH", "COMPUTER"):
        assert token in joined


@requires_subjectwise
def test_subjectwise_first_section_caption_not_lost_to_banner() -> None:
    """The first section (HTM) must NOT be swallowed by the banner title lines.

    Its caption is attached to the first data table, while the genuine report
    subtitle stays in the banner.
    """
    ir = E.extract_document("MWANZA CC SCHOOLS RANK SUBJECTWISE", SUBJECTWISE_PDF, "council")
    # HTM's caption lives on the first table, not in the banner.
    assert ir.tables[0].caption == "SCHOOL RANK IN HTM COUNCILWISE"
    assert "SCHOOL RANK IN HTM COUNCILWISE" not in ir.title_lines
    # the genuine report subtitle is preserved in the banner.
    assert "MWANZA CC SCHOOLS RANK SUBJECTWISE" in ir.title_lines


@requires_subjectwise
def test_subjectwise_body_data_intact() -> None:
    """Recovering per-section captions must not drop or mis-column any data."""
    ir = E.extract_document("MWANZA CC SCHOOLS RANK SUBJECTWISE", SUBJECTWISE_PDF, "council")
    # all body rows survive and every recovered token is in the source HTML.
    assert sum(len(t.body) for t in ir.tables) >= 700
    result = E.crosscheck(ir, "council")
    assert result["checked"] is True
    assert result["missing_count"] == 0


# ---------------------------------------------------------------------------
# Review regression: the S1051 trailing centre-summary tables must carry their
# captions ("... OVERALL PERFORMANCE" / "... SUBJECTS GRADING PERFORMANCE
# SUMMARY") instead of being appended caption-less.
# ---------------------------------------------------------------------------
@requires_s1051
def test_s1051_summary_tables_carry_captions() -> None:
    ir = E.extract_document("S1051-MKOLANI SECONDARY SCHOOL", S1051_PDF, "student")
    summary = [t for t in ir.tables if t.kind == "summary"]
    assert summary, "expected trailing centre-summary tables"
    # none of the summary tables is caption-less any more
    assert all(t.caption for t in summary)
    captions = " ".join(t.caption for t in summary).upper()
    assert "GRADING PERFORMANCE SUMMARY" in captions
    assert "OVERALL" in captions
