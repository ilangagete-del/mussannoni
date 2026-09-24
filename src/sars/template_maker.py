"""Template-maker API: supply report data, get styled HTML or a PDF back.

This is the callable entry point for the templated path built in FEAT-004. It
turns a FEAT-003 *data* schema instance (see :mod:`sars.schema`) into a clean,
self-contained HTML document via the templates in :mod:`sars.templates`, and can
print that HTML to an A4 PDF with WeasyPrint (:mod:`sars.render`).

Typical use::

    from sars import extract_data, template_maker
    from sars.extract import extract_document

    data = extract_data.extract_report(extract_document(pdf, html), name)
    html = template_maker.make(data)              # infer type from the schema
    pdf_bytes = template_maker.render_pdf(data.meta.report_type, data)

Three functions are exposed:

* :func:`render_html` - ``(report_type, data) -> str`` renders the HTML string;
* :func:`render_pdf`  - ``(report_type, data, out_path=None) -> Path | bytes``
  renders the HTML then prints it to PDF, returning the path it wrote or, when
  no path is given, the PDF bytes;
* :func:`make`        - ``(data) -> str`` a convenience that infers the report
  type from the schema instance's class and calls :func:`render_html`.

Each report type has its own expected *data shape*; the shape is the schema
class named for that type (documented on each template module and on the schema
dataclasses). The mapping report_type -> template is
:data:`sars.templates.RENDERERS`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from . import printing
from .templates import RENDERERS, TYPE_BY_SCHEMA, renderer_for


def _report_type_of(data: Any) -> str:
    """Infer the report_type from a schema instance (its ``meta`` or class).

    A ``meta.report_type`` (set by the extractor) is preferred, because it
    distinguishes families that share a schema class (``schools_rank`` vs
    ``top_schools``, or the several :class:`~sars.schema.GenericTabularReport`
    families). The schema class is the fallback.
    """
    meta = getattr(data, "meta", None)
    rtype = getattr(meta, "report_type", "") if meta is not None else ""
    if rtype and rtype in RENDERERS:
        return rtype
    return TYPE_BY_SCHEMA.get(type(data), "generic")


def render_html(report_type: str, data: Any, engine: str | None = None) -> str:
    """Render report *data* to a full, styled HTML document string.

    ``report_type`` selects the template (see :data:`sars.templates.RENDERERS`);
    ``data`` must be the schema instance that template expects - e.g.
    :class:`~sars.schema.SchoolsRankReport` for ``schools_rank`` /
    ``top_schools``, :class:`~sars.schema.SchoolResultSlip` for
    ``school_result_slip``, :class:`~sars.schema.BestStudentsReport` for
    ``best_students``, :class:`~sars.schema.SubjectsRankReport` for
    ``subjects_rank``, and :class:`~sars.schema.GenericTabularReport` for the
    header-driven families (``subject_school_rank`` / ``wards_rank`` /
    ``district_performance`` / ``mock_mobility`` / ``generic``).
    """
    renderer = renderer_for(report_type)
    if engine is None:
        return renderer(data)
    try:
        return renderer(data, engine=engine)
    except TypeError:
        # A renderer that does not take an engine prints the same HTML either
        # way; the engine only affects the baseline calibration.
        return renderer(data)


def render_pdf(
    report_type: str,
    data: Any,
    out_path: str | Path | None = None,
    engine: str | None = None,
) -> Path | bytes:
    """Render report *data* to a PDF (HTML then WeasyPrint).

    Returns the :class:`~pathlib.Path` written when ``out_path`` is given, or the
    PDF ``bytes`` otherwise. ``report_type`` and ``data`` are as for
    :func:`render_html`.
    """
    name = getattr(getattr(data, "meta", None), "name", "") or ""
    engine = engine or printing.engine_for(name)
    html_text = render_html(report_type, data, engine=engine)
    # A base_url lets the engine resolve any relative asset; the templates are
    # self-contained so a temp dir is enough.
    return printing.print_pdf(
        html_text, out_path, engine=engine, base_url=tempfile.gettempdir()
    )


def make(data: Any) -> str:
    """Infer the report type from *data* and render its HTML.

    A convenience wrapper over :func:`render_html` for callers that hold a schema
    instance and do not want to name its type: the type is taken from
    ``data.meta.report_type`` (falling back to the schema class).
    """
    return render_html(_report_type_of(data), data)
