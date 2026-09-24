"""Shared *primitives* for the self-contained report templates.

DATA IS DATA, NOT STYLES, and EACH REPORT IS SELF-CONTAINED. There is no shared
``DOC_CSS`` / ``TEMPLATE_CSS`` constant here funnelling every report through one
look, and no shared chrome funnel: each report type's own template owns its
complete structure and its complete inline styling (see :mod:`sars.templates.
styling`). This module only provides small, reusable *primitives* - HTML
escaping, the ministry masthead text, page orientation for a report type, and
the deterministic competency-band colour - none of which imposes a cross-report
visual identity.

The competency colour in particular is computed deterministically from the
competency label / GPA via :mod:`sars.competency`; it is never read from the
data (the data carries no styles).
"""

from __future__ import annotations

from ..competency import background_for
from ..schema import ReportMeta
from .styling import esc

#: The fixed ministry masthead, printed at the top of every report.
MASTHEAD: tuple[str, ...] = (
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
)

#: Report types whose reference documents print in portrait. Everything else is
#: landscape. Derived from the report type (the data carries no page geometry).
_PORTRAIT_TYPES: frozenset[str] = frozenset({"subject_school_rank", "mock_mobility"})


def orientation_for(meta: ReportMeta) -> str:
    """Page orientation for a report, matching its reference PDF."""
    return "portrait" if meta.report_type in _PORTRAIT_TYPES else "landscape"


def banner_lines(meta: ReportMeta, extra_lines: tuple[str, ...] = ()) -> list[str]:
    """The centred masthead + region / exam / title lines (chrome + data).

    ``extra_lines`` lets a template inject a line between the exam name and the
    title (e.g. a school identity line on the result slip).
    """
    lines: list[str] = [esc(m) for m in MASTHEAD]
    region = (meta.region or "").strip()
    if region:
        lines.append(esc(f"{region.upper()} REGION"))
    if meta.exam_name.strip():
        lines.append(esc(meta.exam_name))
    for extra in extra_lines:
        if extra and extra.strip():
            lines.append(esc(extra))
    return lines


def banner_html(meta: ReportMeta, extra_lines: tuple[str, ...] = ()) -> str:
    """Render the centred banner block; each report styles ``.banner`` itself."""
    lines = banner_lines(meta, extra_lines)
    body = "".join(f"<div>{ln}</div>" for ln in lines)
    title = meta.title.strip()
    if title:
        body += f'<div class="title">{esc(title)}</div>'
    return f'<div class="banner">{body}</div>'


def competency_background(label: str, gpa: str = "") -> str | None:
    """Deterministic competency-band background for a label / GPA, or ``None``.

    The colour is DERIVED (never stored): computed from the competency label,
    falling back to the GPA band, via :func:`sars.competency.background_for`.
    """
    gpa_val: float | None = None
    try:
        gpa_val = float(gpa) if gpa not in ("", None) else None
    except (TypeError, ValueError):
        gpa_val = None
    return background_for(label=label or None, gpa=gpa_val)
