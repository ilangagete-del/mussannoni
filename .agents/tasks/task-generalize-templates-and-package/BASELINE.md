# Baseline & guardrail (FEAT-001)

This is the reference every later feature in `task-generalize-templates-and-package`
must compare against. **The overriding guardrail: no report's per-page
visible-pixel match % may ever drop below the numbers in this file.** The
comparison is measured by `tools/fidelity_gate.py`; use it (not intuition) to
decide whether a change helped or hurt.

Captured & verified this session against `docs/FIDELITY_REPORT.md` (2026-09-24).

## Revert points (undo a bad change immediately)

- `git tag pre-generalize-templates-baseline` — created for this task, the
  immediate revert point. Restore with `git reset --hard pre-generalize-templates-baseline`
  (or `git stash` for uncommitted work).
- `git tag pre-template-refactor` — pre-existing, earlier revert point.

## Durable baseline artifacts

- `output/fidelity/baseline-verify.json` — the captured, verified gate output
  (the authoritative baseline; PASS 0/19, worst page 96.9968%).
- `output/fidelity/baseline.json` — identical copy, used as the stable
  `--baseline` for `tools/fidelity_report.py` diffs. (It previously held a
  stale *pre-font-build* capture at 38.86%; overwritten in FEAT-001 with the
  correct baseline.)

Both were re-verified: a fresh `tools/fidelity_gate.py --json output/fidelity/current.json`
reproduces every per-report number exactly, with **zero regressions**.

## Gate result (must never drop)

- Gate config: rasterise at **2x zoom**, `visible` = max RGB channel delta **<= 8**, target 100% every page.
- **PASS 0/19** — no report is at 100% yet (the gate exits non-zero by design while true; expected).
- **Worst page across all reports = 96.9968% visible.**

### Per-report worst-page-visible % (the guardrail floor)

| Report | worst page visible % |
|---|---:|
| Mwanza f2 Mock Mobility 2026 | 96.9968 |
| S1051-MKOLANI SECONDARY SCHOOL | 97.1377 |
| Mwanza School Rank-English Language | 97.5641 |
| Mwanza Best Students-Overall | 97.6013 |
| Mwanza Schools Rank For Governments | 97.9632 |
| Mwanza Schools Rank For Governments (1) | 97.9632 |
| Mwanza schools rank Overall | 98.3628 |
| MWANZA CC 10 BEST STUDENTS | 98.5350 |
| Mwanza Best students-Subjectwise | 98.8328 |
| MWANZA CC 10 BEST STUDENTS SUBJECTWISE | 98.8893 |
| MWANZA CC SCHOOLS RANK SUBJECTWISE | 98.9748 |
| Mwanza School Rank-EDK | 99.1678 |
| Mwanza f2 District Performance | 99.2258 |
| Mwanza Overall Subjects Performance | 99.3229 |
| MWANZA CC SCHOOLS RANK | 99.4876 |
| MWANZA CC SUBJECTS RANK | 99.5138 |
| MWANZA CC Wards Rank | 99.6535 |
| MWANZA CC 10 BEST SCHOOLS | 99.7399 |
| Mwanza Top 10 Schools | 99.8105 |

## Fast test suite

- `pytest -q -m "not slow"` -> **43 passed, 2 deselected** (exit 0), ~104s.

## Slot audit (value-completeness diagnostic baseline)

`python tools/slot_audit.py` totals across all reports:

- **79408 printed values, 79190 match, 178 empty, 0 unbound, 40 different.**
  - DIFFERENT/number/in-data: 15 · DIFFERENT/text/not-in-data: 25
  - EMPTY/number/in-data: 1 · EMPTY/number/not-in-data: 1 · EMPTY/text/in-data: 176
- `MWANZA CC 10 BEST STUDENTS`: 394 printed values, 0 disagree — **misleading**:
  slot_audit only audits bands the spec defines, and the empty second table
  (TOP TEN BEST FEMALE STUDENTS OVERALL COUNCILWISE) has **no band**, so its
  missing values are not counted. This is the defect FEAT-002 fixes; the
  slot-audit total must rise (more values bound) without any gate regression.

## Render timing baseline (speed — the "it isn't fast" concern)

Measured on this host (WeasyPrint engine; scales with page/row count):

- `Mwanza School Rank-EDK` (1 page): `render_html` ~1.2 ms, `render_pdf` ~0.57 s.
- `MWANZA CC 10 BEST STUDENTS` (5 pages): `render_html` ~44.7 ms, `render_pdf` ~13.35 s.
- Template HTML size ~243 KiB (per context).

(Context.json quoted render_html ~26 ms / render_pdf ~3.4 s as an earlier
average; the PDF cost is dominated by WeasyPrint and grows with page count.)

## Exact re-run commands (the guardrail check)

Always activate the venv first, and fonts MUST be built or the numbers collapse
to 38–90%:

```bash
. .venv/bin/activate
python -m sars.cli unpack            # if data/sars is missing
python tools/build_fonts.py          # REQUIRED — derives+installs reference faces
python -m sars.cli data              # rebuild output/data/*.json from sources
python tools/build_layout_specs.py   # rebuild committed layout specs
python -m sars.cli template          # data -> template HTML + PDF
python tools/fidelity_gate.py --json output/fidelity/current.json
# -> must print PASS 0/19, worst page 96.9968% visible, and NO per-report drop.

# Diagnostics (not acceptance):
python tools/slot_audit.py
python tools/fidelity_report.py output/fidelity/current.json --baseline output/fidelity/baseline-verify.json
```

Regression check for later features: `current.json` per-report `worst_visible_pct`
must be `>=` the baseline value for every report. Aim to raise reports toward
>=98% while never regressing any.
