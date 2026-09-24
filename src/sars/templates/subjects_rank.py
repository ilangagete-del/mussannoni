"""Subjects-rank reports — each document's own recovered fixed layout.

The council and region subject sheets rank every subject on its grade
distribution, GPA and competency; each keeps its own spec in
``layouts/<report>.json`` and this module supplies the rows.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import SubjectsRankReport


def render_subjects_rank(report: SubjectsRankReport, engine: str | None = None) -> str:
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
