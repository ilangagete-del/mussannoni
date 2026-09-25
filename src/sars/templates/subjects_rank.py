"""Subjects-rank reports — each document's own recovered fixed layout.

The council and region subject sheets rank every subject on its grade
distribution, GPA and competency; each keeps its own spec in
``layouts/<report>.json`` and this module supplies the rows.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, render_html, resolve
from ..schema import SubjectsRankReport


def render_subjects_rank(
    report: SubjectsRankReport,
    engine: str | None = None,
    *,
    grow: bool = False,
) -> str:
    """Render this report from its own recovered layout plus the given data."""
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
