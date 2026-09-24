"""Print every report through BOTH engines and keep the one that wins.

The templated HTML is engine-agnostic, but the two available print engines place
text differently:

* **WeasyPrint** resolves a line box and writes glyph runs from the font's own
  advances;
* **Chromium** (headless print-to-PDF) lays out and quantises positions its own
  way.

Which one lands closer to the reference is a measurement, not an opinion, so this
tool renders each report with each engine, gates both against the reference, and
records the winner (with its numbers as evidence) in ``assets/engine_choice.json``.
:func:`sars.printing.engine_for` reads that file, so the pipeline then prints each
report with the engine that reproduces it best.

Usage::

    uv run python tools/engine_bakeoff.py --only "Wards Rank"
    uv run python tools/engine_bakeoff.py                 # every report
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from fidelity_gate import compare_report  # noqa: E402

from sars import printing, sources, template_maker  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.extract_data import extract_report  # noqa: E402

SCRATCH = ROOT / "output" / "engine_bakeoff"


def bake_off(pair, engines: tuple[str, ...]) -> dict:
    document = extract_document(pair.pdf, pair.html)
    data = extract_report(document, pair.name)
    report_type = getattr(data.meta, "report_type", "generic")

    SCRATCH.mkdir(parents=True, exist_ok=True)
    scores: dict[str, float] = {}
    details: dict[str, dict] = {}
    for engine in engines:
        html = template_maker.render_html(report_type, data, engine=engine)
        out_pdf = SCRATCH / f"{pair.name}.{engine}.pdf"
        printing.print_pdf(html, out_pdf, engine=engine)
        result = compare_report(pair.name, pair.pdf, out_pdf)
        if result.hard_fail:
            scores[engine] = -1.0
            details[engine] = {"hard_fail": result.hard_fail}
            continue
        scores[engine] = result.worst_visible
        details[engine] = {
            "worst_visible_pct": round(result.worst_visible, 4),
            "worst_exact_pct": round(result.worst_exact, 4),
            "pages": len(result.pages),
        }
    winner = max(scores, key=lambda engine: scores[engine])
    printing.record_choice(pair.name, winner, {"measured": details})
    return {"winner": winner, "scores": scores, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="substring of a report name")
    args = parser.parse_args()

    engines = printing.available_engines()
    print(f"engine bake-off across {', '.join(engines)}\n")
    if len(engines) < 2:
        print("NOTE: only one engine is available here, so the choice is trivial.")

    tally: dict[str, int] = {}
    for pair in sources.select(args.only):
        outcome = bake_off(pair, engines)
        tally[outcome["winner"]] = tally.get(outcome["winner"], 0) + 1
        scores = "  ".join(
            f"{engine}={value:.4f}%" if value >= 0 else f"{engine}=HARD FAIL"
            for engine, value in outcome["scores"].items()
        )
        print(f"{pair.name}\n    winner {outcome['winner']:11s} {scores}")

    print("\nwinners: " + ", ".join(f"{engine} x{count}" for engine, count in tally.items()))
    print(f"recorded -> {printing.CHOICE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
