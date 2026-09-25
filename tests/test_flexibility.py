"""Flexibility: LESS and MORE data than the 19 bundled examples.

These tests exercise the *mechanism* at the extremes — the longest plausible
student name, the longest council name, a detailed-results string far longer than
the reference ever carried, more rows than a page can hold, fewer rows, and an
empty section — and assert STRUCTURAL correctness on the positioned output
(the pixel gate lives in ``tests/test_fidelity_gate.py``).

Two invariants carry the whole design, and most tests below are one of them:

1. **Reproduction is inert.** With the default ``grow=False`` a document gets
   exactly the reference's pages and exactly the reference's rows. Nothing in the
   overflow policy may fire for a value the reference itself printed, which is
   what makes it impossible for this feature to move the fidelity gate.
2. **A value is absorbed where it is drawn.** An over-long value is condensed —
   and only if that is not enough, truncated — so it never overhangs its
   neighbour and never changes a row height, a row pitch or the page count.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from sars import fonts, layout_spec, sources, template_maker
from sars.layout import MIN_CONDENSE, Box, Canvas, StyleBook
from sars.secondary.competency import background_for

BEST = "MWANZA CC 10 BEST STUDENTS"
RANK = "MWANZA CC SCHOOLS RANK"

#: A run with an explicit horizontal squeeze, and one without.
_CONDENSED = re.compile(
    r'<t class="t\d+" style="left:([\d.-]+)pt;top:([\d.-]+)pt;'
    r'transform-origin:0 0;transform:scaleX\(([\d.]+)\)">([^<]*)</t>'
)
_PLAIN = re.compile(r'<t class="t\d+" style="left:([\d.-]+)pt;top:([\d.-]+)pt">([^<]*)</t>')
_PAGE = '<div class="pg"'

LONG_NAME = "MUHAMMADI ABDULRAHMANI SULEIMANI KIPANGA MWANANCHI WA JAMHURI HABIBU"
LONG_COUNCIL = "MWANZA CITY COUNCIL AND METROPOLITAN GREATER MUNICIPAL AUTHORITY OF THE LAKE"
LONG_SUBJECTS = (
    "HTM - 97'A' BUSI - 80'A' GEO - 91'A' KISW - 85'A' ENGL - 78'A' PHY - 88'A' "
    "CHEM - 93'A' BIO - 90'A' MATH - 84'A' HIST - 77'A' CIVICS - 82'A' "
    "FRENCH - 70'B' COMMERCE - 66'C' AGRIC - 61'C' FOOD - 59'D' MUSIC - 55'D'"
)


def _report(name: str):
    """The extracted report for *name*, from the reference pair."""
    pair = next((p for p in sources.discover() if p.name == name), None)
    if pair is None:  # pragma: no cover - data not unpacked
        pytest.skip(f"reference data for {name!r} is not available")
    from sars.extract import extract_document
    from sars.extract_data import extract_report

    return extract_report(extract_document(pair.pdf, pair.html), name)


def _pages(html: str) -> int:
    return html.count(_PAGE)


def _spec_pages(name: str) -> int:
    return len(layout_spec.load(name)["pages"])


# --------------------------------------------------------------------------- #
# 1. the overflow policy is a NO-OP for anything that fits
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("align", ["left", "center", "right"])
def test_a_value_that_fits_is_placed_exactly_as_before(align):
    """No squeeze, no truncation, and the x the alignment always produced."""
    canvas = Canvas(BEST, 792.0, 612.0, book=StyleBook())
    box = Box(100.0, 50.0, 60.0, 10.0)
    canvas.cell_text(
        box, "JOHN", role="arial", size=7.0, baseline=57.0, align=align, pad=1.0
    )
    (run,) = canvas._texts
    assert "scaleX" not in run, "a fitting value must not be condensed"
    assert ">JOHN</t>" in run, "a fitting value must not be truncated"


def test_every_reference_report_keeps_the_reference_page_count():
    """The default path may never change how many pages a report has."""
    for pair in sources.discover():
        data = _report(pair.name)
        html = template_maker.render_html(
            getattr(data.meta, "report_type", "generic"), data
        )
        assert _pages(html) == _spec_pages(pair.name), pair.name


# --------------------------------------------------------------------------- #
# 2. over-long values are absorbed inside the room the reference used
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("align", ["left", "center", "right"])
@pytest.mark.parametrize(
    "text", [LONG_NAME, LONG_COUNCIL, LONG_SUBJECTS, "X" * 400], ids=
    ["name", "council", "subjects", "absurd"]
)
def test_an_over_long_value_never_leaves_its_cell(text, align):
    """However long the value, what is drawn fits the cell it is drawn in."""
    canvas = Canvas(BEST, 792.0, 612.0, book=StyleBook())
    box = Box(100.0, 50.0, 60.0, 10.0)
    canvas.cell_text(
        box, text, role="arial", size=7.0, baseline=57.0, align=align, pad=1.0
    )
    (markup,) = canvas._texts
    left = float(re.search(r"left:([\d.-]+)pt", markup).group(1))
    squeeze = re.search(r"scaleX\(([\d.]+)\)", markup)
    factor = float(squeeze.group(1)) if squeeze else 1.0
    drawn = re.search(r">([^<]*)</t>", markup).group(1)
    width = fonts.text_width(drawn, BEST, "arial", 7.0) * factor

    assert factor >= MIN_CONDENSE, "never condensed past the readable floor"
    assert width <= box.w + 0.01, f"drawn {width:.2f}pt exceeds the {box.w}pt cell"
    assert left >= box.x - 0.01, "run starts left of its cell"
    assert left + width <= box.right + 0.01, "run overhangs the next column"


def test_truncation_introduces_no_character_the_font_may_not_have():
    """Nothing is appended when a value is cut — no ellipsis, so no fallback font.

    The reference faces are subsets; a "…" would be drawn from some *other*
    family, and this project never allows a fallback font.
    """
    canvas = Canvas(BEST, 792.0, 612.0, book=StyleBook())
    canvas.cell_text(
        Box(100.0, 50.0, 30.0, 10.0), LONG_NAME, role="arial", size=7.0,
        baseline=57.0, align="left", pad=1.0,
    )
    drawn = re.search(r">([^<]*)</t>", canvas._texts[0]).group(1)
    assert LONG_NAME.startswith(drawn), "a cut value must be a prefix of the original"
    assert "…" not in drawn and "..." not in drawn


def test_a_value_may_use_the_room_the_reference_itself_used():
    """A reference cell that overhangs its own box keeps that room.

    ``Mwanza f2 Mock Mobility 2026`` draws ``GPA2.2969`` in a box far narrower
    than the string. Clamping to the box would be *less* faithful than the
    reference, so the budget is the wider of the cell and the reference's own run.
    """
    report = "Mwanza f2 Mock Mobility 2026"
    cell = layout_spec.load(report)["pages"][1]["bands"][0]["cells"][6]
    sample = str(cell["sample"])
    natural = fonts.text_width(sample, report, cell["role"], cell["size"])
    assert natural > cell["w"], "this cell is only interesting because it overhangs"

    canvas = Canvas(report, 612.0, 792.0, book=StyleBook())
    canvas.cell_text(
        Box(cell["x"], 100.0, cell["w"], 10.0), sample, role=cell["role"],
        size=cell["size"], baseline=107.0, align=cell.get("align", "center"),
        pad=cell.get("pad", 0.0), sample=sample,
    )
    assert "scaleX" not in canvas._texts[0], (
        "the reference's own value must not be squeezed out of its own cell"
    )


# --------------------------------------------------------------------------- #
# 3. LESS data
# --------------------------------------------------------------------------- #
def test_fewer_rows_keeps_the_page_count_and_drops_no_chrome():
    data = _report(RANK)
    full = template_maker.render_html("schools_rank", data)
    data.rows = data.rows[:4]
    short = template_maker.render_html("schools_rank", data)
    assert _pages(short) == _pages(full) == _spec_pages(RANK)
    assert len(_PLAIN.findall(short)) < len(_PLAIN.findall(full))


def test_an_empty_section_emits_no_rows_under_its_caption():
    data = _report(BEST)
    if len(data.sections) < 2:  # pragma: no cover
        pytest.skip("report has a single section")
    before = template_maker.render_html("best_students", data)
    data.sections[1].students = []
    after = template_maker.render_html("best_students", data)
    assert _pages(after) == _pages(before) == _spec_pages(BEST)
    assert len(_PLAIN.findall(after)) < len(_PLAIN.findall(before))


def test_no_data_at_all_still_produces_the_reference_shell():
    data = _report(RANK)
    data.rows = []
    html = template_maker.render_html("schools_rank", data)
    assert _pages(html) == _spec_pages(RANK)
    assert _PAGE in html


# --------------------------------------------------------------------------- #
# 4. MORE data - only with grow=True, and then nothing is dropped
# --------------------------------------------------------------------------- #
def _grown(name: str, data) -> str:
    return layout_spec.render_html(
        name, layout_spec.binding_provider(name, data), grow=True
    )


@pytest.mark.parametrize("extra", [1, 10, 60, 200])
def test_more_rows_are_all_rendered_when_growing(extra):
    data = _report(RANK)
    template = data.rows[-1]
    base = len(data.rows)
    for k in range(extra):
        data.rows.append(
            replace(template, sno=str(base + k + 1), school_name=f"EXTRA SCHOOL {k + 1}")
        )
    html = _grown(RANK, data)
    drawn = {m for m in re.findall(r"EXTRA SCHOOL \d+", html)}
    assert len(drawn) == extra, f"{extra - len(drawn)} supplied row(s) were dropped"
    assert _pages(html) >= _spec_pages(RANK)


def test_growing_adds_pages_only_as_the_data_requires():
    data = _report(RANK)
    reference_pages = _pages(_grown(RANK, data))
    template = data.rows[-1]
    for k in range(120):
        data.rows.append(replace(template, sno=str(1000 + k), school_name=f"EXTRA {k}"))
    assert _pages(_grown(RANK, data)) > reference_pages


def test_growing_is_off_by_default_so_reproduction_cannot_repaginate():
    """The guardrail in test form: extra data must not change the default render.

    ``MWANZA CC SCHOOLS RANK SUBJECTWISE`` is the report that proves why this
    default matters — its extracted ``section0`` holds 65 rows while the reference
    page prints 54, so a renderer that grew whenever the provider had more rows
    would turn a faithful 24-page reproduction into 30 pages.
    """
    name = "MWANZA CC SCHOOLS RANK SUBJECTWISE"
    data = _report(name)
    html = template_maker.render_html(
        getattr(data.meta, "report_type", "generic"), data
    )
    assert _pages(html) == _spec_pages(name) == 24


def test_a_grown_row_gets_its_competency_wash_derived():
    """A row the reference never had still gets the right competency colour."""
    data = _report(RANK)
    template = data.rows[-1]
    label = "Grade A (Excellent)"
    expected = background_for(label=label)
    assert expected, "the fixture label must resolve to a band"
    for k in range(80):
        data.rows.append(
            replace(template, sno=str(2000 + k), school_name=f"WASH {k}", competency=label)
        )
    html = _grown(RANK, data)
    assert expected in html, "the derived competency wash is missing"


# --------------------------------------------------------------------------- #
# 5. the extremes together, through the public template entry point
# --------------------------------------------------------------------------- #
def test_longest_name_and_subjects_together_stay_on_the_page():
    data = _report(BEST)
    reference = template_maker.render_html("best_students", data)
    page_w = float(re.search(r"@page\{size:([\d.]+)pt", reference).group(1))
    student = data.sections[0].students[0]
    data.sections[0].students[0] = replace(
        student, name=LONG_NAME, detailed_subjects=LONG_SUBJECTS
    )
    html = template_maker.render_html("best_students", data)
    assert _pages(html) == _spec_pages(BEST)
    for left, _top, _k, _text in _CONDENSED.findall(html):
        assert 0.0 <= float(left) <= page_w
    for left, _top, _text in _PLAIN.findall(html):
        assert 0.0 <= float(left) <= page_w


def test_longest_council_name_does_not_move_the_layout():
    data = _report(RANK)
    row = data.rows[0]
    data.rows[0] = replace(row, council=LONG_COUNCIL, school_name=LONG_COUNCIL)
    html = template_maker.render_html("schools_rank", data)
    assert _pages(html) == _spec_pages(RANK)
    assert "scaleX" in html, "an over-long council name should be condensed"
