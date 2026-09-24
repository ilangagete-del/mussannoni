"""Write the honest per-report fidelity table from gate results.

Takes the JSON the fidelity gate writes (``--json``) and renders
``docs/FIDELITY_REPORT.md``: one row per report with its worst page's visible and
exact match, its page count, and — when a baseline JSON is given — what it was
before, so progress and regressions are both visible.

Usage::

    uv run python tools/fidelity_gate.py --json output/fidelity/current.json
    uv run python tools/fidelity_report.py output/fidelity/current.json \
        --baseline output/fidelity/baseline.json
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "FIDELITY_REPORT.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


CEILING_LINE = re.compile(
    r"^(?P<name>.+?): replay ceiling — worst page visible (?P<visible>[\d.]+)% "
    r"exact (?P<exact>[\d.]+)%"
)


def load_ceiling(path: Path) -> dict[str, dict[str, float]]:
    """Parse ``tools/replay.py`` output: the ceiling this toolchain can reach.

    The replay places the reference's OWN glyph origins and rectangles through the
    same pipeline, so its number is the most any renderer here could score. The
    distance from it is what is actually still winnable.
    """
    out: dict[str, dict[str, float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = CEILING_LINE.match(line.strip())
        if match:
            out[match.group("name")] = {
                "visible": float(match.group("visible")),
                "exact": float(match.group("exact")),
            }
    return out


def render(current: dict, baseline: dict | None, ceiling: dict | None = None) -> str:
    before = {}
    ceiling = ceiling or {}
    if baseline:
        before = {r["name"]: r for r in baseline["reports"]}

    rows = sorted(current["reports"], key=lambda r: r["worst_visible_pct"])
    lines = [
        "# Fidelity report — measured, not claimed",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} by "
        "`tools/fidelity_report.py` from `tools/fidelity_gate.py` output.",
        "",
        f"* gate: **{current['target_pct']:.0f}% visible-pixel match on every page of every "
        f"report**, rasterised at {current['zoom']:g}x, visible = max RGB channel delta "
        f"<= {current['visible_tolerance']}",
        f"* result: **PASS {current['passed']}/{current['total']}**, "
        f"worst page across all reports **{current['worst_page_visible_pct']:.4f}% visible**",
        "",
        "`visible` is the gate's criterion; `exact` (zero delta on every channel) is shown "
        "as well, because the gap between them is glyph-edge antialiasing.",
        "",
        "**replay ceiling** is what `tools/replay.py` scores when it places the reference's "
        "OWN glyph origins and rectangles through this same pipeline - the most any renderer "
        "here could achieve. The last column is therefore what is still winnable; the rest is "
        "the toolchain's rasterisation floor.",
        "",
        "| Report | pages | worst page visible | worst page exact | baseline | change "
        "| replay ceiling | gap to ceiling |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for report in rows:
        name = report["name"]
        old = before.get(name, {})
        old_pct = old.get("worst_visible_pct")
        limit = ceiling.get(name, {}).get("visible")
        if report["hard_fail"]:
            lines.append(
                f"| {name} | {report['page_count']} | **HARD FAIL** | — | "
                + (f"{old_pct:.2f}%" if old_pct is not None else "—")
                + f" | {report['hard_fail']} | — | — |"
            )
            continue
        change = ""
        if old_pct is not None:
            change = f"{report['worst_visible_pct'] - old_pct:+.2f} pt"
        gap = ""
        if limit is not None:
            gap = f"{limit - report['worst_visible_pct']:+.2f} pt"
        lines.append(
            f"| {name} | {report['page_count']} | {report['worst_visible_pct']:.4f}% | "
            f"{report['worst_exact_pct']:.4f}% | "
            + (f"{old_pct:.4f}%" if old_pct is not None else "—")
            + f" | {change} | "
            + (f"{limit:.4f}%" if limit is not None else "—")
            + f" | {gap} |"
        )
    lines += [
        "",
        "## How to read this",
        "",
        "A report is only DONE at 100% visible on **every** page (see "
        "`docs/FIDELITY_SPEC.md` §10). Nothing in this table is done. The gate exits "
        "non-zero and `pytest -m slow` fails while that is true.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("current", type=Path, help="gate JSON for the current state")
    parser.add_argument("--baseline", type=Path, help="gate JSON to compare against")
    parser.add_argument(
        "--ceiling", type=Path, help="tools/replay.py output, for the ceiling column"
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    text = render(
        load(args.current),
        load(args.baseline) if args.baseline else None,
        load_ceiling(args.ceiling) if args.ceiling else None,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
