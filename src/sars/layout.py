"""Fixed-layout drawing mechanism: place boxes and baselines, not CSS tables.

This is the *mechanism* the high-fidelity report renderers draw with. It exists
because the CSS table algorithm cannot reproduce a PDF cell-for-cell: it rounds
column widths, resolves row heights from content, and centres text using
whatever font the renderer happened to pick. The reference documents, by
contrast, state every rectangle and every glyph origin exactly.

So a renderer here works the way the reference does:

* :meth:`Canvas.fill` paints a rectangle at exact coordinates — the cell washes
  and the hairline rules, which the reference draws as filled rectangles too;
* :meth:`Canvas.text` puts a text run's **baseline** at an exact y and its start
  at an exact x, in the font the reference actually renders with
  (:mod:`sars.fonts`), with the box-top-to-baseline distance calibrated against
  the print engine;
* :meth:`Canvas.cell_text` computes that x from the cell box and the alignment,
  measuring the string with the reference font's own advance widths — the same
  measurement the producing application made, so centred and right-aligned
  values land where the reference put them.

It imposes NO visual identity: no colours, no sizes, no fonts, no page size, no
row heights of its own. Every report's renderer owns all of that and emits its
own standalone document; this module only turns "this text, this size, this
baseline, this box" into HTML+CSS that prints where it was asked to.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from . import fonts


@dataclass(frozen=True)
class Box:
    """A rectangle in PDF/CSS points, top-left origin."""

    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def inset(self, dx: float = 0.0, dy: float = 0.0) -> Box:
        return Box(self.x + dx, self.y + dy, self.w - 2 * dx, self.h - 2 * dy)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


#: Narrowest horizontal squeeze applied to a value that does not fit its cell.
#: Below this the run stops shrinking and is truncated instead, because a run
#: condensed past roughly half its natural width stops being readable. This is
#: the only knob in the overflow policy; see :meth:`Canvas.cell_text`.
MIN_CONDENSE = 0.55


def _truncate_to_width(
    content: str, measure, limit: float, scale: float
) -> str:
    """Longest prefix of *content* that fits *limit* when condensed by *scale*.

    No ellipsis is appended. The reference faces are subsets — several carry a
    19-character cmap — so a "…" would not be in the font and the renderer would
    substitute a DIFFERENT face for that one glyph. This project never permits a
    fallback font, so the run is cut cleanly instead of marked.
    """
    if limit <= 0:
        return ""
    low, high = 0, len(content)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(content[:middle]) * scale <= limit:
            low = middle
        else:
            high = middle - 1
    return content[:low]


class StyleBook:
    """This document's own pooled styles: its fonts, sizes, colours and washes.

    One book per document. Every distinct (family, size, colour) a report uses
    becomes a class in THAT document's inline stylesheet, and every distinct fill
    colour likewise — so each report ships its own style block, listing its own
    recovered fonts and its own palette, and no cross-report stylesheet exists.
    """

    def __init__(self) -> None:
        self._text: dict[tuple[str, float, str], str] = {}
        self._fill: dict[str, str] = {}

    def text_class(self, family: str, size: float, color: str) -> str:
        key = (family, round(size, 4), color)
        name = self._text.get(key)
        if name is None:
            name = f"t{len(self._text) + 1}"
            self._text[key] = name
        return name

    def fill_class(self, color: str) -> str:
        name = self._fill.get(color)
        if name is None:
            name = f"f{len(self._fill) + 1}"
            self._fill[color] = name
        return name

    def css(self) -> str:
        rules: list[str] = []
        for (family, size, color), name in self._text.items():
            rules.append(f".{name}{{font-family:'{family}';font-size:{size:.4f}pt;color:{color}}}")
        for color, name in self._fill.items():
            rules.append(f".{name}{{background:{color}}}")
        return "".join(rules)


@dataclass
class Canvas:
    """One page: an ordered list of fills and absolutely placed text runs."""

    report: str
    width: float
    height: float
    engine: str = "weasyprint"
    book: StyleBook = field(default_factory=StyleBook)
    _fills: list[str] = field(default_factory=list)
    _texts: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ paint
    def fill(self, box: Box, color: str) -> None:
        """Paint a rectangle. Draw order is emission order, as in the PDF."""
        if box.w <= 0 or box.h <= 0 or not color:
            return
        self._fills.append(
            f'<i class="{self.book.fill_class(color)}" '
            f'style="left:{box.x:.4f}pt;top:{box.y:.4f}pt;'
            f'width:{box.w:.4f}pt;height:{box.h:.4f}pt"></i>'
        )

    def rule(self, x: float, y: float, w: float, h: float, color: str = "#000000") -> None:
        """Paint a hairline rule (the reference draws its grid as thin fills)."""
        self.fill(Box(x, y, w, h), color)

    # ------------------------------------------------------------------- text
    def text(
        self,
        x: float,
        baseline: float,
        content: str,
        *,
        role: str,
        size: float,
        color: str = "#000000",
        rotation: int = 0,
        condense: float = 1.0,
    ) -> None:
        """Place *content* with its baseline at *baseline* and its start at *x*.

        ``role`` names the reference font (``arial``, ``arial-bold``,
        ``times-bold``, ``arial-narrow-bold``, …) for THIS report; the concrete
        family is resolved from the font manifest, so the glyphs are the ones the
        reference renders.

        ``condense`` horizontally squeezes the run about its own start, for a
        value too wide for its cell. It is applied as ``scaleX``, which leaves
        the baseline exactly where ``baseline`` put it — so the calibrated
        :func:`sars.fonts.baseline_offset` still holds — and changes no glyph's
        vertical position or the row's geometry. At the default ``1.0`` the
        emitted markup is byte-for-byte what it has always been.
        """
        if not content:
            return
        family = fonts.family(self.report, role)
        offset = fonts.baseline_offset(family, size, self.engine)
        squeeze = "" if condense >= 1.0 else f" scaleX({condense:.6f})"
        if rotation:
            placement = (
                f"left:{x:.4f}pt;top:{baseline:.4f}pt;transform-origin:0 0;"
                f"transform:rotate({rotation:g}deg) translateY({-offset:.4f}pt){squeeze}"
            )
        else:
            placement = f"left:{x:.4f}pt;top:{baseline - offset:.4f}pt"
            if squeeze:
                placement += f";transform-origin:0 0;transform:{squeeze.strip()}"
        self._texts.append(
            f'<t class="{self.book.text_class(family, size, color)}" '
            f'style="{placement}">{esc(content)}</t>'
        )

    def measure(self, content: str, role: str, size: float) -> float:
        """Width of *content* at *size*, from the reference font's own advances."""
        return fonts.text_width(content, self.report, role, size)

    def cell_text(
        self,
        box: Box,
        content: str,
        *,
        role: str,
        size: float,
        baseline: float,
        align: str = "center",
        pad: float = 0.0,
        color: str = "#000000",
        rotation: int = 0,
        xfix: float = 0.0,
        sample: str = "",
    ) -> None:
        """Place *content* inside *box* at *baseline*, aligned like the reference.

        The x is computed from the measured string width, which is how the
        producing application placed centred and right-aligned values; ``pad`` is
        the report's own recovered cell padding and ``xfix`` the recovered
        difference between that computation and where the reference actually
        starts the run (its cell box is not the rectangle lattice to the last
        fraction of a point).

        **Overflow.** A value wider than the room available — a longer student
        name, a longer council name, a fuller detailed-results string than the
        reference ever carried — is absorbed where it is drawn: first by
        condensing the run (down to :data:`MIN_CONDENSE`), then, if even that will
        not fit, by truncating it. It never changes the row's height, the row
        pitch or the page count, which is what stops a longer value from
        repaginating the document.

        The room available is **not** simply the cell box. ``sample`` is the value
        the reference itself printed here, and some reference cells legitimately
        overhang their own recovered box: ``Mwanza f2 Mock Mobility 2026`` draws
        ``GPA 2.2969`` in a box far narrower than the string, and clamping it to
        the box would be less faithful than letting it overhang exactly as the
        reference does. So the budget is the wider of the cell and the
        reference's own run: a value may take as much room as the reference's
        value took, and no more. That makes this policy inert for every reference
        value — the gate cannot move — while still containing genuinely new data.
        """
        content = content.strip()
        if not content:
            return
        width = self.measure(content, role, size)
        if rotation:
            # A rotated caption runs along the box's height; centre it there.
            span = box.h
            start = box.bottom - (span - width) / 2 if align == "center" else box.bottom - pad
            self.text(
                box.x + (box.w + size * 0.72) / 2,
                start,
                content,
                role=role,
                size=size,
                color=color,
                rotation=rotation,
            )
            return
        # The horizontal budget, matching how each alignment derives its x: a
        # left/right aligned run starts one pad inside its edge, a centred run is
        # centred in the whole box (the reference pads it on neither side).
        limit = box.w - pad if align in ("left", "right") else box.w
        if sample:
            # The reference's own run is proof of how much room this cell really
            # affords, box lattice or not.
            limit = max(limit, self.measure(sample.strip(), role, size))
        condense = 1.0
        if limit > 0 and width > limit:
            condense = limit / width
            if condense < MIN_CONDENSE:
                # Too wide even fully condensed: keep the readable floor and cut
                # the run to what that floor can show inside the cell.
                condense = MIN_CONDENSE
                content = _truncate_to_width(
                    content, lambda s: self.measure(s, role, size), limit, condense
                )
                if not content:
                    return
                width = self.measure(content, role, size)
        # Alignment uses the run's ON-PAGE width, which condensing changes.
        drawn = width * condense
        if align == "left":
            x = box.x + pad
        elif align == "right":
            x = box.right - pad - drawn
        else:
            x = box.x + (box.w - drawn) / 2
        self.text(
            x + xfix, baseline, content, role=role, size=size, color=color, condense=condense
        )

    # --------------------------------------------------------------- assembly
    def body(self) -> str:
        return (
            f'<div class="pg" style="width:{self.width:.4f}pt;height:{self.height:.4f}pt">'
            + "".join(self._fills)
            + "".join(self._texts)
            + "</div>"
        )


def document(
    *, title: str, width: float, height: float, pages: list[Canvas], extra_css: str = ""
) -> str:
    """Assemble standalone HTML for a set of fixed-layout pages.

    The only styling is the inline block below plus whatever the report adds
    through ``extra_css``: there is no shared stylesheet and no cross-report CSS.
    """
    book = pages[0].book if pages else StyleBook()
    css = (
        f"@page{{size:{width:g}pt {height:g}pt;margin:0}}"
        "html,body{margin:0;padding:0;background:#fff}"
        ".pg{position:relative;overflow:hidden;background:#fff}"
        ".pg+.pg{page-break-before:always}"
        "i,t{position:absolute;display:block}"
        f"t{{line-height:0;white-space:pre;{fonts.SHAPING_RESET}}}"
        + book.css()
        + extra_css
    )
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{esc(title)}</title>\n<style>{css}</style>\n</head>\n<body>"
        + "".join(page.body() for page in pages)
        + "</body>\n</html>\n"
    )
