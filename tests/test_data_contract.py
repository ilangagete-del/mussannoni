"""The documented data contract, executed.

``docs/DATA_STRUCTURE.md`` tells a caller what to supply. These tests build data
exactly the way that document says to and assert it renders — so the
documentation cannot drift away from the code without a test failing.

Nothing here rasterises; the pixel gate lives in ``tests/test_fidelity_gate.py``.
"""

from __future__ import annotations

import re

import pytest

from sars import layout_spec, schema, template_maker
from sars.secondary import competency
from sars.secondary.templates import RENDERERS

PG = '<div class="pg"'


def _meta(**kw):
    base = dict(
        name="MY COUNCIL SCHOOLS RANK 2027",
        report_type="schools_rank",
        level="council",
        variant="overall",
        region="Mwanza",
        council="My CC",
        exam_name="REGIONAL FORM TWO MOCK ASSESSMENT RESULTS, JULY 2027",
        title="MY COUNCIL SCHOOLS RANK",
    )
    base.update(kw)
    return schema.ReportMeta(**base)


def _schools_rank(rows: int) -> schema.SchoolsRankReport:
    """The worked example from §6 of the data-structure document."""
    return schema.SchoolsRankReport(
        meta=_meta(),
        rows=[
            schema.SchoolRankRow(
                sno=str(i + 1),
                ward="NYAMAGANA",
                school_name=f"SCHOOL NUMBER {i + 1}",
                ownership="GOVERNMENT",
                registered=schema.GenderCounts(f="30", m="28", t="58"),
                sat=schema.GenderCounts(f="29", m="27", t="56"),
                sat_pct="96.6",
                division={"I": {"f": "5", "m": "4", "t": "9"}},
                gpa="2.90",
                competency="Grade C (Good)",
                council_rank=str(i + 1),
            )
            for i in range(rows)
        ],
    )


# --------------------------------------------------------------------------- #
# the documented type table is the real one
# --------------------------------------------------------------------------- #
def test_every_documented_report_type_has_a_schema_and_a_renderer():
    documented = {
        "school_result_slip", "best_students", "best_students_subjectwise",
        "schools_rank", "top_schools", "subjects_rank", "subject_school_rank",
        "wards_rank", "district_performance", "mock_mobility", "generic",
    }
    assert documented <= set(RENDERERS), "a documented type has no renderer"
    # every type except the subjectwise alias is routable to a schema class
    for report_type in documented - {"best_students_subjectwise"}:
        assert report_type in schema.SCHEMA_BY_TYPE, report_type


def test_the_worked_example_from_the_documentation_renders():
    report = _schools_rank(120)
    html = template_maker.render_html("schools_rank", report, grow=True)
    assert html.startswith("<!DOCTYPE html>")
    assert PG in html
    assert "SCHOOL NUMBER 1" in html


# --------------------------------------------------------------------------- #
# shape: round-trip, and dict/JSON construction
# --------------------------------------------------------------------------- #
def test_schema_round_trips_through_dict_and_json():
    report = _schools_rank(3)
    again = schema.from_dict(schema.to_dict(report))
    assert isinstance(again, schema.SchoolsRankReport)
    assert [r.school_name for r in again.rows] == [r.school_name for r in report.rows]
    assert again.rows[0].registered.t == "58"
    assert again.rows[0].division["I"]["t"] == "9"

    from_json = schema.from_json(schema.to_json(report))
    assert schema.to_dict(from_json) == schema.to_dict(report)


def test_report_type_is_taken_from_meta_when_not_given():
    report = _schools_rank(2)
    assert template_maker.make(report).startswith("<!DOCTYPE html>")


# --------------------------------------------------------------------------- #
# layout resolution, exactly as documented in §3
# --------------------------------------------------------------------------- #
def test_an_exact_document_name_wins():
    assert layout_spec.resolve("MWANZA CC SCHOOLS RANK") == "MWANZA CC SCHOOLS RANK"


def test_a_layout_can_be_selected_by_kind():
    chosen = layout_spec.resolve(None, report_type="best_students")
    assert chosen in layout_spec.available()
    narrowed = layout_spec.resolve(
        None, report_type="best_students", level="region", variant="subjectwise"
    )
    assert narrowed == "Mwanza Best students-Subjectwise"


def test_an_unknown_name_falls_back_to_its_kind():
    assert layout_spec.resolve(
        "SOME COUNCIL NOBODY HAS SEEN", report_type="schools_rank", level="council"
    ) in layout_spec.available()


def test_an_unresolvable_layout_raises_and_lists_what_exists():
    with pytest.raises(layout_spec.LayoutSpecMissing) as excinfo:
        layout_spec.resolve("nope", report_type="primary_school_rank")
    assert "Available report_type/level/variant" in str(excinfo.value)


def test_the_catalogue_describes_every_bundled_layout():
    entries = layout_spec.catalogue()
    assert len(entries) == len(layout_spec.available()) == 19
    for entry in entries:
        assert entry["layout"] and entry["report_type"] and entry["level"]


# --------------------------------------------------------------------------- #
# the competency table in the documentation is the real mapping
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "label,colour",
    [
        ("Grade A (Excellent)", "#00b050"),
        ("Grade B (Very Good)", "#92d050"),
        ("Grade C (Good)", "#ffff00"),
        ("Grade D (Satisfactory)", "#ffc000"),
        ("Grade F (Fail)", "#ff0000"),
        ("Weak", "#ff0000"),
        ("Failed", "#ff0000"),
        ("EXCELLENT", "#00b050"),
        ("A", "#00b050"),
    ],
)
def test_documented_competency_colours(label, colour):
    assert competency.background_for(label=label) == colour


def test_a_gpa_is_used_when_the_label_is_unrecognised():
    assert competency.background_for(label="no such band", gpa=1.2)


def test_competency_colour_is_derived_not_supplied():
    """The colour must come from the label, and appear in the output."""
    report = _schools_rank(40)
    for row in report.rows:
        row.competency = "Grade A (Excellent)"
    html = template_maker.render_html("schools_rank", report, grow=True)
    assert competency.background_for(label="Grade A (Excellent)") in html


# --------------------------------------------------------------------------- #
# mode: grow, exactly as the documentation's table says
# --------------------------------------------------------------------------- #
def test_grow_false_keeps_the_reference_page_count_and_drops_surplus():
    layout = layout_spec.resolve(None, report_type="schools_rank", level="council")
    reference_pages = len(layout_spec.load(layout)["pages"])
    html = template_maker.render_html("schools_rank", _schools_rank(400))
    assert html.count(PG) == reference_pages


def test_grow_true_renders_every_supplied_row():
    report = _schools_rank(150)
    html = template_maker.render_html("schools_rank", report, grow=True)
    drawn = {int(m) for m in re.findall(r"SCHOOL NUMBER (\d+)", html)}
    assert drawn == set(range(1, 151)), "a supplied row was dropped"


def test_less_data_needs_no_flag():
    layout = layout_spec.resolve(None, report_type="schools_rank", level="council")
    reference_pages = len(layout_spec.load(layout)["pages"])
    for rows in (0, 1, 5):
        html = template_maker.render_html("schools_rank", _schools_rank(rows))
        assert html.count(PG) == reference_pages


# --------------------------------------------------------------------------- #
# header-driven data, as documented for GenericTabularReport
# --------------------------------------------------------------------------- #
def test_dict_and_json_data_render_identically_to_objects():
    """Supplying data as JSON must not change the output.

    ``GenericTabularReport.sections`` used to round-trip as plain dicts, because
    ``TabularSection`` was missing from the schema's nested-type map, so a caller
    who supplied JSON got a *different* document from one who built objects.
    """
    from sars import sources
    from sars.extract import extract_document
    from sars.extract_data import extract_report

    pair = next((p for p in sources.discover() if p.name == "MWANZA CC Wards Rank"), None)
    if pair is None:  # pragma: no cover
        pytest.skip("reference data not available")
    fresh = extract_report(extract_document(pair.pdf, pair.html), pair.name)
    revived = schema.from_json(schema.to_json(fresh))

    assert all(isinstance(s, schema.TabularSection) for s in revived.sections)
    rtype = fresh.meta.report_type
    assert template_maker.render_html(rtype, revived) == template_maker.render_html(
        rtype, fresh
    )


def test_the_layout_publishes_the_field_paths_it_reads():
    """A caller can discover the required keys instead of guessing them."""
    contract = layout_spec.data_contract("MWANZA CC Wards Rank")
    assert contract, "the wards layout binds no columns"
    fields = contract[0]["fields"]
    assert fields[1] == "NO. OF / WARDS IN / COUNCIL"
    assert fields[8] == "DIVISION PERFORMANCE / I-III / TOTAL"


def test_header_keyed_sections_find_their_columns_using_the_published_paths():
    """Header-driven data binds when it uses the reference's own header labels.

    A generic report's bands bind to ``section<N>`` groups, so the data must be
    supplied as ``sections`` in the same order — the second section fills the
    second table.
    """
    layout = "MWANZA CC Wards Rank"
    contract = layout_spec.data_contract(layout)
    # the ranked table is the band bound to section1
    band = next(entry for entry in contract if entry["group"] == "section1")
    headers = [band["fields"][i] for i in sorted(band["fields"])]

    report = schema.GenericTabularReport(
        meta=_meta(report_type="wards_rank", name=layout),
        column_headers=headers,
        sections=[
            schema.TabularSection(column_headers=[], rows=[]),          # section0
            schema.TabularSection(                                      # section1
                column_headers=headers,
                rows=[schema.TabularRow(values={headers[1]: "NYAMAGANA"})],
            ),
        ],
    )
    html = template_maker.render_html("wards_rank", report)
    assert "NYAMAGANA" in html


def test_invented_keys_bind_to_nothing_rather_than_guessing():
    """A key the layout does not know must not be silently placed somewhere."""
    report = schema.GenericTabularReport(
        meta=_meta(report_type="wards_rank", name="MWANZA CC Wards Rank"),
        column_headers=["WARD", "GPA"],
        rows=[schema.TabularRow(values={"WARD": "ZZZ-NOT-A-REAL-KEY", "GPA": "9.99"})],
    )
    html = template_maker.render_html("wards_rank", report)
    assert "ZZZ-NOT-A-REAL-KEY" not in html


def test_best_students_sections_are_independent_tables():
    students = [
        schema.StudentRow(
            cno=f"S5344-{i:04d}", name=f"CANDIDATE NUMBER {i}", sex="F",
            aggregate="7", division="I", position=str(i), school_name="MUSABE GIRLS",
            detailed_subjects="HTM - 97'A' BUSI - 80'A'",
        )
        for i in range(1, 11)
    ]
    report = schema.BestStudentsReport(
        meta=_meta(report_type="best_students", name="MWANZA CC 10 BEST STUDENTS"),
        sections=[
            schema.BestStudentsSection(title="TOP TEN BEST STUDENTS", students=students),
            schema.BestStudentsSection(title="TOP TEN BEST FEMALE STUDENTS", students=students),
        ],
    )
    html = template_maker.render_html("best_students", report)
    # both tables carry a body: the candidate appears in each section's band
    assert html.count("CANDIDATE NUMBER 1<") >= 2


def test_an_empty_section_still_prints_its_shell():
    report = schema.BestStudentsReport(
        meta=_meta(report_type="best_students", name="MWANZA CC 10 BEST STUDENTS"),
        sections=[
            schema.BestStudentsSection(title="TOP TEN BEST STUDENTS", students=[]),
            schema.BestStudentsSection(title="TOP TEN BEST FEMALE STUDENTS", students=[]),
        ],
    )
    html = template_maker.render_html("best_students", report)
    assert PG in html
