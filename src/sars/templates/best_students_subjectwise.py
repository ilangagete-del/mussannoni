"""Best-students (subjectwise) reports — each document's own recovered layout.

A subjectwise list ranks candidates *within one subject* on that subject's
``MARKS`` / ``GRADE`` / ``COMPETENCY LEVEL``, one block per subject. Each document's
blocks, lattice and fills come from its own ``layouts/<report>.json``.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import BestStudentsReport


def render_best_students_subjectwise(report: BestStudentsReport, engine: str | None = None) -> str:
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
