"""Wards-rank pivot report — its own recovered fixed layout, filled from data.

This renderer owns the council wards report and nothing else. Its page box, its
column lattice, its row pitch, its fills, its fonts and its baselines come from
``layouts/MWANZA CC Wards Rank.json``, recovered from that report's reference PDF
by ``tools/build_layout_specs.py``; this module supplies only the *data*.

The report's shape: a two-row SUMMARY PERFORMANCE block (council totals and
``% PASS``), then the ranked wards table with a ``TOTAL`` row — one spec band
each, fed from the data's sections in order.
"""

from __future__ import annotations

from ..layout_spec import binding_provider, has_spec, render_html
from ..schema import GenericTabularReport

REPORT_NAME = "MWANZA CC Wards Rank"


def render_wards_rank(report: GenericTabularReport, engine: str | None = None) -> str:
    """Render the wards-rank report from its recovered layout plus this data."""
    name = report.meta.name or REPORT_NAME
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
