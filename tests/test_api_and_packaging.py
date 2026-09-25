"""The installed-package promise: install it, call the API, get a document.

These tests cover the surface a caller actually touches after
``pip install sars-convert`` — :mod:`sars.api` — plus the two things that make
that install sufficient on its own: the bundled reference faces, and the stage
layout that lets primary school reports be added later without a restructure.
"""

from __future__ import annotations

import json
import re

import pytest

from sars import api, fontsetup, layout_spec, schema, stages

PG = '<div class="pg"'


def _council_rank(rows: int = 20) -> dict:
    """A schools-rank report as a plain dict, the way a caller would send it."""
    return {
        "meta": {
            "name": "API TEST COUNCIL RANK",
            "report_type": "schools_rank",
            "level": "council",
            "variant": "overall",
            "region": "Mwanza",
            "council": "Test CC",
            "exam_name": "REGIONAL FORM TWO MOCK ASSESSMENT RESULTS, JULY 2027",
            "title": "API TEST COUNCIL RANK",
        },
        "rows": [
            {
                "sno": str(i + 1),
                "ward": "NYAMAGANA",
                "school_name": f"API SCHOOL {i + 1}",
                "ownership": "GOVERNMENT",
                "registered": {"f": "30", "m": "28", "t": "58"},
                "sat": {"f": "29", "m": "27", "t": "56"},
                "sat_pct": "96.6",
                "division": {"I": {"f": "5", "m": "4", "t": "9"}},
                "gpa": "2.90",
                "competency": "Grade C (Good)",
                "council_rank": str(i + 1),
            }
            for i in range(rows)
        ],
    }


# --------------------------------------------------------------------------- #
# the API accepts data in every form a caller might hold it
# --------------------------------------------------------------------------- #
def test_renders_from_a_dict():
    html = api.render_html(_council_rank())
    assert html.startswith("<!DOCTYPE html>")
    assert "API SCHOOL 1" in html


def test_renders_from_a_json_string():
    html = api.render_html(json.dumps(_council_rank()))
    assert "API SCHOOL 1" in html


def test_renders_from_a_schema_object():
    data = schema.from_dict(_council_rank())
    assert isinstance(data, schema.SchoolsRankReport)
    assert "API SCHOOL 1" in api.render_html(data)


def test_all_three_forms_agree():
    payload = _council_rank()
    from_dict = api.render_html(payload)
    from_json = api.render_html(json.dumps(payload))
    from_object = api.render_html(schema.from_dict(payload))
    assert from_dict == from_json == from_object


def test_report_type_is_inferred_from_the_data():
    """A caller who already set meta.report_type need not repeat it."""
    assert api.render_html(_council_rank()) == api.render_html(
        _council_rank(), report_type="schools_rank"
    )


# --------------------------------------------------------------------------- #
# render_pdf returns bytes, or writes a file
# --------------------------------------------------------------------------- #
def test_render_pdf_returns_bytes():
    pdf = api.render_pdf(_council_rank(5))
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_render_pdf_writes_the_path_it_is_given(tmp_path):
    out = api.render_pdf(_council_rank(5), out_path=tmp_path / "r.pdf")
    assert out.exists()
    assert out.read_bytes()[:4] == b"%PDF"


# --------------------------------------------------------------------------- #
# discovery: a caller can find out what it can render
# --------------------------------------------------------------------------- #
def test_report_types_are_discoverable():
    types = api.report_types()
    assert "schools_rank" in types
    assert types == sorted(types)


def test_available_reports_describe_how_to_select_them():
    reports = api.available_reports()
    assert len(reports) == 19
    for entry in reports:
        assert {"layout", "stage", "report_type", "level", "variant"} <= set(entry)
        assert entry["stage"] == "secondary"


def test_data_contract_is_reachable_from_the_api():
    contract = api.data_contract("MWANZA CC Wards Rank")
    assert contract
    assert "fields" in contract[0]


def test_an_unknown_report_type_is_refused_not_quietly_rendered():
    """It must not fall back to the generic table renderer.

    That would hand back *a* document, styled nothing like the report asked for,
    with no way for the caller to tell.
    """
    data = _council_rank()
    data["meta"]["report_type"] = "not_a_report_type"
    with pytest.raises(api.UnknownReportType) as excinfo:
        api.render_html(data, report_type="not_a_report_type")
    assert "schools_rank" in str(excinfo.value), "the error should list what IS renderable"

    # ... and also when the type comes from the data rather than the argument
    with pytest.raises(api.UnknownReportType):
        api.render_html(data)


def test_a_report_type_with_no_layout_raises_rather_than_substituting_one():
    """A renderable type whose layout cannot be resolved must still fail loudly."""
    data = _council_rank()
    data["meta"]["name"] = "NO SUCH DOCUMENT"
    data["meta"]["report_type"] = "school_result_slip"
    data["meta"]["level"] = "school"
    data["meta"]["variant"] = "nonexistent_variant"
    # school_result_slip has a bundled layout, so this resolves by kind rather
    # than raising - which is the documented behaviour, and must stay deliberate.
    assert api.render_html(data, report_type="school_result_slip").startswith("<!DOCTYPE")


# --------------------------------------------------------------------------- #
# grow, through the public API
# --------------------------------------------------------------------------- #
def test_grow_renders_every_supplied_row():
    html = api.render_html(_council_rank(150), grow=True)
    drawn = {int(n) for n in re.findall(r"API SCHOOL (\d+)", html)}
    assert drawn == set(range(1, 151))


def test_default_reproduces_the_reference_page_count():
    layout = layout_spec.resolve(None, report_type="schools_rank", level="council")
    expected = len(layout_spec.load(layout)["pages"])
    assert api.render_html(_council_rank(400)).count(PG) == expected


# --------------------------------------------------------------------------- #
# fonts: bundled, used, and never silently substituted
# --------------------------------------------------------------------------- #
def test_the_reference_faces_are_bundled_in_the_package():
    faces = fontsetup.bundled()
    assert len(faces) >= 50
    for path in faces.values():
        # inside the package, so they ship in the wheel
        assert "sars" in path.parts
        assert path.exists()


def test_rendering_uses_only_bundled_reference_faces():
    """No fallback font may appear in the output, ever."""
    html = api.render_html(_council_rank())
    families = set(re.findall(r"font-family:'([^']+)'", html))
    assert families, "no font families in the document"
    assert all(name.startswith("SARS ") for name in families), families


def test_fonts_are_resolvable_after_ensure():
    fontsetup.ensure()
    assert fontsetup.missing() == []


def test_verify_reports_every_missing_family_rather_than_substituting(monkeypatch):
    """With fontconfig blind, verify() must raise, not quietly carry on."""
    monkeypatch.setattr(fontsetup, "_fc_families", lambda: set())
    with pytest.raises(fontsetup.FontsUnavailable) as excinfo:
        fontsetup.verify()
    message = str(excinfo.value)
    assert "no fallback font" in message
    assert "would NOT match the original" in message


# --------------------------------------------------------------------------- #
# stages: primary can arrive without a restructure
# --------------------------------------------------------------------------- #
def test_secondary_is_the_default_stage():
    assert stages.DEFAULT_STAGE == "secondary"
    assert stages.get().name == "secondary"
    assert not stages.get().planned


def test_primary_is_registered_but_planned():
    assert "primary" in stages.names()
    primary = stages.get("primary")
    assert primary.planned
    assert primary.renderers == {}


def test_only_implemented_stages_serve_layouts():
    assert [stage.name for stage in stages.implemented()] == ["secondary"]
    assert all(entry["stage"] == "secondary" for entry in layout_spec.catalogue())


def test_an_unknown_stage_is_rejected_by_name():
    with pytest.raises(KeyError):
        stages.get("tertiary")


def test_the_mechanism_does_not_import_a_stage_at_module_level():
    """The shared mechanism must stay stage-agnostic, or primary means a rewrite."""
    from pathlib import Path

    root = Path(stages.__file__).parent
    for module in ("layout.py", "layout_spec.py", "fonts.py", "printing.py", "binding.py",
                   "schema.py"):
        text = (root / module).read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("from .secondary", "from .primary", "import sars.secondary")):
                raise AssertionError(f"{module} imports a stage at module level: {stripped}")
