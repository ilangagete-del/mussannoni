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

requires_s1051 = pytest.mark.skipif(
    not os.path.exists(S1051_PDF), reason="S1051 reference PDF not present"
)
requires_council = pytest.mark.skipif(
    not os.path.exists(COUNCIL_PDF), reason="council reference PDF not present"
)


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
    assert "MWANZA CC TOP TEN BEST SCHOOLS" in ir.title_lines

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
