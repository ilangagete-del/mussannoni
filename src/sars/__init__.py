"""Reproduce Mwanza SARS result reports as HTML + CSS, printed to PDF.

Install it, hand it data and a report type, get a document back::

    from sars import api

    html = api.render_html(data, report_type="schools_rank")
    api.render_pdf(data, report_type="schools_rank", out_path="rank.pdf")

    api.report_types()        # what can be rendered
    api.available_reports()   # every layout, and how to select it

``api`` is the supported surface; see ``docs/DATA_STRUCTURE.md`` for the shape of
``data`` and ``docs/PACKAGING.md`` for how the reference fonts are shipped.

The package is organised so that a future education stage is an addition rather
than a rewrite (see :mod:`sars.stages`):

* stage-agnostic mechanism — :mod:`sars.layout`, :mod:`sars.layout_spec`,
  :mod:`sars.fonts`, :mod:`sars.printing`, :mod:`sars.binding`,
  :mod:`sars.schema`;
* one stage's own reports, layouts and grading scale — :mod:`sars.secondary`
  (and :mod:`sars.primary`, registered and awaiting implementation).

Importing :mod:`sars` deliberately pulls in nothing heavy: the PDF engine and the
font manifest load on first use.
"""

__version__ = "1.0.0"

__all__ = ["__version__", "api"]


def __getattr__(name: str):
    """Expose ``sars.api`` lazily, so ``import sars`` stays cheap.

    Uses :func:`importlib.import_module` rather than ``from . import api``: the
    latter re-enters this hook while the attribute is still unset, which recurses
    until the stack runs out.
    """
    if name == "api":
        import importlib

        module = importlib.import_module(f"{__name__}.api")
        globals()["api"] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
