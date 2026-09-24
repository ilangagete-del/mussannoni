"""School result slip — the school's own recovered fixed layout, filled from data.

The slip is unlike every other document: a cyan panel, a division summary, a
per-candidate table continuing over many pages and a performance block. All of
that geometry lives in ``layouts/S1051-MKOLANI SECONDARY SCHOOL.json``, recovered
from its reference PDF; this module supplies the data.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import SchoolResultSlip


def render_school_result_slip(report: SchoolResultSlip, engine: str | None = None) -> str:
    """Render this report from its own recovered layout plus the given data."""
    name = report.meta.name
    if not has_spec(name):  # pragma: no cover - the spec ships with the repo
        raise RuntimeError(
            f"{name!r} has no recovered layout spec; run tools/build_layout_specs.py"
        )
    return render_html(
        name,
        binding_provider(name, report),
        title=report.meta.title or name,
        engine=engine,
    )
