"""The fidelity gate, wired into pytest.

``docs/FIDELITY_SPEC.md`` §4.2 requires that ``pytest`` can never be green while
any report is imperfect. This module is that wiring: it runs
``tools/fidelity_gate.py`` over every page of every report and fails unless each
one is a 100% visible-pixel match to its reference.

It is slow on purpose — it rasterises every page of 19 documents — so it is
marked ``slow`` and can be selected or deselected explicitly::

    uv run pytest -m slow            # only the gate
    uv run pytest -m "not slow"      # everything else

Running it requires the generated PDFs (``uv run sars template``) and the font
assets (``uv run python tools/build_fonts.py``). If either is absent the test
FAILS rather than skips: a missing prerequisite is not a pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytestmark = pytest.mark.slow


def _gate():
    import fidelity_gate

    return fidelity_gate


def test_every_report_matches_its_reference_on_every_page():
    gate = _gate()
    results = gate.run(quiet=True)
    assert results, "no reports discovered — the gate must never pass vacuously"

    lines: list[str] = []
    for result in sorted(results, key=lambda r: r.worst_visible):
        if result.hard_fail:
            lines.append(f"{result.name}: HARD FAIL {result.hard_fail}")
        elif not result.ok:
            lines.append(
                f"{result.name}: worst page {result.worst_visible:.4f}% visible "
                f"/ {result.worst_exact:.4f}% exact over {len(result.pages)} page(s)"
            )
    passed, total, worst = gate.summarise(results)
    assert not lines, (
        f"fidelity gate: PASS {passed}/{total}, worst page {worst:.4f}% visible.\n"
        + "\n".join(lines)
    )


def test_gate_refuses_to_pass_on_a_partial_page_sample():
    """A ``--pages`` run is a diagnostic and must never report success."""
    gate = _gate()
    assert gate.main(["--only", "MWANZA CC Wards Rank", "--pages", "1"]) != 0
