"""School result slip — the school's own recovered fixed layout, filled from data.

The slip is unlike every other document: a cyan panel, a division summary, a
per-candidate table continuing over many pages and a performance block. All of
that geometry lives in ``layouts/S1051-MKOLANI SECONDARY SCHOOL.json``, recovered
from its reference PDF; this module supplies the data.
"""

from __future__ import annotations

from ...layout_spec import binding_provider, render_html, resolve
from ...schema import SchoolResultSlip


def render_school_result_slip(
    report: SchoolResultSlip,
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
