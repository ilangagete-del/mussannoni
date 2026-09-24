"""Best-students (overall) reports — each document's own recovered layout.

An overall list ranks a candidate on ``AGGT`` / ``DIVISION`` and prints the
``DETAILED SUBJECTS`` breakdown. The council and region sheets each keep their own
spec in ``layouts/<report>.json``; this module only feeds the students in.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import BestStudentsReport


def render_best_students(report: BestStudentsReport, engine: str | None = None) -> str:
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
