"""The public API: supply data and a report type, get HTML or a PDF back.

This is the whole surface a caller needs after ``pip install sars-convert``:

    >>> from sars import api
    >>> pdf_bytes = api.render_pdf(my_data, report_type="schools_rank")

Everything else in the package is machinery behind these functions.

Design notes worth knowing before you use it:

* **Data may be objects, dicts or JSON.** All three are accepted and produce
  identical output; see :mod:`sars.schema` and ``docs/DATA_STRUCTURE.md``.
* **Fonts are checked, never substituted.** Each entry point registers the
  bundled reference faces first and raises if any is unavailable, because a
  substituted face silently costs ~12 points of fidelity. Pass
  ``check_fonts=False`` only when you have deliberately arranged them yourself.
* **``grow`` decides the job.** The default (``False``) reproduces the reference
  document's exact pages and rows. ``grow=True`` renders *all* of your data,
  continuing onto further pages as needed. The distinction matters and is
  explained in ``docs/DATA_STRUCTURE.md`` §4.
* **A layout is never silently substituted.** If nothing matches the report you
  asked for, :class:`~sars.layout_spec.LayoutSpecMissing` is raised listing what
  is available, rather than printing your data in the shape of a different
  report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import fontsetup, layout_spec, schema, stages, template_maker

__all__ = [
    "UnknownReportType",
    "available_reports",
    "data_contract",
    "render_html",
    "render_pdf",
    "report_types",
]


def _coerce_data(data: Any, report_type: str | None) -> Any:
    """Accept a schema instance, a ``dict``, or a JSON string, uniformly."""
    if isinstance(data, str | bytes):
        data = json.loads(data)
    if isinstance(data, dict):
        return schema.from_dict(data, report_type=report_type)
    return data


class UnknownReportType(KeyError):
    """Raised when a report type this stage cannot render is asked for.

    Deliberately not a silent fall back to the generic table renderer: that would
    return *a* document, styled nothing like the report requested, and the caller
    would have no way to tell.
    """

    def __str__(self) -> str:  # KeyError quotes its argument; this reads better
        return self.args[0] if self.args else ""


def _resolved_type(data: Any, report_type: str | None, stage: str | None) -> str:
    known = stages.get(stage).renderers
    if report_type:
        if report_type not in known:
            raise UnknownReportType(
                f"stage {stages.get(stage).name!r} cannot render report_type "
                f"{report_type!r}. Available: {', '.join(sorted(known))}"
            )
        return report_type
    meta = getattr(data, "meta", None)
    from_meta = getattr(meta, "report_type", "") if meta is not None else ""
    if from_meta:
        if from_meta not in known:
            raise UnknownReportType(
                f"the data's meta.report_type is {from_meta!r}, which stage "
                f"{stages.get(stage).name!r} cannot render. "
                f"Available: {', '.join(sorted(known))}"
            )
        return from_meta
    return schema.TYPE_BY_SCHEMA.get(type(data), "generic")


def render_html(
    data: Any,
    report_type: str | None = None,
    *,
    stage: str | None = None,
    grow: bool = False,
    check_fonts: bool = True,
) -> str:
    """Render *data* to a standalone HTML document.

    ``data`` is a :mod:`sars.schema` instance, a ``dict`` from
    :func:`sars.schema.to_dict`, or a JSON string of the same. ``report_type``
    selects the report; when omitted it is taken from ``data.meta.report_type``.
    ``stage`` selects the education stage (default: secondary). ``grow`` renders
    every supplied row rather than reproducing the reference's row count.

    The returned document is self-contained: one inline stylesheet, no external
    references, and no shared cross-report CSS.
    """
    if check_fonts:
        fontsetup.ensure()
    data = _coerce_data(data, report_type)
    resolved = _resolved_type(data, report_type, stage)
    return template_maker.render_html(resolved, data, grow=grow)


def render_pdf(
    data: Any,
    report_type: str | None = None,
    out_path: str | Path | None = None,
    *,
    stage: str | None = None,
    grow: bool = False,
    check_fonts: bool = True,
) -> Path | bytes:
    """Render *data* to a PDF, printed at the reference's own page size.

    Returns the :class:`~pathlib.Path` written when ``out_path`` is given, and the
    PDF ``bytes`` otherwise. Arguments are as for :func:`render_html`.
    """
    if check_fonts:
        fontsetup.ensure()
    data = _coerce_data(data, report_type)
    resolved = _resolved_type(data, report_type, stage)
    return template_maker.render_pdf(resolved, data, out_path, grow=grow)


def report_types(stage: str | None = None) -> list[str]:
    """Every ``report_type`` this stage can render."""
    return sorted(stages.get(stage).renderers)


def available_reports(stage: str | None = None) -> list[dict[str, str]]:
    """Every layout that can be rendered, with the descriptor that selects it.

    Each entry gives ``layout`` (the document its geometry came from), ``stage``,
    ``report_type``, ``level`` and ``variant`` — the vocabulary
    :func:`render_html` and :func:`render_pdf` accept.
    """
    entries = layout_spec.catalogue()
    if stage:
        entries = [entry for entry in entries if entry["stage"] == stage]
    return entries


def data_contract(layout: str) -> list[dict[str, Any]]:
    """The field paths *layout* will read, per band.

    Use this instead of guessing key names for the header-driven reports, whose
    bindings name each column by the reference's own header label. See
    ``docs/DATA_STRUCTURE.md`` §2.
    """
    return layout_spec.data_contract(layout)
