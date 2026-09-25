"""Education stages: what is specific to secondary, primary, or any later stage.

Everything built so far reproduces **secondary** school reports (the Form Two
mock assessments). Primary school reports are coming, and they will bring their
own report types, their own recovered page layouts, and quite possibly their own
competency scale. This module is the seam that lets them arrive as an *addition*
rather than a rewrite.

The split is by **who owns the knowledge**, not by convenience:

``sars.<mechanism>`` — stage-agnostic, shared, and already correct for any stage
    :mod:`sars.layout` (place a box, place a baseline), :mod:`sars.layout_spec`
    (drive a recovered spec), :mod:`sars.fonts` (real faces and their advances),
    :mod:`sars.printing`, :mod:`sars.binding`, :mod:`sars.schema`. None of these
    know what a school is.

``sars.secondary`` / ``sars.primary`` — one stage's own knowledge
    Which reports exist and how they are classified, the recovered layouts, the
    renderers, and the competency bands. A stage owns its documents.

So adding primary means writing ``sars/primary/`` and registering it here. It
means changing nothing that already works, and renaming nothing.

Usage::

    from sars import stages

    stage = stages.get()                 # the default stage: secondary
    stage.renderers["schools_rank"]      # its renderers
    stage.layouts                        # its recovered layouts directory
    stages.names()                       # every registered stage
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The stage the package renders unless told otherwise. Secondary is the only
#: implemented stage; this constant is what a future caller flips or overrides,
#: and what keeps every existing call site meaning exactly what it means today.
DEFAULT_STAGE = "secondary"

#: Registered stage module names, in the order they are searched for a layout.
_STAGE_MODULES: dict[str, str] = {
    "secondary": "sars.secondary",
    "primary": "sars.primary",
}


@dataclass(frozen=True)
class Stage:
    """One education stage's own reports, layouts, renderers and scale."""

    #: Stage id (``secondary`` / ``primary``).
    name: str
    #: Directory holding this stage's recovered layout specs.
    layouts: Path
    #: ``report_type`` -> renderer callable.
    renderers: dict[str, Callable[..., str]]
    #: Document name -> classification (report_type / level / variant).
    catalogue: dict[str, Any]
    #: Classify a document name that is not in the catalogue.
    spec_for: Callable[[str], Any]
    #: Competency label / GPA -> background colour, on THIS stage's scale.
    background_for: Callable[..., str | None]
    #: True when the stage is registered but not yet implemented.
    planned: bool = False


class StageNotImplemented(NotImplementedError):
    """Raised when a registered stage has no implementation yet."""


def names() -> list[str]:
    """Every registered stage id, implemented or planned."""
    return list(_STAGE_MODULES)


def get(name: str | None = None) -> Stage:
    """The :class:`Stage` for *name*, defaulting to :data:`DEFAULT_STAGE`.

    Imported lazily: a stage's package imports the shared mechanism, and the
    mechanism asks for a stage, so eager imports here would be circular.
    """
    stage_name = name or DEFAULT_STAGE
    module_path = _STAGE_MODULES.get(stage_name)
    if module_path is None:
        raise KeyError(f"unknown stage {stage_name!r}; registered: {', '.join(names())}")

    from importlib import import_module

    module = import_module(module_path)
    stage = getattr(module, "STAGE", None)
    if stage is None:  # pragma: no cover - a stage package must define STAGE
        raise StageNotImplemented(f"{module_path} defines no STAGE")
    return stage


def implemented() -> list[Stage]:
    """Every stage that is actually usable, in search order."""
    found: list[Stage] = []
    for name in names():
        try:
            stage = get(name)
        except (StageNotImplemented, ImportError):
            continue
        if not stage.planned:
            found.append(stage)
    return found


def layout_dirs() -> list[Path]:
    """Every implemented stage's layouts directory, in search order.

    A layout is looked up across stages, so a primary layout becomes findable by
    registering the stage — no lookup code changes.
    """
    return [stage.layouts for stage in implemented() if stage.layouts.is_dir()]
