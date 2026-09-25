"""Jinja2 versus this project's own layout mechanism — measured, not assumed.

The open question was whether a templating engine should own the row loop: for
students, subjects and schools a report is *mostly* "repeat this row per record,
and only the competency wash differs". If a template engine can do that without
ever making the PDF comparison worse, it should be used; if it makes the match
worse in any way, it must not be.

This tool answers it with three measurements on real reports:

1. **Fidelity** — is the Jinja2 document BYTE-IDENTICAL to the current one? A
   differing byte is a differing pixel risk, so byte equality is the only
   acceptable answer; anything else fails the guardrail by definition.
2. **Assembly speed** — how long each approach takes to build the HTML.
3. **Share of the whole job** — what fraction of ``render_pdf`` that assembly
   even is, which decides whether the answer can matter for speed at all.

The Jinja2 side is a faithful port: it receives the *same* draw list the current
renderer builds (every fill and every text run, already positioned), and its only
job is to turn that list into markup — which is precisely the "looping" a
template engine is for. It cannot be given less than that, because the positions
come from font metrics (advance widths, calibrated baselines) that only Python
can compute; a template language has no way to measure a string.

Usage::

    python tools/templating_bakeoff.py                  # three representative reports
    python tools/templating_bakeoff.py --only "SCHOOLS RANK"
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sars import sources, template_maker  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.extract_data import extract_report  # noqa: E402

#: Reports that between them cover the looping cases the question is about:
#: students, schools and subjects.
DEFAULT_REPORTS = (
    "MWANZA CC 10 BEST STUDENTS",   # students, two sections on a page
    "MWANZA CC SCHOOLS RANK",       # schools, 64-row band + totals
    "MWANZA CC SUBJECTS RANK",      # subjects
)

#: The Jinja2 port. It emits exactly what ``layout.Canvas``/``document`` emit:
#: the same elements, the same attribute order, the same 4-decimal formatting.
JINJA_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>{{ css }}</style>
</head>
<body>\
{%- for page in pages -%}
<div class="pg" style="width:{{ "%.4f"|format(page.width) }}pt;\
height:{{ "%.4f"|format(page.height) }}pt">\
{%- for f in page.fills -%}
<i class="{{ f.cls }}" style="left:{{ "%.4f"|format(f.x) }}pt;top:{{ "%.4f"|format(f.y) }}pt;\
width:{{ "%.4f"|format(f.w) }}pt;height:{{ "%.4f"|format(f.h) }}pt"></i>\
{%- endfor -%}
{%- for t in page.texts -%}
<t class="{{ t.cls }}" style="{{ t.placement }}">{{ t.content }}</t>\
{%- endfor -%}
</div>\
{%- endfor -%}
</body>
</html>
"""


def _draw_list(report_name: str, report_type: str, data):
    """Render once through the real pipeline, capturing the positioned draw list.

    ``Canvas`` already stores its output as the exact element strings, so the
    honest way to give Jinja2 the same input is to capture the *values* that went
    into them. This monkeypatches the two emitters to record structured entries
    alongside the normal ones, so both sides are driven by identical geometry.
    """
    from sars import layout

    fills: list[list[dict]] = []
    texts: list[list[dict]] = []
    pages_meta: list[dict] = []

    real_fill, real_text, real_body = layout.Canvas.fill, layout.Canvas.text, layout.Canvas.body

    def fill(self, box, color):
        before = len(self._fills)
        real_fill(self, box, color)
        if len(self._fills) > before:  # a zero-size fill is skipped
            self._cap_fills.append(
                {
                    "cls": self.book.fill_class(color),
                    "x": box.x, "y": box.y, "w": box.w, "h": box.h,
                }
            )

    def text(self, x, baseline, content, *, role, size, color="#000000", rotation=0,
             condense=1.0):
        before = len(self._texts)
        real_text(self, x, baseline, content, role=role, size=size, color=color,
                  rotation=rotation, condense=condense)
        if len(self._texts) > before:
            # Reuse the element the real emitter just produced, so the captured
            # placement string and escaped content are byte-for-byte its own.
            element = self._texts[-1]
            placement = element.split('style="', 1)[1].split('"', 1)[0]
            body = element.split(">", 1)[1].rsplit("</t>", 1)[0]
            self._cap_texts.append(
                {
                    "cls": self.book.text_class(
                        __import__("sars").fonts.family(self.report, role), size, color
                    ),
                    "placement": placement,
                    "content": body,
                }
            )

    def body(self):
        pages_meta.append({"width": self.width, "height": self.height})
        fills.append(self._cap_fills)
        texts.append(self._cap_texts)
        return real_body(self)

    def ensure(self):
        if not hasattr(self, "_cap_fills"):
            self._cap_fills, self._cap_texts = [], []

    def fill_wrapped(self, box, color):
        ensure(self)
        fill(self, box, color)

    def text_wrapped(self, x, baseline, content, **kw):
        ensure(self)
        text(self, x, baseline, content, **kw)

    def body_wrapped(self):
        ensure(self)
        return body(self)

    layout.Canvas.fill, layout.Canvas.text, layout.Canvas.body = (
        fill_wrapped, text_wrapped, body_wrapped
    )
    try:
        html = template_maker.render_html(report_type, data)
    finally:
        layout.Canvas.fill, layout.Canvas.text, layout.Canvas.body = (
            real_fill, real_text, real_body
        )

    css = html.split("<style>", 1)[1].split("</style>", 1)[0]
    title = html.split("<title>", 1)[1].split("</title>", 1)[0]
    pages = [
        {"width": m["width"], "height": m["height"], "fills": f, "texts": t}
        for m, f, t in zip(pages_meta, fills, texts, strict=True)
    ]
    return html, {"title": title, "css": css, "pages": pages}


def run(names: list[str]) -> int:
    try:
        import jinja2
    except ImportError:
        print(
            "jinja2 is not installed, so this comparison cannot run.\n"
            "It is a DEV-ONLY dependency, needed by this tool and nothing else:\n"
            "    uv pip install jinja2      (or: pip install 'sars-convert[dev]')\n"
            "The recorded outcome of this bake-off is in docs/DECISIONS.md.",
            file=sys.stderr,
        )
        return 2

    # autoescape off: the content was already escaped by Canvas, exactly once.
    # keep_trailing_newline on: Jinja2 strips a template's final newline, and the
    # document ends with one.
    env = jinja2.Environment(autoescape=False, keep_trailing_newline=True)
    template = env.from_string(JINJA_TEMPLATE)

    print(f"{'report':<34}{'identical':>11}{'ours':>9}{'jinja2':>9}"
          f"{'assembly':>10}{'of render_pdf':>15}")
    print("-" * 90)

    verdict_identical = True
    verdict_faster = False
    for name in names:
        pair = next((p for p in sources.discover() if p.name == name), None)
        if pair is None:
            print(f"{name:<34}  (not available)")
            continue
        data = extract_report(extract_document(pair.pdf, pair.html), name)
        report_type = getattr(data.meta, "report_type", "generic")

        ours, context = _draw_list(name, report_type, data)
        theirs = template.render(**context)

        identical = ours == theirs
        verdict_identical &= identical

        t = time.perf_counter()
        for _ in range(3):
            template_maker.render_html(report_type, data)
        ours_s = (time.perf_counter() - t) / 3

        t = time.perf_counter()
        for _ in range(3):
            template.render(**context)
        theirs_s = (time.perf_counter() - t) / 3

        t = time.perf_counter()
        template_maker.render_pdf(report_type, data, "/dev/null")
        pdf_s = time.perf_counter() - t

        if theirs_s < ours_s:
            verdict_faster = True
        print(f"{name[:32]:<34}{('YES' if identical else 'NO'):>11}"
              f"{ours_s:>8.3f}s{theirs_s:>8.3f}s"
              f"{ours_s / pdf_s * 100:>9.1f}%{pdf_s:>14.1f}s")

    print()
    print("byte-identical on every report :", "YES" if verdict_identical else "NO")
    print("jinja2 ever faster to assemble :", "YES" if verdict_faster else "NO")
    print()
    print("Reading this: assembly % is the share of a full render_pdf that HTML")
    print("templating even accounts for. Whatever engine wins it cannot move the")
    print("remainder, which is WeasyPrint turning the HTML into a PDF.")
    return 0 if verdict_identical else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="substring of a report name")
    args = parser.parse_args()
    names = list(DEFAULT_REPORTS)
    if args.only:
        names = [p.name for p in sources.select(args.only)]
    return run(names)


if __name__ == "__main__":
    raise SystemExit(main())
