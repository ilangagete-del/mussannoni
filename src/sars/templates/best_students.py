"""Best-students (overall) reports — each document's own recovered layout.

An overall list ranks a candidate on ``AGGT`` / ``DIVISION`` and prints the
``DETAILED SUBJECTS`` breakdown. The council and region sheets each keep their own
spec in ``layouts/<report>.json``; this module only feeds the students in.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, render_html, resolve
from ..schema import BestStudentsReport


def render_best_students(
    report: BestStudentsReport,
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
