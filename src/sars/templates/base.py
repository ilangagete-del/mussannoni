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
from ..html_out import MARGIN_PT, BORDER_PT, DOC_CSS, StylePool, a4_box
from ..model import Style
from ..schema import CellStyle, ReportMeta

#: The reference PDFs are all US-Letter (792x612pt); the conversion path fits
#: them to A4 with a single uniform factor (see :func:`html_out.scale_for`). The
#: templated path emits the same recovered fonts and row pitches, so it must
#: apply the *same* scale or every recovered size/height would print larger than
#: its reference. Both orientations resolve to the same factor (the A4 and Letter
#: aspect ratios cross), so one constant per orientation is exact.
_SRC_W, _SRC_H = 792.0, 612.0


def _scale_for(orientation: str) -> float:
    """Fit-to-A4 scale for a US-Letter source, mirroring ``html_out.scale_for``."""
    pw, ph = a4_box(orientation)
    src_w, src_h = (_SRC_W, _SRC_H) if orientation == "landscape" else (_SRC_H, _SRC_W)
    return min((pw - 2 * MARGIN_PT) / src_w, (ph - 2 * MARGIN_PT) / src_h)


def _to_style(cs: CellStyle | None) -> Style | None:
    """Convert a recovered :class:`~sars.schema.CellStyle` to a model ``Style``.

    Returns ``None`` for a missing carrier so callers can fall back to the
    plain, unstyled markup that pre-style JSON rendered as.
    """
    if cs is None:
        return None
    return Style(
        family=cs.family,
        size_pt=cs.size_pt,
        bold=cs.bold,
        italic=cs.italic,
        color=cs.color,
        background=cs.background,
        align=cs.align,
        rotation=cs.rotation,
    )

#: The fixed ministry masthead, printed at the top of every report.
MASTHEAD: tuple[str, ...] = (
    "THE PRIME MINISTER'S OFFICE",
    "REGIONAL ADMINISTRATION AND LOCAL GOVERNMENT",
)

#: Additional CSS for the templated (flow-layout) output. It layers on top of
#: the shared :data:`DOC_CSS`; the flow layout means cells wrap by default, so
#: the report reads correctly at any data length.
#:
#: FEAT-002: this NO LONGER forces a single Arial 4.9pt / line-height:1.04 over
#: every cell. Each ``<td>`` / ``<th>`` now carries the *recovered* font, colour,
#: background fill and row pitch (a pooled ``stN`` class + inline
#: ``line-height`` + inline ``background-color``), exactly as the faithful
#: conversion path does. What remains here is only the chrome that the data does
#: not carry (borders, collapse, banner) and the text-fidelity safeguards
#: (elastic word-boundary wrapping and single-token nowrap) that protect against
#: tokens being split or lost.
TEMPLATE_CSS = """\
body{color:#000;margin:0}
/* Keep the content inside the printable box. A nowrap caption is allowed to
   overhang its own column, so leaving no side padding pushed the widest table
   past the right page edge. */
/* The fallback font-size lives on the container (inherited, specificity 0), so a
   chrome header or an un-recovered cell picks it up while a recovered cell's
   pooled .stN class always wins. Two scales: the wide many-row reports (compact)
   sit near the recovered ~4pt data size; other reports a touch larger. */
.report{padding:2pt 5pt;font-size:6.5pt;line-height:1.05;
        font-family:Arial, Helvetica, sans-serif}
.report.compact{font-size:4.6pt;line-height:1.04}
.banner{text-align:center;font-weight:700;font-size:8pt;line-height:1.35}
.banner .title{margin-top:6pt}
table.tmpl{border-collapse:collapse;table-layout:fixed;width:100%;
           border-spacing:0;margin-top:6pt}
.report.compact table.tmpl{margin-top:3pt}
/* Elastic cells: wrap at word boundaries so a long multi-word value (a school
   name, a COMPETENCY LEVEL label) flows onto extra lines inside its ruled box
   and the row grows to fit, but a single long word is never broken mid-token
   (which would split it into two verification tokens and drop text fidelity).
   overflow stays visible so a value wider than its column overhangs, exactly as
   the reference PDFs do, rather than being clipped. */
table.tmpl th,table.tmpl td{border:0.4pt solid #000;padding:0 0.8pt;
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


class TemplatePool:
    """Pools the recovered per-cell styles a template emits into CSS classes.

    Thin wrapper around the conversion path's :class:`~sars.html_out.StylePool`
    so the templated path emits *exactly* the same ``.stN`` classes (font
    family / size / weight / slant / colour / alignment / background), scaled by
    the same fit-to-A4 factor. The template accumulates styles into the pool
    while it builds the body, then :func:`document_html` injects :meth:`css`.

    A cell whose recovered carrier is absent (older JSON, or a chrome cell with
    no source cell) is simply emitted without a pooled class and inherits the
    plain table defaults, so nothing is invented where nothing was recovered.
    """

    def __init__(self, orientation: str) -> None:
        self._scale = _scale_for(orientation)
        self._pool = StylePool(scale=self._scale)

    @property
    def scale(self) -> float:
        return self._scale

    def class_for(self, cs: CellStyle | None) -> str | None:
        style = _to_style(cs)
        return self._pool.class_for(style) if style is not None else None

    def css(self) -> str:
        return self._pool.css()


def _open_tag(
    tag: str,
    *,
    cls: list[str],
    style_cls: str | None,
    pitch: float,
    scale: float,
    background: str | None,
    colspan: int,
    rowspan: int = 1,
) -> str:
    """Build an opening ``<td>`` / ``<th>`` tag carrying the recovered style.

    ``style_cls`` is the pooled font/colour/background class; ``pitch`` is the
    recovered source row height in points which becomes the cell's
    ``line-height`` (minus the rule width, exactly as
    :func:`html_out._cell_html` does, because WeasyPrint drops rows given an
    explicit ``<tr>`` height). ``background`` overrides the pooled fill when a
    caller resolves a colour itself (the competency fallback).
    """
    classes = list(cls)
    if style_cls:
        classes.append(style_cls)
    inline: list[str] = []
    if pitch and pitch > 0 and rowspan == 1:
        line_h = max(pitch * scale - BORDER_PT, 0.5)
        inline.append(f"line-height:{line_h:.2f}pt")
    if background:
        inline.append(f"background-color:{background}")
    attrs = f' class="{" ".join(classes)}"' if classes else ""
    if colspan > 1:
        attrs += f' colspan="{colspan}"'
    if rowspan > 1:
        attrs += f' rowspan="{rowspan}"'
    style_attr = f' style="{";".join(inline)}"' if inline else ""
    return f"<{tag}{attrs}{style_attr}>"


def styled_cell(
    pool: TemplatePool,
    value: str,
    cs: CellStyle | None,
    pitch: float = 0.0,
    *,
    tag: str = "td",
    text: bool = False,
    colspan: int = 1,
    rowspan: int = 1,
    nowrap: bool = False,
    background: str | None = None,
    rotate: bool = False,
) -> str:
    """A data / header cell carrying its recovered style, pitch and rotation.

    Mirrors the conversion path's ``_cell_html``: the recovered font/colour/fill
    come from the pooled ``stN`` class, the row height from an inline
    ``line-height``, and a rotated label is wrapped in the shared ``.rot`` span
    (see :data:`DOC_CSS`) so vertical rank captions render turned and unclipped.
    """
    classes: list[str] = []
    if text:
        classes.append("text")
    rot = rotate or (cs is not None and cs.rotation in (90, 270))
    if rot:
        classes.append("vcell")
    if nowrap or (tag == "th" and value and not str(value).strip().count(" ")):
        classes.append("nw")
    style_cls = pool.class_for(cs)
    open_tag = _open_tag(
        tag,
        cls=classes,
        style_cls=style_cls,
        pitch=pitch,
        scale=pool.scale,
        background=background,
        colspan=colspan,
        rowspan=rowspan,
    )
    body = esc(value)
    if rot and value and value.strip():
        body = f'<span class="rot">{body}</span>'
    return f"{open_tag}{body}</{tag}>"


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


def document_html(
    meta: ReportMeta, body: str, *, compact: bool = False, pool: TemplatePool | None = None
) -> str:
    """Wrap ``body`` (banner + tables) in the full HTML document shell.

    ``compact`` selects the dense layout used by the wide, many-row reports.
    ``pool`` is the :class:`TemplatePool` the template filled while building
    ``body``; its pooled ``.stN`` classes (the recovered fonts / colours / fills)
    are injected into the document ``<style>`` so every cell that referenced a
    class resolves. Passing no pool keeps the old plain output.
    """
    orientation = orientation_for(meta)
    page_css = f"@page{{size:A4 {orientation};margin:{MARGIN_PT:.0f}pt}}"
    title = esc(meta.title or meta.name)
    report_cls = "report compact" if compact else "report"
    pool_css = f"\n{pool.css()}" if pool is not None else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{page_css}\n{DOC_CSS}\n{TEMPLATE_CSS}{pool_css}</style>\n"
        "</head>\n<body>\n"
        f'<section class="{report_cls}">{body}</section>\n'
        "</body>\n</html>\n"
    )


def competency_cell(
    label: str,
    gpa: str = "",
    *,
    tag: str = "td",
    pool: TemplatePool | None = None,
    style: CellStyle | None = None,
    pitch: float = 0.0,
) -> str:
    """A competency cell that PREFERS the recovered fill, then the derived one.

    When the source cell's own background fill was recovered (carried on
    ``style``) it wins - matching the conversion path's rule that a recovered
    colour is authoritative. Only when no fill was recovered does the cell fall
    back to :func:`sars.competency.background_for` (label first, GPA band next),
    and an unrecognised value is left un-coloured rather than guessed.
    """
    recovered = style.background if style is not None else None
    background = recovered
    if background is None:
        gpa_val: float | None = None
        try:
            gpa_val = float(gpa) if gpa not in ("", None) else None
        except (TypeError, ValueError):
            gpa_val = None
        background = background_for(label=label or None, gpa=gpa_val)
    if pool is not None:
        return styled_cell(
            pool,
            label,
            style,
            pitch,
            tag=tag,
            text=True,
            background=background,
        )
    bg = f' style="background-color:{background}"' if background else ""
    return f'<{tag} class="text comp"{bg}>{esc(label)}</{tag}>'


def cell(
    value: str,
    *,
    tag: str = "td",
    text: bool = False,
    colspan: int = 1,
    pool: TemplatePool | None = None,
    style: CellStyle | None = None,
    pitch: float = 0.0,
) -> str:
    """A plain data / header cell.

    When a ``pool`` and recovered ``style`` are supplied the cell carries its
    recovered font / colour / fill and row pitch (see :func:`styled_cell`);
    otherwise it degrades to the old plain markup. A single-token header caption
    is marked ``nw`` so it cannot break inside itself (see the ``th.nw`` rule in
    :data:`TEMPLATE_CSS`).
    """
    if pool is not None:
        return styled_cell(pool, value, style, pitch, tag=tag, text=text, colspan=colspan)
    classes = ["text"] if text else []
    if tag == "th" and value and not str(value).strip().count(" "):
        classes.append("nw")
    cls = f' class="{" ".join(classes)}"' if classes else ""
    span = f' colspan="{colspan}"' if colspan > 1 else ""
    return f"<{tag}{cls}{span}>{esc(value)}</{tag}>"


def header_cell(
    value: str,
    *,
    text: bool = False,
    colspan: int = 1,
    pool: TemplatePool | None = None,
    style: CellStyle | None = None,
    pitch: float = 0.0,
) -> str:
    """A ``<th>`` caption cell, guarding single-token captions against breaking."""
    return cell(value, tag="th", text=text, colspan=colspan, pool=pool, style=style, pitch=pitch)
