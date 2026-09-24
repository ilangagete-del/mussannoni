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

from weasyprint import HTML

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


def render_html(report_type: str, data: Any) -> str:
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
    return renderer_for(report_type)(data)


def render_pdf(report_type: str, data: Any, out_path: str | Path | None = None) -> Path | bytes:
    """Render report *data* to a PDF (HTML then WeasyPrint).

    Returns the :class:`~pathlib.Path` written when ``out_path`` is given, or the
    PDF ``bytes`` otherwise. ``report_type`` and ``data`` are as for
    :func:`render_html`.
    """
    html_text = render_html(report_type, data)
    # A base_url lets WeasyPrint resolve any relative asset; the templates are
    # self-contained so a temp dir is enough.
    base = tempfile.gettempdir()
    document = HTML(string=html_text, base_url=base)
    if out_path is None:
        return document.write_pdf()
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document.write_pdf(str(target))
    return target


def make(data: Any) -> str:
    """Infer the report type from *data* and render its HTML.

    A convenience wrapper over :func:`render_html` for callers that hold a schema
    instance and do not want to name its type: the type is taken from
    ``data.meta.report_type`` (falling back to the schema class).
    """
    return render_html(_report_type_of(data), data)
