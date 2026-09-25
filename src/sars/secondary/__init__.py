"""Secondary school reports: the Form Two mock assessment documents.

This package owns everything that is true of *secondary* reports and of nothing
else:

* :mod:`sars.secondary.reports` — which documents exist and how each is
  classified (``report_type`` / ``level`` / ``variant``);
* :mod:`sars.secondary.templates` — a renderer per report type, and the recovered
  layout spec per document under ``templates/layouts/``;
* :mod:`sars.secondary.competency` — the competency bands and the GPA cut-offs
  this stage grades on.

The drawing mechanism it renders with (:mod:`sars.layout`,
:mod:`sars.layout_spec`, :mod:`sars.fonts`, :mod:`sars.printing`) is deliberately
*not* here: it is stage-agnostic and shared. See :mod:`sars.stages` for why the
line falls where it does.
"""

from __future__ import annotations

from pathlib import Path

from ..stages import Stage
from .competency import background_for
from .reports import CATALOGUE, spec_for
from .templates import RENDERERS

#: This stage's recovered layout specs, one per source document.
LAYOUTS = Path(__file__).resolve().parent / "templates" / "layouts"

#: The stage descriptor :mod:`sars.stages` hands out.
STAGE = Stage(
    name="secondary",
    layouts=LAYOUTS,
    renderers=RENDERERS,
    catalogue=CATALOGUE,
    spec_for=spec_for,
    background_for=background_for,
    planned=False,
)

__all__ = ["CATALOGUE", "LAYOUTS", "RENDERERS", "STAGE", "background_for", "spec_for"]
