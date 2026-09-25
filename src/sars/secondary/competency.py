"""Deterministic competency-level -> colour mapping for Mwanza mock reports.

Form Two mock assessment reports grade a school / subject / candidate on the
Tanzanian GPA competency scale. The GPA band determines both the competency
*label* and the deterministic cell *background colour* the reports paint that
label with:

======================  ========  ==================  ===========
GPA band                Grade     Competency label    Background
======================  ========  ==================  ===========
1.0 - 1.5               A         Excellent           ``#00b050``
1.6 - 2.5               B         Very Good           ``#92d050``
2.6 - 3.5               C         Good                ``#ffff00``
3.6 - 4.5               D         Satisfactory        ``#ffc000``
4.6 - 5.0               F         Fail                ``#ff0000``
======================  ========  ==================  ===========

The canonical palette above is the one drawn by the majority of the reference
PDFs, but a handful of reports paint a band with a different tint (e.g. some
paint *Very Good* yellow, or *Satisfactory* as ``#eeb500``). Those variants are
recorded in :data:`KNOWN_VARIANTS` purely for documentation; the extraction
pipeline treats a colour it actually recovered from the PDF as authoritative,
falling back to :func:`background_for` only when no fill could be recovered, so
no report ever regresses.

This module is deliberately free of any dependency on the rest of the package
so the templates in FEAT-004 can import it directly to colour competency cells
when they are handed raw data instead of a rendered PDF.
"""

from __future__ import annotations

from dataclasses import dataclass

#: GPA band cut-offs. A GPA <= cutoffs[i] falls in band i (0 = best).
#: 1.0-1.5 Excellent | 1.6-2.5 Very Good | 2.6-3.5 Good | 3.6-4.5 Satisfactory |
#: 4.6-5.0 Fail.
CUTOFFS: tuple[float, ...] = (1.5, 2.5, 3.5, 4.5)


@dataclass(frozen=True)
class Band:
    """One competency band: its grade letter, label and canonical colour."""

    grade: str
    label: str
    background: str


#: Canonical bands, best (index 0) to worst, aligned with :data:`CUTOFFS`.
BANDS: tuple[Band, ...] = (
    Band("A", "Excellent", "#00b050"),
    Band("B", "Very Good", "#92d050"),
    Band("C", "Good", "#ffff00"),
    Band("D", "Satisfactory", "#ffc000"),
    Band("F", "Fail", "#ff0000"),
)

#: Alternative tints some reports paint a band with. The extracted colour wins
#: over the canonical one, so these never need to be applied - they document why
#: a recovered colour may legitimately differ from :data:`BANDS`.
KNOWN_VARIANTS: dict[str, tuple[str, ...]] = {
    "Very Good": ("#ffff00",),
    "Satisfactory": ("#eeb500", "#e26b0a", "#daf2d0"),
    "Good": ("#daf2d0",),
}

# Lookup keys -> band index. Both the grade letter and the free-text label
# (however the report spells it) resolve to a single band.
_LABEL_TO_INDEX: dict[str, int] = {}
for _i, _b in enumerate(BANDS):
    _LABEL_TO_INDEX[_b.grade.upper()] = _i
    _LABEL_TO_INDEX[_b.label.upper()] = _i
    _LABEL_TO_INDEX[f"GRADE {_b.grade}".upper()] = _i
# Common synonyms observed in the reports.
_LABEL_TO_INDEX["WEAK"] = 4
_LABEL_TO_INDEX["FAILED"] = 4

# Multi-word phrases used for containment matching (single letters/words are
# matched only by exact equality to avoid false positives inside ordinary text).
_PHRASE_TO_INDEX: dict[str, int] = {
    "VERY GOOD": 1,
    "GRADE A": 0,
    "GRADE B": 1,
    "GRADE C": 2,
    "GRADE D": 3,
    "GRADE F": 4,
}


def _clean(label: str) -> str:
    """Upper-case, drop punctuation/parenthesised text, collapse whitespace."""
    out: list[str] = []
    depth = 0
    for ch in label:
        if ch == "(":
            depth += 1
            out.append(" ")
        elif ch == ")":
            depth = max(depth - 1, 0)
            out.append(" ")
        elif depth:
            continue
        elif ch.isalpha() or ch.isspace():
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).upper().split())


def band_for_gpa(gpa: float) -> Band:
    """Return the competency :class:`Band` for a GPA on the 1.0-5.0 scale."""
    for i, cut in enumerate(CUTOFFS):
        if gpa <= cut:
            return BANDS[i]
    return BANDS[-1]


def band_for_label(label: str) -> Band | None:
    """Resolve a competency label / grade string to its :class:`Band`.

    Handles ``"Grade A (Excellent)"``, ``"Excellent"``, ``"A"``, ``"Grade A"``,
    ``"Very Good"`` and the ``"Weak"`` / ``"Failed"`` synonyms. Returns ``None``
    when the text names no known competency.
    """
    if not label:
        return None
    cleaned = _clean(label)
    if cleaned in _LABEL_TO_INDEX:
        return BANDS[_LABEL_TO_INDEX[cleaned]]
    # Match a full multi-word competency phrase appearing as whole words in the
    # text (e.g. "GRADE A EXCELLENT" once parentheses are stripped). Only phrases
    # of two or more words are matched by containment so a stray single letter
    # in an ordinary label (a SCHOOL NAME containing "A") is never mistaken for a
    # grade; single-token labels must match exactly (handled above).
    words = cleaned.split()
    for phrase, idx in _PHRASE_TO_INDEX.items():
        plen = len(phrase.split())
        if plen < 2:
            continue
        for i in range(len(words) - plen + 1):
            if words[i : i + plen] == phrase.split():
                return BANDS[idx]
    return None


def resolve(label: str | None = None, gpa: float | None = None) -> tuple[str, str] | None:
    """Map a competency *label* and/or *gpa* to ``(label_text, background_hex)``.

    The label is preferred; the GPA band is used when the label is missing or
    unrecognised. Returns ``None`` when neither yields a band.
    """
    band: Band | None = None
    if label:
        band = band_for_label(label)
    if band is None and gpa is not None:
        band = band_for_gpa(gpa)
    if band is None:
        return None
    return band.label, band.background


def background_for(label: str | None = None, gpa: float | None = None) -> str | None:
    """Canonical background colour for a competency label and/or GPA."""
    resolved = resolve(label=label, gpa=gpa)
    return resolved[1] if resolved else None
