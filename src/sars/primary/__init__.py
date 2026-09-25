"""Primary school reports — registered, not yet implemented.

This package exists so that primary school work is an *addition* and never a
restructure. It is deliberately empty of behaviour: importing it succeeds, and
asking :mod:`sars.stages` for it reports a planned stage rather than crashing, so
the seam can be tested before there is anything behind it.

To implement this stage, add — mirroring :mod:`sars.secondary`, and changing
nothing outside this package:

1. ``reports.py`` — the document catalogue: one entry per source document giving
   its ``report_type``, ``level`` and ``variant``, plus a ``spec_for(name)`` that
   classifies a name that is not catalogued.
2. ``templates/`` — a renderer per ``report_type``, registered in a ``RENDERERS``
   mapping, and ``templates/layouts/<document>.json.gz`` holding each document's
   recovered geometry (build them with ``tools/build_layout_specs.py``).
3. ``competency.py`` — a ``background_for(label=None, gpa=None)`` for this
   stage's own grading scale. Primary is **not** assumed to share secondary's
   bands or GPA cut-offs; that is precisely why it lives per stage.
4. Set ``STAGE`` below to a real :class:`~sars.stages.Stage` with
   ``planned=False``.

What must NOT be duplicated: the drawing mechanism. :mod:`sars.layout`,
:mod:`sars.layout_spec`, :mod:`sars.fonts`, :mod:`sars.printing`,
:mod:`sars.binding` and :mod:`sars.schema` are stage-agnostic and already work
for any stage. If something there needs a change to fit primary, that is a signal
it was secondary-specific and belongs in a stage package instead.

If a primary report needs data fields secondary has no use for, add a schema
dataclass in :mod:`sars.schema` and register it in ``SCHEMA_BY_TYPE``. The schema
module is shared on purpose: it describes *data*, and data has no stage.
"""

from __future__ import annotations

from pathlib import Path

from ..stages import Stage

#: Where this stage's recovered layouts will live. Absent until the stage exists.
LAYOUTS = Path(__file__).resolve().parent / "templates" / "layouts"

#: Registered but unimplemented: ``planned=True`` keeps it out of the resolvers
#: while still letting :mod:`sars.stages` describe it.
STAGE = Stage(
    name="primary",
    layouts=LAYOUTS,
    renderers={},
    catalogue={},
    spec_for=lambda name: None,
    background_for=lambda label=None, gpa=None: None,
    planned=True,
)

__all__ = ["LAYOUTS", "STAGE"]
