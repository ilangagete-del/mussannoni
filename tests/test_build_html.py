"""Tests for :mod:`sars_convert.build_html` (FEAT-004 clean HTML+CSS).

These build clean HTML directly from small hand-built IR fixtures (so they run
without any PDF), plus one end-to-end build over the real recovered IR when it
is present. They assert the semantic structure that matters: grouped ``<thead>``
colspans/rowspans, data cell values in the right columns, the ``@page``
orientation, rotated-label repair, conditional percentage shading, and the
absence of any fixed-layout artifacts (``transform:matrix`` / ``position:
absolute`` / pooled ``.cN`` / ``class="t "``).
"""

from __future__ import annotations

import os
import re

import pytest

from sars_convert import build_html as B

IR_DIR = os.path.join("output", "ir")


# ---------------------------------------------------------------------------
# IR fixtures (no PDF required)
# ---------------------------------------------------------------------------
def _s1051_ir() -> dict:
    return {
        "stem": "S1051-MKOLANI SECONDARY SCHOOL",
        "category": "student",
        "orientation": "landscape",
        "title_lines": [
            "THE PRIME MINISTER'S OFFICE",
            "S1051 - MKOLANI SECONDARY SCHOOL",
        ],
        "captions": [],
        "tables": [
            {
                "caption": "DIVISION PERFORMANCE SUMMARY",
                "n_cols": 6,
                "kind": "pivot",
                "header_rows": [
                    [
                        {"label": "SEX", "colspan": 1, "rowspan": 1, "col": 0, "row": 0},
                        {"label": "I", "colspan": 1, "rowspan": 1, "col": 1, "row": 0},
                        {"label": "II", "colspan": 1, "rowspan": 1, "col": 2, "row": 0},
                        {"label": "III", "colspan": 1, "rowspan": 1, "col": 3, "row": 0},
                        {"label": "IV", "colspan": 1, "rowspan": 1, "col": 4, "row": 0},
                        {"label": "0", "colspan": 1, "rowspan": 1, "col": 5, "row": 0},
                    ]
                ],
                "body": [["F", "0", "4", "17", "180", "12"]],
                "percent_cells": [[False] * 6],
            },
            {
                "caption": "",
                "n_cols": 7,
                "kind": "student-list",
                "header_rows": [
                    [
                        {"label": lbl, "colspan": 1, "rowspan": 1, "col": i, "row": 0}
                        for i, lbl in enumerate(
                            [
                                "CNO",
                                "CANDIDATE FULL NAME",
                                "SEX",
                                "AGGT",
                                "DIV",
                                "POS",
                                "DETAILED SUBJECTS",
                            ]
                        )
                    ]
                ],
                "body": [
                    [
                        "S1051-0001",
                        "ABIGAEL SAMSONI MICHAEL",
                        "F",
                        "31",
                        "IV",
                        "215",
                        "HTM - 68'B' BUSI - 21'F'",
                    ]
                ],
                "percent_cells": [[False] * 7],
            },
        ],
    }


def _council_ir() -> dict:
    return {
        "stem": "MWANZA CC 10 BEST SCHOOLS",
        "category": "council",
        "orientation": "landscape",
        "title_lines": ["THE PRIME MINISTER'S OFFICE"],
        "captions": [],
        "tables": [
            {
                "caption": "",
                "n_cols": 6,
                "kind": "table",
                "header_rows": [
                    [
                        {"label": "S/NO.", "colspan": 1, "rowspan": 2, "col": 0, "row": 0},
                        {"label": "SCHOOL NAME", "colspan": 1, "rowspan": 2, "col": 1, "row": 0},
                        {
                            "label": "NUMBER OF CANDIDATES",
                            "colspan": 3,
                            "rowspan": 1,
                            "col": 2,
                            "row": 0,
                        },
                        {"label": "K N A R /C", "colspan": 1, "rowspan": 2, "col": 5, "row": 0},
                    ],
                    [
                        {"label": "F", "colspan": 1, "rowspan": 1, "col": 2, "row": 1},
                        {"label": "T", "colspan": 1, "rowspan": 1, "col": 3, "row": 1},
                        {"label": "%", "colspan": 1, "rowspan": 1, "col": 4, "row": 1},
                    ],
                ],
                "body": [
                    ["01", "MUSABE BOYS", "0", "225", "100", "1"],
                    ["02", "BUTIMBA DAY", "0", "212", "26", "4"],
                ],
                "percent_cells": [
                    [False, False, False, False, True, False],
                    [False, False, False, False, True, False],
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# Rotated / garbled label repair
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "garbled,expected",
    [
        ("K N A R /C", "C/RANK"),
        ("R /C", "C/RANK"),
        ("X E S", "SEX"),
        ("NOISIVID", "DIVISION"),
        ("SOP", "POS"),
        ("N O IT IS O P", "POSITION"),
    ],
)
def test_repair_label_maps_rotated_glyphs(garbled: str, expected: str) -> None:
    assert B.repair_label(garbled) == expected


def test_repair_label_passes_through_normal_labels() -> None:
    assert B.repair_label("SCHOOL NAME") == "SCHOOL NAME"


# ---------------------------------------------------------------------------
# Conditional percentage shading
# ---------------------------------------------------------------------------
def test_percent_class_grades_by_value() -> None:
    assert B.percent_class("100") == "pct-hi"
    assert B.percent_class("97.59") == "pct-good"
    assert B.percent_class("60") == "pct-mid"
    assert B.percent_class("26.89") == "pct-low"
    assert B.percent_class("8.41") == "pct-min"
    assert B.percent_class("Grade A") == ""


# ---------------------------------------------------------------------------
# Grouped header structure
# ---------------------------------------------------------------------------
def test_council_thead_has_expected_spans_and_repaired_rotated_head() -> None:
    ir = _council_ir()
    html = B.build_document_html(ir)
    # NUMBER OF CANDIDATES super-header spans 3 columns and is tinted.
    assert re.search(r'<th colspan="3" class="grp-cand">NUMBER OF CANDIDATES</th>', html)
    # S/NO. and SCHOOL NAME are tall single-column headers (rowspan 2).
    assert '<th rowspan="2">S/NO.</th>' in html
    assert '<th rowspan="2">SCHOOL NAME</th>' in html
    # the rotated C/RANK header is repaired and marked vertical.
    assert 'class="vhead">C/RANK</th>' in html
    # the '%' sub-header carries its own hook.
    assert '<th class="pct-head">%</th>' in html


def test_council_body_values_land_in_expected_columns_with_shading() -> None:
    ir = _council_ir()
    html = B.build_document_html(ir)
    # first data row: ordinal cell, school name left aligned, and a shaded 100%.
    assert re.search(r"<td[^>]*>01</td>", html)
    assert re.search(r'<td class="al-left">MUSABE BOYS</td>', html)
    # 100% -> pct-hi (green); 26% -> pct-low.
    assert re.search(r'<td class="al-center pct-hi">100</td>', html)
    assert re.search(r'<td class="al-center pct-low">26</td>', html)


def test_student_doc_has_pivot_and_blue_cno_and_orientation() -> None:
    ir = _s1051_ir()
    html = B.build_document_html(ir)
    assert "@page { size: A4 landscape;" in html
    assert 'class="doc-student"' in html
    # pivot table gets its own class; CNO cell is blue-coded.
    assert '<table class="report pivot">' in html
    assert re.search(r'<td class="al-center cno">S1051-0001</td>', html)
    # DETAILED SUBJECTS is left-aligned free text.
    assert re.search(r'<td class="al-left">HTM - 68', html)
    # banner heading present as <h1> (apostrophe HTML-escaped).
    assert "<h1>THE PRIME MINISTER&#x27;S OFFICE</h1>" in html


def test_portrait_orientation_declared_for_portrait_doc() -> None:
    ir = _s1051_ir()
    ir["orientation"] = "portrait"
    html = B.build_document_html(ir)
    assert "@page { size: A4 portrait;" in html


def test_no_fixed_layout_artifacts_in_generated_html() -> None:
    for ir in (_s1051_ir(), _council_ir()):
        html = B.build_document_html(ir)
        assert "transform:matrix" not in html
        assert "position:absolute" not in html
        assert 'class="t ' not in html
        assert not re.search(r'class="c\d+"', html)


def test_merge_continuations_folds_headerless_table() -> None:
    tables = [
        {
            "n_cols": 3,
            "header_rows": [[{"label": "A", "colspan": 1, "rowspan": 1, "col": 0, "row": 0}]],
            "body": [["1", "2", "3"]],
            "percent_cells": [[False, False, False]],
        },
        {
            "n_cols": 3,
            "header_rows": [],
            "body": [["4", "5", "6"]],
            "percent_cells": [[False, False, False]],
        },
    ]
    merged = B.merge_continuations(tables)
    assert len(merged) == 1
    assert merged[0]["body"] == [["1", "2", "3"], ["4", "5", "6"]]


# ---------------------------------------------------------------------------
# End-to-end over the real recovered IR (skips if not generated)
# ---------------------------------------------------------------------------
requires_ir = pytest.mark.skipif(
    not os.path.exists(os.path.join(IR_DIR, "MWANZA CC 10 BEST SCHOOLS.json")),
    reason="IR not generated (run `python -m sars_convert.extract`)",
)


@requires_ir
def test_build_real_council_ir_produces_clean_semantic_html() -> None:
    ir = B._load_ir(os.path.join(IR_DIR, "MWANZA CC 10 BEST SCHOOLS.json"))
    html = B.build_document_html(ir)
    assert "<table" in html and "<thead>" in html and "<tbody>" in html
    assert re.search(r'colspan="7"[^>]*>NUMBER OF CANDIDATES</th>', html)
    assert "MUSABE BOYS" in html
    assert "transform:matrix" not in html and "position:absolute" not in html


@requires_ir
def test_build_real_s1051_ir_recovers_first_student_row() -> None:
    ir = B._load_ir(os.path.join(IR_DIR, "S1051-MKOLANI SECONDARY SCHOOL.json"))
    html = B.build_document_html(ir)
    assert 'class="al-center cno">S1051-0001</td>' in html
    assert "ABIGAEL SAMSONI MICHAEL" in html
    assert "@page { size: A4 landscape;" in html
