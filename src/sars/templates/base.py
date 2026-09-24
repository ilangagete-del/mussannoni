"""Shared building blocks for the report templates.

DATA IS DATA, NOT STYLES. The extracted data carries only the report's figures
and structure - it deliberately no longer carries any recovered per-cell fonts,
colours, background fills or row pitch. Each template therefore renders from
pure data: the fixed chrome (borders, banner, page box) lives here, the only
colour the template computes is the deterministic *competency* band colour
(derived from the label / GPA via :mod:`sars.competency`, never stored in the
data), and everything else is plain, ruled table markup.

The faithful per-report-type styling is the job of FEAT-003; at this point the
templated output is intentionally plain, but it is built entirely from pure
data and runs without error.
"""

from __future__ import annotations

import html

from ..competency import background_for
from ..html_out import MARGIN_PT
from ..schema import ReportMeta

#: The fixed ministry masthead, printed at the top of every report.
MASTHEAD: tuple[str, ...] = (
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
)

#: CSS for the templated (flow-layout) output. It carries only chrome the data
#: does not: borders, collapse, banner, and the text-fidelity safeguards
#: (word-boundary wrapping, single-token nowrap) that keep tokens from being
#: split or lost. No recovered fonts / colours / fills / pitch are applied here,
#: because the data no longer carries them - that is FEAT-003's job.
TEMPLATE_CSS = """\
body{color:#000;margin:0}
.report{padding:2pt 5pt;font-size:6.5pt;line-height:1.05;
        font-family:Arial, Helvetica, sans-serif}
.report.compact{font-size:4.6pt;line-height:1.04}
.banner{text-align:center;font-weight:700;font-size:8pt;line-height:1.35}
.banner .title{margin-top:6pt}
table.tmpl{border-collapse:collapse;table-layout:fixed;width:100%;
           border-spacing:0;margin-top:6pt}
.report.compact table.tmpl{margin-top:3pt}
table.tmpl th,table.tmpl td{border:0.4pt solid #000;padding:0 0.8pt;
           text-align:center;vertical-align:middle;overflow:visible;
           white-space:normal;overflow-wrap:normal;word-break:keep-all}
table.tmpl th{font-weight:700}
table.tmpl th.nw{white-space:nowrap}
table.tmpl td.text,table.tmpl th.text{text-align:left}
table.tmpl tr.total th,table.tmpl tr.total td{font-weight:700}
.comp{}
"""


def esc(text: str) -> str:
    """HTML-escape a value, mapping empty to a non-breaking space."""
    text = "" if text is None else str(text)
    return html.escape(text) if text.strip() else "&#160;"


def styled_cell(
    value: str,
    *,
    tag: str = "td",
    text: bool = False,
    colspan: int = 1,
    rowspan: int = 1,
    nowrap: bool = False,
    background: str | None = None,
) -> str:
    """A data / header cell rendered from pure data (no recovered style).

    Only the deterministic competency ``background`` (resolved by the caller) is
    ever applied inline; everything else is plain ruled markup.
    """
    classes: list[str] = []
    if text:
        classes.append("text")
    if nowrap or (tag == "th" and value and not str(value).strip().count(" ")):
        classes.append("nw")
    attrs = f' class="{" ".join(classes)}"' if classes else ""
    if colspan > 1:
        attrs += f' colspan="{colspan}"'
    if rowspan > 1:
        attrs += f' rowspan="{rowspan}"'
    style_attr = f' style="background-color:{background}"' if background else ""
    return f"<{tag}{attrs}{style_attr}>{esc(value)}</{tag}>"


def banner_html(meta: ReportMeta, extra_lines: tuple[str, ...] = ()) -> str:
    """The ministry banner (chrome) + region/exam/title (data), centred.

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
    title = meta.title.strip()
    body = "".join(f"<div>{ln}</div>" for ln in lines)
    if title:
        body += f'<div class="title">{esc(title)}</div>'
    return f'<div class="banner">{body}</div>'


#: Report types whose reference documents print in portrait. Everything else
#: is landscape. Keyed by report_type; a narrow single-subject school rank and
#: the mock-mobility pivot are the portrait families.
_PORTRAIT_TYPES: frozenset[str] = frozenset({"subject_school_rank", "mock_mobility"})


def orientation_for(meta: ReportMeta) -> str:
    """Page orientation for a report, matching its reference PDF.

    Derived from the report type (the data does not carry page geometry): the
    single-subject school ranks and the mock-mobility pivot are portrait, every
    other report type is landscape.
    """
    return "portrait" if meta.report_type in _PORTRAIT_TYPES else "landscape"


def document_html(meta: ReportMeta, body: str, *, compact: bool = False) -> str:
    """Wrap ``body`` (banner + tables) in the full HTML document shell.

    ``compact`` selects the dense layout used by the wide, many-row reports. The
    document carries only the chrome CSS (:data:`TEMPLATE_CSS`) - the data no
    longer carries per-cell presentation, so no pooled style block is emitted.
    """
    orientation = orientation_for(meta)
    page_css = f"@page{{size:A4 {orientation};margin:{MARGIN_PT:.0f}pt}}"
    title = esc(meta.title or meta.name)
    report_cls = "report compact" if compact else "report"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{page_css}\n{TEMPLATE_CSS}</style>\n"
        "</head>\n<body>\n"
        f'<section class="{report_cls}">{body}</section>\n'
        "</body>\n</html>\n"
    )


def competency_cell(label: str, gpa: str = "", *, tag: str = "td") -> str:
    """A competency cell whose fill is DERIVED, never stored in the data.

    The colour is computed deterministically from the competency label (and, as
    a fallback, the GPA band) via :func:`sars.competency.background_for`. An
    unrecognised value is left un-coloured rather than guessed.
    """
    gpa_val: float | None = None
    try:
        gpa_val = float(gpa) if gpa not in ("", None) else None
    except (TypeError, ValueError):
        gpa_val = None
    background = background_for(label=label or None, gpa=gpa_val)
    bg = f' style="background-color:{background}"' if background else ""
    return f'<{tag} class="text comp"{bg}>{esc(label)}</{tag}>'


def cell(value: str, *, tag: str = "td", text: bool = False, colspan: int = 1) -> str:
    """A plain data / header cell rendered from pure data."""
    return styled_cell(value, tag=tag, text=text, colspan=colspan)


def header_cell(value: str, *, text: bool = False, colspan: int = 1) -> str:
    """A ``<th>`` caption cell, guarding single-token captions against breaking."""
    return cell(value, tag="th", text=text, colspan=colspan)
