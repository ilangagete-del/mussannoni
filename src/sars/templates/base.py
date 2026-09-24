"""Shared building blocks for the report templates.

Every template emits the same document skeleton the conversion pipeline emits:
an ``@page`` A4 rule, the shared :data:`~sars.html_out.DOC_CSS`, a ministry
banner reconstructed from :class:`~sars.schema.ReportMeta`, and one or more
semantic ``<table>`` blocks. Unlike the conversion pipeline the tables are laid
out in normal flow (no absolute geometry, since the data carries none), so long
values wrap elastically inside their ruled cell - the elastic behaviour asked
for in FEAT-002 - and rows grow to fit.

Colours: only the *competency* cell is coloured, and that colour is derived
deterministically from the competency label / GPA via :mod:`sars.competency`.
The decorative header tints of the reference PDFs are chrome that the data does
not carry; templates leave header cells un-tinted so no colour is invented.
"""

from __future__ import annotations

import html

from ..competency import background_for
from ..html_out import DOC_CSS
from ..schema import ReportMeta

#: The fixed ministry masthead, printed at the top of every report.
MASTHEAD: tuple[str, ...] = (
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
)

#: Additional CSS for the templated (flow-layout) output. It layers on top of
#: the shared :data:`DOC_CSS`; the flow layout means cells wrap by default, so
#: the report reads correctly at any data length.
TEMPLATE_CSS = """\
body{font-family:Arial, Helvetica, sans-serif;color:#000;margin:0}
/* Keep the content inside the printable box. A nowrap caption is allowed to
   overhang its own column, so leaving no side padding pushed the widest table
   past the right page edge. */
.report{padding:2pt 5pt}
.banner{text-align:center;font-weight:700;font-size:8pt;line-height:1.35}
.banner .title{margin-top:6pt}
table.tmpl{border-collapse:collapse;table-layout:fixed;width:100%;
           border-spacing:0;margin-top:6pt;font-size:5.4pt;line-height:1.05}
/* Dense reports (schools rank, top schools, subjects rank, the wide pivots) pack
   many rows onto one page just as the reference does. The font is sized to fill
   the page rather than to the smallest that fits: too small and the table hangs
   in the top third of the sheet with a band of white beneath it, which is what
   the reference never does. */
.report.compact table.tmpl{font-size:4.9pt;line-height:1.04;margin-top:3pt}
.report.compact table.tmpl th,.report.compact table.tmpl td{padding:0 0.5pt}
/* Elastic cells: wrap at word boundaries so a long multi-word value (a school
   name, a COMPETENCY LEVEL label) flows onto extra lines inside its ruled box
   and the row grows to fit, but a single long word is never broken mid-token
   (which would split it into two verification tokens and drop text fidelity).
   overflow stays visible so a value wider than its column overhangs, exactly as
   the reference PDFs do, rather than being clipped. */
table.tmpl th,table.tmpl td{border:0.4pt solid #000;padding:0.2pt 1pt;
           text-align:center;vertical-align:middle;overflow:visible;
           white-space:normal;overflow-wrap:normal;word-break:keep-all}
table.tmpl th{font-weight:700}
/* A caption that is a single token ("C/RANK", "S/NO.", "%A-C") must never break
   inside itself: a line break at the slash turns one token into two and reads as
   lost text. Such a caption gains nothing from wrapping anyway, so it is held on
   one line and allowed to overhang. Multi-word captions ("COMPETENCY LEVEL")
   still wrap at their spaces. */
table.tmpl th.nw{white-space:nowrap}
table.tmpl td.text,table.tmpl th.text{text-align:left}
table.tmpl tr.total th,table.tmpl tr.total td{font-weight:700}
"""


def esc(text: str) -> str:
    """HTML-escape a value, mapping empty to a non-breaking space."""
    text = "" if text is None else str(text)
    return html.escape(text) if text.strip() else "&#160;"


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

    ``compact`` selects the dense layout (smaller table font, tighter rows) used
    by the wide, many-row reports so they occupy the reference's page count.
    """
    orientation = orientation_for(meta)
    page_css = f"@page{{size:A4 {orientation};margin:8pt}}"
    title = esc(meta.title or meta.name)
    report_cls = "report compact" if compact else "report"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{page_css}\n{DOC_CSS}\n{TEMPLATE_CSS}</style>\n"
        "</head>\n<body>\n"
        f'<section class="{report_cls}">{body}</section>\n'
        "</body>\n</html>\n"
    )


def competency_cell(label: str, gpa: str = "", *, tag: str = "td") -> str:
    """A competency cell coloured deterministically from its label / GPA.

    The background is looked up via :func:`sars.competency.background_for`
    (label first, GPA band as fallback); an unrecognised value is left
    un-coloured rather than guessed.
    """
    gpa_val: float | None = None
    try:
        gpa_val = float(gpa) if gpa not in ("", None) else None
    except (TypeError, ValueError):
        gpa_val = None
    bg = background_for(label=label or None, gpa=gpa_val)
    style = f' style="background-color:{bg}"' if bg else ""
    return f'<{tag} class="text comp"{style}>{esc(label)}</{tag}>'


def cell(value: str, *, tag: str = "td", text: bool = False, colspan: int = 1) -> str:
    """A plain data / header cell.

    A single-token header caption is marked ``nw`` so it cannot break inside
    itself (see the ``th.nw`` rule in :data:`TEMPLATE_CSS`).
    """
    classes = ["text"] if text else []
    if tag == "th" and value and not str(value).strip().count(" "):
        classes.append("nw")
    cls = f' class="{" ".join(classes)}"' if classes else ""
    span = f' colspan="{colspan}"' if colspan > 1 else ""
    return f"<{tag}{cls}{span}>{esc(value)}</{tag}>"


def header_cell(value: str, *, text: bool = False, colspan: int = 1) -> str:
    """A ``<th>`` caption cell, guarding single-token captions against breaking."""
    return cell(value, tag="th", text=text, colspan=colspan)
