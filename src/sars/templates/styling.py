"""Self-contained styling *mechanism* for the report templates.

This module is a reusable **mechanism**, deliberately NOT a shared look. It does
not define a single monolithic ``DOC_CSS`` / ``TEMPLATE_CSS`` constant that every
report is funnelled through; instead it gives each report type the tools to
assemble its OWN complete, standalone HTML document with its OWN inline
``<style>``:

* :class:`Sheet` - a tiny per-document CSS accumulator. Each report creates its
  own instance, appends the rules it needs (its ``@page``, its table rules, its
  own per-column fill washes, its own fonts and row heights, its own rotation
  rule), and the collected rules are inlined into THAT document's ``<head>``.
  Two different report types therefore emit two different, independent style
  blocks - none depends on a cross-report constant.
* :func:`document` - wraps a report's body + its own sheet into a full,
  standalone ``<!DOCTYPE html>`` document. No external stylesheet is linked.
* :func:`fit_scale` - the same fit-to-A4 scale the conversion path uses, so a
  template can author font sizes / row heights at the report's *true* recovered
  point sizes and have them print at the reference scale.
* Small shared *primitives* (HTML escaping, the ``.rot`` rotate(-90deg) span,
  the word-boundary wrap safeguards) that are rendering mechanics, not a shared
  visual identity.

DATA IS DATA, NOT STYLES: none of this reads presentation from the data. The
fill washes a template paints are the report *type's* fixed chrome (keyed to the
column group), authored in the template; the only data-derived colour is the
competency band, computed deterministically from the label / GPA via
:mod:`sars.competency`.
"""

from __future__ import annotations

import html

# A4 in points (portrait); the conversion path uses the same figures.
A4_W, A4_H = 595.276, 841.890
#: Printing margin (pt) applied on every side, matching the conversion path.
MARGIN_PT = 8.0
#: US-Letter source page size (pt); the sources are Letter, printed to A4.
LETTER_W, LETTER_H = 792.0, 612.0


def a4_box(orientation: str) -> tuple[float, float]:
    """(width, height) of the A4 page in points for an orientation."""
    return (A4_H, A4_W) if orientation == "landscape" else (A4_W, A4_H)


def fit_scale(orientation: str, src_w: float = LETTER_W, src_h: float = LETTER_H) -> float:
    """Uniform fit-to-A4 scale for a Letter-sized source, as html_out uses.

    A template authors its cells at the report's TRUE recovered point sizes;
    multiplying by this scale makes them print at the same size the faithful
    conversion path prints them, so the templated output matches the reference.
    """
    pw, ph = a4_box(orientation)
    if orientation == "portrait":
        src_w, src_h = min(src_w, src_h), max(src_w, src_h)
    else:
        src_w, src_h = max(src_w, src_h), min(src_w, src_h)
    return min((pw - 2 * MARGIN_PT) / src_w, (ph - 2 * MARGIN_PT) / src_h)


def esc(text: str) -> str:
    """HTML-escape a value, mapping blank to a non-breaking space."""
    text = "" if text is None else str(text)
    return html.escape(text) if text.strip() else "&#160;"


class Sheet:
    """A per-document CSS accumulator - one instance per rendered report.

    A template creates its own :class:`Sheet`, adds the rules THIS report needs,
    and the rules are inlined into THIS document's ``<head>``. Nothing here is
    shared across report types; each report owns its complete style block.
    """

    def __init__(self) -> None:
        self._rules: list[str] = []
        self._seen: set[str] = set()

    def add(self, rule: str) -> Sheet:
        """Append a CSS rule (deduped within this one document)."""
        rule = rule.strip()
        if rule and rule not in self._seen:
            self._seen.add(rule)
            self._rules.append(rule)
        return self

    def extend(self, rules: str) -> Sheet:
        """Append many rules given as one CSS string."""
        for chunk in rules.strip().split("\n"):
            self.add(chunk)
        return self

    def css(self) -> str:
        return "\n".join(self._rules)


def rot(body: str) -> str:
    """Wrap a caption in the rotate(-90deg) span used for vertical labels."""
    return f'<span class="rot">{body}</span>'


def document(*, title: str, orientation: str, sheet: Sheet, body: str) -> str:
    """Assemble a standalone HTML document from a report's own body + sheet.

    The document is fully self-contained: its only styling is the inline
    ``<style>`` built from ``sheet``; there is no ``<link rel="stylesheet">`` and
    no dependency on any cross-report CSS constant.
    """
    page_css = f"@page{{size:A4 {orientation};margin:{MARGIN_PT:.0f}pt}}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{esc(title)}</title>\n"
        f"<style>\n{page_css}\n{sheet.css()}\n</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )
