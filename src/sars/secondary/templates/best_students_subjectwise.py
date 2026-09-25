"""Best-students (subjectwise) reports — each document's own recovered layout.

A subjectwise list ranks candidates *within one subject* on that subject's
``MARKS`` / ``GRADE`` / ``COMPETENCY LEVEL``, one block per subject. Each document's
blocks, lattice and fills come from its own ``layouts/<report>.json``.
"""

from __future__ import annotations

from ...layout_spec import binding_provider, render_html, resolve
from ...schema import BestStudentsReport


def render_best_students_subjectwise(
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
