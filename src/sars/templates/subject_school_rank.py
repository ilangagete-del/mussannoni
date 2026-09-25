"""Single-subject school-rank reports — recovered fixed layout, filled from data.

Three documents share this *shape* (a portrait page ranking every school on one
subject's grade distribution, GPA and competency) but NOT a layout: the council
subjectwise sheet, the EDK sheet and the English Language sheet each keep their
own recovered spec under ``layouts/<report>.json``, with their own page count,
lattice, fills, fonts and row pitch. This module only feeds them data.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, render_html, resolve
from ..schema import GenericTabularReport


def render_subject_school_rank(
    report: GenericTabularReport,
    engine: str | None = None,
    *,
    grow: bool = False,
) -> str:
    """Render one subject's school ranking from its own recovered layout."""
    name = report.meta.name
    layout = resolve(
        name,
        report_type=report.meta.report_type,
        level=report.meta.level,
        variant=report.meta.variant,
    )
    return render_html(
        layout,
        binding_provider(layout, report),
        title=report.meta.title or name,
        engine=engine,
        grow=grow,
    )
