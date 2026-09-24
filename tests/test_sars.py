"""Tests for the SARS report converter.

The end-to-end tests run against a real reference PDF, because the whole point
of the pipeline is fidelity to those documents.
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

from sars import sources
from sars.classify import (
    _compact_columns,
    classify,
    is_total_text,
    merge_header_stacks,
    peel_banner_rows,
    split_tables,
)
from sars.extract import cluster_edges, css_family, extract_document, int_to_hex, snap
from sars.html_out import a4_box, render_document, scale_for
from sars.model import Cell, Line, Style, Table
from sars.verify import page_tokens

# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------


def test_cluster_edges_merges_near_identical_coordinates():
    # pdfplumber reports the same ruling at very slightly different offsets.
    edges = cluster_edges([10.0, 10.4, 10.9, 40.0, 40.2, 75.0])
    assert len(edges) == 3
    assert edges[0] == pytest.approx(10.433, abs=0.01)
    assert edges[1] == pytest.approx(40.1, abs=0.01)
    assert edges[2] == pytest.approx(75.0)


def test_cluster_edges_keeps_distinct_columns_apart():
    edges = cluster_edges([0.0, 1.5, 3.0, 4.5])
    assert edges == [0.0, 1.5, 3.0, 4.5]


def test_snap_finds_nearest_lattice_line():
    edges = [0.0, 20.0, 40.0, 60.0]
    assert snap(19.2, edges) == 1
    assert snap(41.0, edges) == 2
    assert snap(-5.0, edges) == 0


@pytest.mark.parametrize(
    ("pdf_font", "expected_fragment"),
    [
        ("ArialMT", "Arial"),
        ("Arial-BoldMT", "Arial"),
        ("TimesNewRomanPS-BoldMT", "Times New Roman"),
        ("BCDEEE+ArialNarrow-Bold", "Arial Narrow"),
        ("BCDEEE+Tahoma-Bold", "Tahoma"),
        # Subset CID fonts carry no usable family and must fall back.
        ("CIDFont+F2", "Arial"),
    ],
)
def test_css_family_maps_pdf_fonts(pdf_font, expected_fragment):
    assert expected_fragment in css_family(pdf_font)


def test_int_to_hex_converts_pymupdf_colours():
    assert int_to_hex(0x000000) == "#000000"
    assert int_to_hex(0x92CDDC) == "#92cddc"


# ---------------------------------------------------------------------------
# domain classification
# ---------------------------------------------------------------------------


def _cell(row, col, text, colspan=1, rowspan=1):
    lines = [Line(text=text, style=Style(), top=0.0, bottom=5.0)] if text else []
    return Cell(row=row, col=col, rowspan=rowspan, colspan=colspan, lines=lines)


def _table(cells, n_rows, n_cols):
    return Table(
        col_edges=[float(i) * 10 for i in range(n_cols + 1)],
        row_edges=[float(i) * 10 for i in range(n_rows + 1)],
        cells=cells,
    )


def test_classify_separates_header_band_from_data():
    cells = [
        _cell(0, 0, "S/NO."),
        _cell(0, 1, "SCHOOL NAME"),
        _cell(0, 2, "GPA"),
        _cell(1, 0, "01"),
        _cell(1, 1, "MUSABE BOYS"),
        _cell(1, 2, "1.4418"),
    ]
    t = classify(_table(cells, 2, 3))
    assert t.row_kinds == ["header", "data"]
    assert t.header_rows == 1


def test_classify_does_not_treat_total_column_header_as_a_totals_row():
    """A column headed TOTAL must not split the header band.

    Doing so would put a rowspan header in <thead> and the rest in <tbody>,
    truncating the span and shifting every sub-header out of its column.
    """
    cells = [
        _cell(0, 0, "S/N", rowspan=2),
        _cell(0, 1, "GRADING PERFORMANCE", colspan=3),
        _cell(1, 1, "A"),
        _cell(1, 2, "F"),
        _cell(1, 3, "TOTAL"),
        _cell(2, 0, "001"),
        _cell(2, 1, "4"),
        _cell(2, 2, "0"),
        _cell(2, 3, "4"),
    ]
    t = classify(_table(cells, 3, 4))
    assert t.row_kinds[:2] == ["header", "header"]
    assert t.header_rows == 2
    assert "total" not in t.row_kinds[:2]


def test_classify_marks_real_totals_row_after_data():
    cells = [
        _cell(0, 0, "S/NO."),
        _cell(0, 1, "COUNT"),
        _cell(1, 0, "01"),
        _cell(1, 1, "25"),
        _cell(2, 0, "TOTAL"),
        _cell(2, 1, "25"),
    ]
    t = classify(_table(cells, 3, 2))
    assert t.row_kinds == ["header", "data", "total"]


def test_is_total_text_recognises_aggregate_labels():
    assert is_total_text("TOTAL")
    assert is_total_text("grand total")
    assert is_total_text("Average")
    assert not is_total_text("MUSABE BOYS")


def test_merge_header_stacks_collapses_a_stacked_label():
    # GPA is drawn as three stacked rectangles with the label in the middle.
    cells = [
        _cell(0, 0, ""),
        _cell(1, 0, "GPA"),
        _cell(2, 0, ""),
        _cell(3, 0, "1.44"),
    ]
    t = _table(cells, 4, 1)
    t.header_rows = 3
    merge_header_stacks(t)
    survivors = [c for c in t.cells if c.row < 3]
    assert len(survivors) == 1
    assert survivors[0].text == "GPA"
    assert survivors[0].rowspan == 3


def test_split_tables_separates_regions_divided_by_a_blank_row():
    cells = [
        _cell(0, 0, "SEX"),
        _cell(0, 1, "I"),
        _cell(1, 0, "F"),
        _cell(1, 1, "4"),
        # row 2 is entirely blank -> a genuine separation
        _cell(3, 0, "CNO"),
        _cell(3, 1, "AGGT"),
        _cell(4, 0, "S1051-0001"),
        _cell(4, 1, "31"),
    ]
    parts = split_tables(_table(cells, 5, 2))
    assert len(parts) == 2
    assert parts[0].n_rows == 2
    assert parts[1].n_rows == 2
    assert parts[1].cells[0].text == "CNO"


def test_peel_banner_rows_lifts_full_width_titles_out():
    cells = [
        _cell(0, 0, "THE PRIME MINISTER'S OFFICE", colspan=3),
        _cell(1, 0, "S/NO."),
        _cell(1, 1, "SCHOOL"),
        _cell(1, 2, "GPA"),
    ]
    headings, table = peel_banner_rows(_table(cells, 2, 3))
    assert [h.text for h in headings] == ["THE PRIME MINISTER'S OFFICE"]
    assert table.n_rows == 1
    assert {c.text for c in table.cells} == {"S/NO.", "SCHOOL", "GPA"}


def test_compact_columns_drops_unused_outer_columns():
    cells = [_cell(0, 2, "SEX"), _cell(0, 3, "I")]
    out, edges = _compact_columns(cells, [0.0, 10.0, 20.0, 30.0, 40.0, 50.0])
    assert [c.col for c in out] == [0, 1]
    assert edges == [20.0, 30.0, 40.0]


# ---------------------------------------------------------------------------
# A4 page setup
# ---------------------------------------------------------------------------


def test_a4_box_orientation():
    land = a4_box("landscape")
    port = a4_box("portrait")
    assert land[0] > land[1]
    assert port[0] < port[1]
    assert land[0] == pytest.approx(port[1])


# ---------------------------------------------------------------------------
# end-to-end against a real reference PDF
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def edk_pair():
    """A small single-page portrait report."""
    hits = [p for p in sources.discover() if p.name == "Mwanza School Rank-EDK"]
    if not hits:
        pytest.skip("reference data not extracted")
    return hits[0]


@pytest.fixture(scope="module")
def edk_doc(edk_pair):
    doc = extract_document(edk_pair.pdf, edk_pair.html)
    for page in doc.pages:
        for block in page.blocks:
            if block.table is not None:
                classify(block.table)
    return doc


def test_extracted_document_has_expected_geometry(edk_doc):
    assert edk_doc.orientation == "portrait"
    assert len(edk_doc.pages) == 1
    assert edk_doc.width == pytest.approx(612, abs=1)
    assert edk_doc.height == pytest.approx(792, abs=1)


def test_scale_fits_content_inside_the_a4_page(edk_doc):
    s = scale_for(edk_doc)
    pw, ph = a4_box(edk_doc.orientation)
    assert edk_doc.width * s <= pw
    assert edk_doc.height * s <= ph


def test_grouped_header_is_recovered_with_real_spans(edk_doc):
    tables = [b.table for b in edk_doc.pages[0].blocks if b.table is not None]
    assert tables, "expected at least one table"
    main = max(tables, key=lambda t: t.n_rows)
    texts = {c.text: c for c in main.cells if not c.is_empty}
    # The grouped heading spans its sub-columns...
    assert texts["GRADING PERFORMANCE"].colspan > 1
    # ...while the identity columns span the header band vertically.
    assert texts["S/N"].rowspan == 2
    assert texts["SCHOOL NAME"].rowspan == 2


def test_rendered_html_is_pure_and_semantic(edk_doc):
    html = render_document(edk_doc)
    # Semantic table markup is present.
    for token in ("<table>", "<colgroup>", "<thead>", "<tbody>", "<th ", "rowspan=", "colspan="):
        assert token in html, token
    # None of the fixed-layout junk from the pdf2html source survives.
    for junk in ("transform:matrix", "matrix(", 'class="t c', '<div class="t '):
        assert junk not in html, junk
    # A4 orientation is declared.
    assert "@page{size:A4 portrait" in html


def test_rendered_html_preserves_original_styles(edk_doc):
    html = render_document(edk_doc)
    # Cell shading and font weights recovered from the PDF are carried in CSS.
    assert "background-color:#" in html
    assert "font-weight:700" in html
    assert re.search(r"font-size:\d+\.\d+pt", html)


def test_conversion_html_is_self_contained(edk_doc):
    """The conversion path emits a standalone document: its complete CSS (the
    shared structural DOC_CSS plus its own pooled per-cell classes) is inlined
    into its own <head> and no external stylesheet is linked."""
    html = render_document(edk_doc)
    # No external stylesheet is ever linked.
    assert 'rel="stylesheet"' not in html
    assert "<link" not in html
    # The shared structural rules are inlined, not fetched from styles.css.
    assert "<style" in html and "</style>" in html
    assert ".page{position:relative" in html
    assert "@page{size:A4" in html


def test_generated_pdf_matches_reference(edk_pair):
    """The printed A4 PDF must carry exactly the reference content."""
    generated = sources.OUT_PDF / f"{edk_pair.name}.pdf"
    if not generated.exists():
        pytest.skip("run `sars all` first")
    ref = page_tokens(edk_pair.pdf)
    out = page_tokens(generated)
    assert len(ref) == len(out)
    for a, b in zip(ref, out, strict=True):
        assert Counter("".join(a)) == Counter("".join(b))


# ---------------------------------------------------------------------------
# competency band -> colour mapping (reused by the templates in FEAT-004)
# ---------------------------------------------------------------------------


def test_competency_canonical_colours_by_label():
    from sars import competency

    assert competency.background_for("Grade A (Excellent)") == "#00b050"
    assert competency.background_for("Grade B (Very Good)") == "#92d050"
    assert competency.background_for("Grade C (Good)") == "#ffff00"
    assert competency.background_for("Grade D (Satisfactory)") == "#ffc000"
    assert competency.background_for("Grade F (Fail)") == "#ff0000"


def test_competency_bands_by_gpa_use_documented_cutoffs():
    from sars import competency

    assert competency.CUTOFFS == (1.5, 2.5, 3.5, 4.5)
    assert competency.band_for_gpa(1.0).label == "Excellent"
    assert competency.band_for_gpa(1.5).label == "Excellent"
    assert competency.band_for_gpa(2.5).label == "Very Good"
    assert competency.band_for_gpa(3.5).label == "Good"
    assert competency.band_for_gpa(4.5).label == "Satisfactory"
    assert competency.band_for_gpa(5.0).label == "Fail"


def test_competency_resolves_synonyms_and_grade_letters():
    from sars import competency

    assert competency.band_for_label("Excellent").grade == "A"
    assert competency.band_for_label("A").grade == "A"
    assert competency.band_for_label("Weak").grade == "F"
    assert competency.band_for_label("Failed").grade == "F"


def test_competency_ignores_ordinary_labels_containing_grade_letters():
    """A SCHOOL NAME with a stray 'A' must not be mistaken for a competency."""
    from sars import competency

    assert competency.band_for_label("ALLIANCE GIRLS") is None
    assert competency.band_for_label("NASCO") is None
    assert competency.band_for_label("BUHONGWA") is None


# ---------------------------------------------------------------------------
# data extraction (FEAT-003): DATA vs CHROME separation
# ---------------------------------------------------------------------------


def _report_for(name: str):
    from sars.extract import extract_document
    from sars.extract_data import extract_report

    pair = next(p for p in sources.discover() if p.name == name)
    return extract_report(extract_document(pair.pdf, pair.html), name)


def test_catalogue_covers_every_document():
    from sars import reports

    names = {p.name for p in sources.discover()}
    assert set(reports.CATALOGUE) == names
    for spec in reports.CATALOGUE.values():
        assert spec.level in ("school", "council", "region")
        assert spec.report_type and spec.variant


def test_school_slip_extracts_students_and_metadata():
    from sars import schema

    slip = _report_for("S1051-MKOLANI SECONDARY SCHOOL")
    assert isinstance(slip, schema.SchoolResultSlip)
    assert slip.centre_no == "S1051"
    assert "MKOLANI" in slip.school_name.upper()
    assert slip.meta.region == "Mwanza"
    # Every candidate across all continuation pages is captured.
    assert len(slip.students) >= 380
    first = slip.students[0]
    assert first.cno == "S1051-0001"
    assert first.sex == "F"
    assert first.subjects  # detailed subjects parsed into structured results
    assert slip.division_summary  # the F/M/T division summary is data


def test_schools_rank_extracts_rows_and_total_data():
    from sars import schema

    report = _report_for("MWANZA CC SCHOOLS RANK")
    assert isinstance(report, schema.SchoolsRankReport)
    assert report.meta.council == "Mwanza CC"
    assert report.rows
    row = report.rows[0]
    assert row.school_name
    assert row.registered.t  # F/M/T triples populated
    assert row.gpa and row.competency
    # The TOTAL row's DATA is kept; its label is the key (chrome).
    assert report.totals


def test_best_students_splits_titled_sections():
    from sars import schema

    report = _report_for("MWANZA CC 10 BEST STUDENTS")
    assert isinstance(report, schema.BestStudentsReport)
    assert len(report.sections) >= 2
    assert all(sec.students for sec in report.sections)
    assert report.sections[0].students[0].school_name


def test_subjects_rank_extracts_grade_breakdown():
    from sars import schema

    report = _report_for("MWANZA CC SUBJECTS RANK")
    assert isinstance(report, schema.SubjectsRankReport)
    assert report.rows
    row = report.rows[0]
    assert row.subject_name and row.gpa
    assert "A" in row.grades and "TOTAL" in row.grades


def test_generic_report_captures_unmapped_layouts():
    from sars import schema

    report = _report_for("Mwanza f2 Mock Mobility 2026")
    assert isinstance(report, schema.GenericTabularReport)
    assert report.column_headers
    assert report.rows and report.rows[0].values


def test_every_document_round_trips_through_json():
    from sars import schema

    for pair in sources.discover():
        report = _report_for(pair.name)
        text = schema.to_json(report)
        restored = schema.from_json(text)
        assert schema.to_json(restored) == text, pair.name


def test_competency_colour_is_not_stored_as_data():
    """DATA IS DATA, NOT STYLES: the competency colour is never stored.

    The competency band colour is a deterministic function of the label / GPA
    (:mod:`sars.competency`) computed by the template at render time, so it must
    never be written into the extracted data. The label and GPA stay plain text;
    no hex colour appears in any data field.
    """
    report = _report_for("MWANZA CC SCHOOLS RANK")

    # Competency is carried as a plain text label, never as a colour.
    labels = {row.competency for row in report.rows if row.competency}
    assert labels, "competency labels should be captured as data"
    for row in report.rows:
        for value in (row.competency, row.gpa, row.school_name, row.ownership):
            assert "#" not in value


def test_extracted_data_carries_no_presentation_fields():
    """The data schema and JSON carry only DATA + STRUCTURE, no presentation.

    No font family / size / weight, text colour, background fill, alignment or
    row pitch is stored anywhere - those belong to each report type's own
    self-contained template, not to the data.
    """
    import json
    from dataclasses import fields, is_dataclass

    from sars import schema

    # (1) No schema dataclass declares a presentation field, and CellStyle is
    #     gone entirely.
    assert not hasattr(schema, "CellStyle")
    banned = {"styles", "pitch", "total_styles", "total_pitch"}
    schema_classes = [
        getattr(schema, name) for name in dir(schema) if is_dataclass(getattr(schema, name, None))
    ]
    for cls in schema_classes:
        names = {f.name for f in fields(cls)}
        assert not (names & banned), (cls.__name__, names & banned)

    # (2) The serialised JSON of a report carries none of the style keys.
    report = _report_for("MWANZA CC SCHOOLS RANK")
    text = schema.to_json(report)
    payload = json.loads(text)
    for key in (
        "background",
        "size_pt",
        "family",
        "pitch",
        "styles",
        "total_styles",
        "total_pitch",
    ):
        assert key not in text, key
    assert set(payload) >= {"meta", "rows", "totals"}


# ---------------------------------------------------------------------------
# templates (FEAT-003): SELF-CONTAINED, FAITHFUL, no shared CSS constant
# ---------------------------------------------------------------------------


def test_template_output_is_self_contained():
    """Each templated report is a standalone document styled by its OWN inline
    <style>: no external stylesheet link, no dependency on a shared cross-report
    CSS blob. Checked for schools_rank and one other family."""
    from sars import template_maker

    for name, rtype, page_rule in (
        # schools_rank is a fixed-layout renderer that emits the reference's own
        # US-Letter page box (792pt x 612pt), not A4.
        ("MWANZA CC SCHOOLS RANK", "schools_rank", "@page{size:792pt 612pt"),
        # subjects_rank is now a fixed-layout renderer too (FEAT-003): it emits
        # the reference's own US-Letter page box (792pt x 612pt), not A4.
        ("MWANZA CC SUBJECTS RANK", "subjects_rank", "@page{size:792pt 612pt"),
    ):
        html = template_maker.render_html(rtype, _report_for(name))
        assert "<!DOCTYPE html>" in html
        assert "<style" in html and "</style>" in html
        # No external stylesheet is ever linked.
        assert 'rel="stylesheet"' not in html
        assert "<link" not in html
        # The page geometry is declared in the document's own inline style.
        assert page_rule in html


def test_schools_rank_paints_every_wash_its_reference_paints():
    """Every fill colour the reference PDF paints must appear in the output.

    Stronger than checking a hand-typed palette: the expected colours are read
    out of the reference document itself, so a wash cannot drift (the previous
    hand-typed list had ``#daeef4`` where the reference actually paints
    ``#daeef3``, and four more like it).
    """
    import pymupdf

    from sars import template_maker

    pair = next(p for p in sources.discover() if p.name == "MWANZA CC SCHOOLS RANK")
    with pymupdf.open(pair.pdf) as document:
        expected = set()
        for drawing in document[0].get_drawings():
            if drawing["type"] not in ("f", "fs") or drawing.get("fill") is None:
                continue
            expected.add(
                "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in drawing["fill"])
            )

    html = template_maker.render_html("schools_rank", _report_for("MWANZA CC SCHOOLS RANK"))
    missing = sorted(wash for wash in expected if wash not in html)
    assert not missing, f"washes the reference paints but the template does not: {missing}"


def test_competency_band_colour_is_derived_from_the_value():
    """The competency wash is computed from the label, never replayed from the PDF."""
    from sars import template_maker

    report = _report_for("MWANZA CC SCHOOLS RANK")
    for row in report.rows:
        row.competency = "Grade A (Excellent)"
    html = template_maker.render_html("schools_rank", report)
    # Excellent -> #00b050; the reference's own band for these rows is yellow, so
    # this colour can only come from the deterministic competency mapping.
    assert "#00b050" in html


def test_no_shared_css_constant_across_report_types():
    """Two different report types must NOT share one identical monolithic style
    block: each owns its own inline styling. There is also no shared
    DOC_CSS / TEMPLATE_CSS constant funneling every report through one look."""
    import re

    from sars import template_maker
    from sars.templates import base

    # The dismantled shared-funnel constants are gone from the template base.
    assert not hasattr(base, "TEMPLATE_CSS")
    assert not hasattr(base, "DOC_CSS")
    assert not hasattr(base, "document_html")

    def style_block(html: str) -> str:
        m = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
        return m.group(1) if m else ""

    sr = style_block(
        template_maker.render_html("schools_rank", _report_for("MWANZA CC SCHOOLS RANK"))
    )
    sj = style_block(
        template_maker.render_html("subjects_rank", _report_for("MWANZA CC SUBJECTS RANK"))
    )
    assert sr and sj
    # The two report types emit different, independent style blocks.
    assert sr != sj
