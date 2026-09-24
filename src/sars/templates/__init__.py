"""Report *templates*: render a FEAT-003 schema instance back to clean HTML.

Where the conversion pipeline (:mod:`sars.html_out`) redraws a *specific* PDF
faithfully - geometry, fonts and every recovered colour - a **template** does
the opposite job: it holds the *static chrome* of a report type (the ministry
banner, the fixed column headings, the ``TOTAL`` / ``% PASS`` row labels) once,
and is handed only the *data* (a schema instance from :mod:`sars.schema`) to
fill in. The same document can therefore be regenerated from data alone.

Each template is a small Python renderer (string assembly, mirroring
``html_out`` so there is no style drift and no new dependency) registered here
by ``report_type``. Templates are *named by level + purpose* - the name a caller
would pick a template file by - via :data:`TEMPLATE_NAMES`, with
private/overall/government handled as *variants* of one renderer where the
structure matches and separate renderers only where it genuinely differs.

The competency background colour is applied **deterministically** from the
competency label / GPA in the data via :mod:`sars.competency`, never stored.
"""

from __future__ import annotations

from collections.abc import Callable

from ..schema import (
    BestStudentsReport,
    GenericTabularReport,
    SchoolResultSlip,
    SchoolsRankReport,
    SubjectsRankReport,
)
from .best_students import render_best_students
from .best_students_subjectwise import render_best_students_subjectwise
from .generic import render_generic
from .school_result_slip import render_school_result_slip
from .schools_rank import render_schools_rank
from .subjects_rank import render_subjects_rank
from .top_schools import render_top_schools

#: report_type -> renderer callable ``(schema_instance) -> str`` (full HTML doc).
RENDERERS: dict[str, Callable[..., str]] = {
    "school_result_slip": render_school_result_slip,
    "schools_rank": render_schools_rank,
    "top_schools": render_top_schools,
    "best_students": render_best_students,
    "best_students_subjectwise": render_best_students_subjectwise,
    "subjects_rank": render_subjects_rank,
    "subject_school_rank": render_generic,
    "wards_rank": render_generic,
    "district_performance": render_generic,
    "mock_mobility": render_generic,
    "generic": render_generic,
}

#: schema class -> report_type, used by :func:`sars.template_maker.make` to infer
#: the report type from a schema instance when it is not given explicitly.
TYPE_BY_SCHEMA: dict[type, str] = {
    SchoolResultSlip: "school_result_slip",
    SchoolsRankReport: "schools_rank",
    BestStudentsReport: "best_students",
    SubjectsRankReport: "subjects_rank",
    GenericTabularReport: "generic",
}

#: Template *names* by level + purpose - the file/registry key a caller selects.
#: Where private/overall/government share a structure they are variants of one
#: template (one entry); only genuinely different structures get their own name.
#: The value is the ``report_type`` (and thus renderer) each name maps to.
TEMPLATE_NAMES: dict[str, str] = {
    # school level
    "school_result_slip": "school_result_slip",
    # council level
    "council_top_10_schools": "top_schools",
    "council_top_10_students": "best_students",
    "council_top_10_students_subjectwise": "best_students_subjectwise",
    "council_schools_rank": "schools_rank",
    "council_schools_rank_subjectwise": "subject_school_rank",
    "council_subjects_rank": "subjects_rank",
    "council_wards_rank": "wards_rank",
    # region level
    "region_top_10_schools": "top_schools",
    "region_best_students_overall": "best_students",
    "region_best_students_subjectwise": "best_students_subjectwise",
    "region_schools_rank_overall": "schools_rank",
    "region_schools_rank_government": "schools_rank",
    "region_subjects_rank_overall": "subjects_rank",
    "region_school_rank_subject": "subject_school_rank",
    "region_district_performance": "district_performance",
    "region_mock_mobility": "mock_mobility",
}


def renderer_for(report_type: str) -> Callable[..., str]:
    """Return the renderer for a report type, defaulting to the generic one."""
    return RENDERERS.get(report_type, render_generic)
