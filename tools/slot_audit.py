"""Audit every value the reference prints against what the template fills in.

The pixel gate says a page is X% wrong; it does not say "the TOTAL row is missing
its number". This does. For every report it walks the recovered layout spec,
asks the report's own data provider for each band row, and compares the result
with the text the reference actually printed in that cell (the spec's recovered
sample), classifying every disagreement:

* ``EMPTY``     the reference printed something, the template prints nothing —
                the defect that silently drops a TOTAL, a percentage or a rank;
* ``DIFFERENT`` both print something, but not the same string;
* ``UNBOUND``   the column has no recovered data binding at all;
* and for each of those, whether the printed text exists **anywhere** in the
  extracted data (so a gap can be told apart from a mapping error), and whether
  it looks like a number or a label.

A number the reference prints and the data does not carry is a real extraction
gap. A label (``TOTAL``, ``% PASS``, ``AVERAGE``) that no data field carries is
chrome and belongs in the layout, not in the data.

Usage::

    uv run python tools/slot_audit.py                  # every report
    uv run python tools/slot_audit.py --only "SCHOOLS RANK" --list 40
    uv run python tools/slot_audit.py --json output/fidelity/slots.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sars import binding, layout_spec, sources  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.extract_data import extract_report  # noqa: E402

NUMERIC = re.compile(r"^[-+]?[\d.,%/ ]+$")
#: Row labels the reports print as fixed furniture rather than as data.
LABELS = {
    "total", "totals", "% pass", "%pass", "average", "grand total", "sub total",
    "subtotal", "pass", "summary", "all", "overall",
}


def _norm(text: str) -> str:
    return " ".join(str(text).split())


def _kind(text: str) -> str:
    if _norm(text).casefold() in LABELS:
        return "label"
    return "number" if NUMERIC.match(_norm(text)) else "text"


def audit(pair) -> dict:
    document = extract_document(pair.pdf, pair.html)
    data = extract_report(document, pair.name)
    spec = layout_spec.load(pair.name)
    provider = layout_spec.binding_provider(pair.name, data)

    # Every value the data carries anywhere, for the "is it even extracted?" check.
    everywhere: set[str] = set()
    for group in binding.row_groups(data):
        for row in group["rows"]:
            for value in row.values():
                everywhere.add(_norm(value).casefold())

    findings: list[dict] = []
    counts: Counter[str] = Counter()
    for page_index, page in enumerate(spec["pages"]):
        for band_index, band in enumerate(page["bands"]):
            bindings = band.get("bindings") or {}
            for row in range(band["reference_rows"]):
                supplied = provider(page_index, band_index, band["kind"], row)
                cells = (
                    band["per_row_cells"][row]
                    if row < len(band["per_row_cells"])
                    else band["cells"]
                )
                for cell in cells:
                    printed = _norm(cell.get("sample") or "")
                    if not printed or "role" not in cell:
                        continue
                    counts["printed"] += 1
                    column = cell["col"]
                    got = ""
                    if supplied is not None:
                        got = (
                            supplied.get(column, "")
                            if isinstance(supplied, dict)
                            else (supplied[column] if column < len(supplied) else "")
                        )
                    got = _norm(got or "")
                    if got == printed:
                        counts["ok"] += 1
                        continue
                    if not got:
                        problem = "UNBOUND" if str(column) not in bindings else "EMPTY"
                    else:
                        problem = "DIFFERENT"
                    counts[problem] += 1
                    kind = _kind(printed)
                    in_data = printed.casefold() in everywhere
                    counts[f"{problem}/{kind}/{'in-data' if in_data else 'not-in-data'}"] += 1
                    findings.append(
                        {
                            "page": page_index + 1,
                            "band": band_index,
                            "band_kind": band["kind"],
                            "row": row,
                            "col": column,
                            "printed": printed,
                            "got": got,
                            "problem": problem,
                            "kind": kind,
                            "in_data": in_data,
                            "group": band.get("group"),
                            "binding": bindings.get(str(column)),
                        }
                    )
    return {"name": pair.name, "counts": dict(counts), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="substring of a report name")
    parser.add_argument("--list", type=int, default=10, help="findings to list per report")
    parser.add_argument("--json", type=Path, help="write the full audit as JSON")
    args = parser.parse_args()

    results = []
    total = Counter()
    for pair in sources.select(args.only):
        result = audit(pair)
        results.append(result)
        counts = result["counts"]
        total.update(counts)
        bad = counts.get("EMPTY", 0) + counts.get("UNBOUND", 0) + counts.get("DIFFERENT", 0)
        print(
            f"{pair.name}\n    {counts.get('printed', 0)} printed values, "
            f"{counts.get('ok', 0)} match, {bad} disagree "
            f"(empty {counts.get('EMPTY', 0)}, unbound {counts.get('UNBOUND', 0)}, "
            f"different {counts.get('DIFFERENT', 0)})"
        )
        shown = Counter()
        for finding in result["findings"]:
            key = (finding["problem"], finding["kind"], finding["in_data"], finding["col"])
            if shown[key] >= 2 or sum(shown.values()) >= args.list:
                shown[key] += 1
                continue
            shown[key] += 1
            print(
                f"      p{finding['page']} band{finding['band']}({finding['band_kind']}) "
                f"row{finding['row']} col{finding['col']}: {finding['problem']} "
                f"{finding['kind']}, {'in data' if finding['in_data'] else 'NOT in data'} — "
                f"reference {finding['printed']!r}, template {finding['got']!r}"
            )

    print(
        f"\nall reports: {total.get('printed', 0)} printed values, {total.get('ok', 0)} match, "
        f"{total.get('EMPTY', 0)} empty, {total.get('UNBOUND', 0)} unbound, "
        f"{total.get('DIFFERENT', 0)} different"
    )
    for key in sorted(k for k in total if "/" in k):
        print(f"    {key}: {total[key]}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
        print(f"json -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
