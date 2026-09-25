"""Build experimental data at the extremes, beyond the 19 bundled examples.

FEAT-003 (flexibility): the templated path must render correctly for *less* and
*more* data than the reference reports, not just the fixed cases. This module
mutates an extracted schema instance into the extreme shapes the reference never
had, so the shared layout mechanism can be exercised and asserted on:

* the longest plausible **student name** (overhang past its column);
* the longest plausible **council name** (a wide identity column);
* an over-long **DETAILED SUBJECTS** string (wider than the whole column, and
  wide enough to run off the page without clipping);
* **more rows** than fit one page (forcing pagination);
* **fewer rows** than the reference (a short section);
* an **empty section** (a caption with no body).

Everything here is *data*: it reuses the report's own recovered layout spec, so
it proves the mechanism is elastic without special-casing any report. The
fixtures are reproducible (a fixed seed / fixed strings) and kept separate from
the committed 19 — they are never written into ``output/data``.

Run ``python tools/stress_data.py`` to render each extreme to
``output/stress/<case>.html`` (and ``.pdf`` with ``--pdf``) for eyeballing.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import replace
from pathlib import Path
from typing import Any

from sars import schema, sources, template_maker
from sars.extract import extract_document
from sars.extract_data import extract_report

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "output" / "data"
OUT = ROOT / "output" / "stress"

# The extreme strings, fixed so the fixtures are reproducible.
LONG_NAME = "MUHAMMADI ABDULRAHMANI SULEIMANI KIPANGA MWANANCHI WA JAMHURI"  # 60 chars
LONG_COUNCIL = "MWANZA CITY COUNCIL AND METROPOLITAN GREATER MUNICIPAL AUTHORITY"  # 63 chars
LONG_SUBJECTS = (
    "HTM - 97'A' BUSI - 80'A' GEO - 91'A' KISW - 85'A' ENGL - 78'A' PHY - 88'A' "
    "CHEM - 93'A' BIO - 90'A' MATH - 84'A' HIST - 77'A' CIVICS - 82'A' "
    "FRENCH - 70'B' COMMERCE - 66'C' AGRIC - 61'C' FOOD - 59'D' MUSIC - 55'D'"
)


def _load(name: str) -> Any:
    """Load an extracted schema instance from ``output/data`` if present, else
    extract it fresh from the reference pair (so this runs even before
    ``sars data``)."""
    path = DATA / f"{name}.json"
    if path.exists():
        return schema.from_json(path.read_text(encoding="utf-8"))
    pair = next(p for p in sources.discover() if p.name == name)
    return extract_report(extract_document(pair.pdf, pair.html), name)


def longest_student_name(name: str = "MWANZA CC 10 BEST STUDENTS") -> Any:
    """A best-students report whose top candidate has the longest name."""
    data = _load(name)
    data.sections[0].students[0] = replace(
        data.sections[0].students[0], name=LONG_NAME
    )
    return data


def longest_detailed_subjects(name: str = "MWANZA CC 10 BEST STUDENTS") -> Any:
    """A best-students report whose top candidate has an over-long breakdown."""
    data = _load(name)
    data.sections[0].students[0] = replace(
        data.sections[0].students[0], detailed_subjects=LONG_SUBJECTS
    )
    return data


def longest_council_name(name: str = "MWANZA CC SCHOOLS RANK") -> Any:
    """A schools-rank report whose first row carries the longest council name."""
    data = _load(name)
    row = data.rows[0]
    if hasattr(row, "council"):
        data.rows[0] = replace(row, council=LONG_COUNCIL, school_name=LONG_COUNCIL)
    return data


def more_rows(name: str = "MWANZA CC SCHOOLS RANK", extra: int = 60) -> Any:
    """A schools-rank report with far more rows than fit one page."""
    data = _load(name)
    template = data.rows[-1]
    base = len(data.rows)
    for k in range(extra):
        data.rows.append(
            replace(
                copy.deepcopy(template),
                sno=str(base + k + 1),
                school_name=f"EXTRA SECONDARY SCHOOL NUMBER {k + 1}",
            )
        )
    return data


def fewer_rows(name: str = "MWANZA CC SCHOOLS RANK", keep: int = 4) -> Any:
    """A schools-rank report with far fewer rows than the reference."""
    data = _load(name)
    data.rows = data.rows[:keep]
    return data


def empty_section(name: str = "MWANZA CC 10 BEST STUDENTS") -> Any:
    """A best-students report whose second section has no candidates."""
    data = _load(name)
    if len(data.sections) > 1:
        data.sections[1].students = []
    return data


#: name -> (report_type, builder)
CASES: dict[str, tuple[str, Any]] = {
    "longest_student_name": ("best_students", longest_student_name),
    "longest_detailed_subjects": ("best_students", longest_detailed_subjects),
    "longest_council_name": ("schools_rank", longest_council_name),
    "more_rows": ("schools_rank", more_rows),
    "fewer_rows": ("schools_rank", fewer_rows),
    "empty_section": ("best_students", empty_section),
}


def render(case: str) -> str:
    report_type, builder = CASES[case]
    return template_maker.render_html(report_type, builder())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="also print each case to PDF")
    parser.add_argument("cases", nargs="*", help="cases to render (default: all)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for case in args.cases or list(CASES):
        report_type, builder = CASES[case]
        data = builder()
        html = template_maker.render_html(report_type, data)
        (OUT / f"{case}.html").write_text(html, encoding="utf-8")
        print(f"{case}: {len(html):,} bytes -> output/stress/{case}.html")
        if args.pdf:
            template_maker.render_pdf(report_type, data, OUT / f"{case}.pdf")


if __name__ == "__main__":
    main()
