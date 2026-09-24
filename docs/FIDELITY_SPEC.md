# FIDELITY SPEC — Pixel-perfect (100%) reproduction of every SARS report

> **Read this file in full before writing any code.** It is the authoritative
> acceptance contract for the report-reproduction work. A previous attempt was
> rejected for reporting "100% text similarity" and "19/19 pass" while the
> reports were visually 44–90% wrong. That happened because the green checks
> measured the wrong things. This document exists so that never happens again.

---

## 1. The goal (non-negotiable)

Each report's **templated PDF** (`output/template_pdf/<name>.pdf`, produced by
`uv run sars template`) must be a **100% pixel-identical replica** of its
**reference PDF** (`data/sars/**/<name>.pdf`), on **every page**.

"100% identical" means **all** of the following are reproduced exactly, not
approximately, cell by cell, dot by dot:

- **Page geometry** — identical page size (pt) and identical page count.
- **Position** — identical banner position; identical table origin (x, y);
  identical absolute position of every cell and every glyph.
- **Row sizing** — every row's height matches the reference row pitch exactly;
  the header band's row heights match; the TOTAL/summary row heights match.
- **Column sizing** — every column width matches the reference lattice exactly.
- **Text content** — every character, in every cell, present and correct.
- **Text alignment** — per cell: left / center / right AND vertical alignment
  must match the reference cell. (e.g. school names left-aligned, numbers
  centered, some cells right-aligned — copy the reference per cell, do not
  assume a global alignment.)
- **Fonts** — the reference's REAL named fonts, embedded: Arial, Arial Bold,
  Times New Roman, Times New Roman Bold, Arial Narrow. Not Liberation/Nimbus
  substitutes unless an exact font is genuinely unavailable (and then it must be
  disclosed with evidence).
- **Font size & weight** — per cell, matching the recovered size (e.g. 4.0pt
  data, 4.2pt headers, 4.8pt group headings, 5.4/6.0pt banner) and weight.
- **Per-cell fill color** — every cell's background wash matches the reference
  cell's fill exactly (the division washes, the GPA/competency bands, the
  registered/SAT tints, the rank-column tints, etc.). No cell may be left white
  if the reference paints it, and no cell may be tinted if the reference leaves
  it white.
- **Rotations** — rotated captions (e.g. vertical C/RANK, R/RANK, "SUMMARY
  PERFORMANCE") match the reference rotation.
- **Text color** — per cell, matching the reference (usually black, but honor
  any exceptions).

The extracted data is identical to the source, so a faithful reproduction MUST
be pixel-for-pixel. Any deviation is a **defect to fix**, not a result to
accept.

**Target = 100% visible-pixel match on every page of every report.** Not 95%.
Drive exact-pixel match as high as physically possible; see §6 for the only
allowed residual.

---

## 2. The 19 reports

Discover canonically:

```bash
uv run python -c "import sys; sys.path.insert(0,'src'); from sars import sources; [print(p.name) for p in sources.discover()]"
```

1. S1051-MKOLANI SECONDARY SCHOOL
2. MWANZA CC 10 BEST SCHOOLS
3. MWANZA CC 10 BEST STUDENTS SUBJECTWISE
4. MWANZA CC 10 BEST STUDENTS
5. MWANZA CC SCHOOLS RANK SUBJECTWISE
6. MWANZA CC SCHOOLS RANK
7. MWANZA CC SUBJECTS RANK
8. MWANZA CC Wards Rank
9. Mwanza Best Students-Overall
10. Mwanza Best students-Subjectwise
11. Mwanza Overall Subjects Performance
12. Mwanza School Rank-EDK
13. Mwanza School Rank-English Language
14. Mwanza Schools Rank For Governments (1)
15. Mwanza Schools Rank For Governments
16. Mwanza Top 10 Schools
17. Mwanza f2 District Performance
18. Mwanza f2 Mock Mobility 2026
19. Mwanza schools rank Overall

---

## 3. Honest baseline (measured, page 1, visible match @ max-RGB-delta > 8)

This is the REAL starting state. Do not trust any prior "done"/"pass" claim.

| Report | visible % | page size | page count | Status |
|---|---|---|---|---|
| Mwanza Best students-Subjectwise | 90.3% | ok | ok | closest, still short of 100% |
| Mwanza Best Students-Overall | 89.9% | ok | ok | short |
| MWANZA CC 10 BEST STUDENTS SUBJECTWISE | 88.5% | ok | ok | short |
| Mwanza f2 District Performance | 85.4% | ok | ok | short |
| Mwanza Top 10 Schools | 82.2% | ok | ok | short |
| MWANZA CC SUBJECTS RANK | 80.8% | ok | ok | short |
| Mwanza Overall Subjects Performance | 79.0% | ok | ok | short |
| MWANZA CC 10 BEST STUDENTS | 78.9% | ok | ok | short |
| S1051-MKOLANI SECONDARY SCHOOL | 78.5% | ok | ok | short (+ upstream extraction gaps) |
| Mwanza School Rank-EDK | 77.0% | ok | ok | short |
| MWANZA CC SCHOOLS RANK | 75.9% | ok | ok | best-tuned, still short |
| MWANZA CC 10 BEST SCHOOLS | 64.7% | ok | ok | short |
| MWANZA CC Wards Rank | 61.7% | ok | ok | short |
| Mwanza School Rank-English Language | 50.9% | ok | ok | BROKEN layout |
| MWANZA CC SCHOOLS RANK SUBJECTWISE | 50.9% | ok | ok | BROKEN (banner −57pt, cols −27pt, compressing row pitch) |
| Mwanza schools rank Overall | 47.4% | ok | ok | BROKEN |
| Mwanza f2 Mock Mobility 2026 | 44.8% | ok | ok | BROKEN |
| Mwanza Schools Rank For Governments | 44.1% | ok | ok | BROKEN |
| Mwanza Schools Rank For Governments (1) | 44.1% | ok | ok | BROKEN |

**0 of 19 meet the target.** Page-size/page-count being "ok" is exactly the trap:
it does NOT mean the layout matches. Example measured drift on
`MWANZA CC SCHOOLS RANK SUBJECTWISE`: banner ~57pt too high, table header ~79pt
too high, rows ~27pt too far left with a row pitch that compresses from −90pt at
row 1 to −162pt by row 27. That is a real layout defect, not antialiasing.

---

## 4. Guardrails — BUILD THESE FIRST, before touching any renderer

### 4.1 `tools/fidelity_gate.py` (the definition of done)
- For all 19 reports × **all pages** (never page 1 only), rasterize reference
  and templated PDFs losslessly at a fixed matrix, dimension-locked.
- HARD FAIL if page size or page count differ.
- Per page compute:
  - **exact %** = pixels with zero RGB delta,
  - **visible %** = pixels within a small delta (report both a strict 0 and a
    >8 tolerance column for insight; gate on visible).
- Print a per-report, per-page table, a summary `PASS n/19`, and the single
  `worst page across all reports = X%`.
- **Exit non-zero unless every page of every report is 100%.**

### 4.2 pytest wiring
- Add a test that runs the gate at the 100% threshold and FAILS otherwise, so
  `pytest` can never be green while any report is imperfect.
- Do not weaken, skip, or delete existing tests.

### 4.3 One comparison image per report
- `output/compare/<name>.jpg`, overwritten in place: a `REFERENCE | TEMPLATE |
  DIFF` panel, DIFF = lossless heatmap labelled with exact/visible %. No
  per-page/per-kind file pile-up. (Already implemented in `tools/compare.py`;
  keep it.)

---

## 5. Anti-cheating rules (hard constraints)

- **Text-similarity, page-size, and page-count are DIAGNOSTICS ONLY — NEVER
  acceptance criteria.** The ONLY gate is per-page pixel identity from
  `fidelity_gate.py`.
- Do NOT claim a report is "done / matching / faithful / finished" until the gate
  reports it at target for every page. Prove each report individually; no
  aggregate hand-waving.
- Do NOT loosen the threshold, sample fewer pages, shrink the raster, widen the
  tolerance, or edit the reference PDFs to flatter the numbers. Any such change
  is a task failure.
- Do NOT report "100%" if it is not literally 100%.

---

## 6. The only allowed residual, and how to prove it

If, after exact geometry + color + text + alignment, a report cannot reach
literal 100% exact-pixel match purely because of **rasterizer glyph
antialiasing on 1-pixel edges**, you must:
1. Prove the residual is confined to sub-pixel glyph/border edges (show the diff
   heatmap and sample pixel coordinates).
2. Exhaust remedies: embed the exact reference fonts; match WeasyPrint's
   rasterizer / hinting; render and compare through a matched pipeline.
3. Report the exact remaining % with evidence.

Even then, **visible % must be 100%** (the >0 exact residual, if any, must be
invisible edge noise only). Do not present an antialiasing excuse for a report
whose fills, positions, sizes, alignment, or colors are wrong.

---

## 7. How to do the work — per report, iteratively

1. **Recover ground truth** from the reference via `src/sars/extract.py`
   `extract_document(pdf, html)` and `src/sars/model.py` (`Table.col_edges`,
   `row_edges`, `Cell.row/col/rowspan/colspan`, `Cell.style` →
   `family, size_pt, bold, italic, color, background, align, rotation`). This is
   the FIDELITY ORACLE. Read exact values; never guess.
2. **Set them literally** in that report's OWN self-contained fixed-layout
   renderer in `src/sars/templates/` (its own file, its own inline `<style>`).
   **Do NOT force a shared/global stylesheet or merge structures across report
   types.** Each report is independent; per-report fidelity is the only success
   criterion; efficiency over abstraction is acceptable.
3. **Embed the REAL fonts** (Arial / Times New Roman / Arial Narrow). Network is
   open; fetch and install the actual font files, disclose any fallback.
4. **Render → gate → read drift → correct → re-render → re-gate.** Iterate until
   that report is 100% on every page.
5. Move to the next report. The all-19 gate prevents regressions.

Reference PDFs are read-only inputs and must never be modified.

---

## 8. Delegation protocol — ONE report at a time (mandatory)

To stop messing/regressions, work is delegated so that **each sub-agent handles
exactly ONE report and nothing else**:

- The orchestrator builds/owns the guardrails (§4) FIRST and commits them.
- Then, for each report, delegate a sub-agent whose entire scope is **that single
  report**: recover its geometry, edit only its renderer file, render only that
  report, and iterate until `fidelity_gate.py` reports **that one report** at
  100% on every page.
- A sub-agent may NOT touch other reports' renderers or shared mechanism in a way
  that changes another report's output. If a shared change is unavoidable, it
  must be flagged to the orchestrator, made carefully, and re-gated across ALL 19
  to prove no regression.
- A report is only marked done when: (a) `fidelity_gate.py` shows it at 100% on
  every page, AND (b) its `output/compare/<name>.jpg` DIFF panel is white except
  for provably-irreducible edge noise (§6). Show both as proof.
- After each report passes, run the FULL gate over all 19 to confirm nothing
  regressed before starting the next.

---

## 9. Proof obligations (deliverables)

- `tools/fidelity_gate.py` + its pytest wiring, committed.
- Gate output for the HONEST starting state (expected: failing) and the FINAL
  state.
- The 19 `output/compare/<name>.jpg` images with white DIFF panels.
- `pytest` green **because** the fidelity gate passed.
- A short honest per-report report: exact% and visible%; for any report not at
  literal 100%, the precise evidence (which pixels, why, what was tried).
- Final fresh regeneration before finishing:
  `uv run sars data && uv run sars all && uv run sars template && uv run python tools/compare.py && uv run python tools/fidelity_gate.py`.

---

## 10. Definition of DONE

`tools/fidelity_gate.py` exits 0 with **19/19 reports at 100% visible-pixel
identity on every page**; `pytest` passes on the strength of that gate; the 19
comparison images confirm it visually; and any sub-100% exact-pixel residual is
proven to be irreducible rasterizer edge noise with full disclosure.

Until every one of those is true, the task is **IN PROGRESS** — never report it
as complete.
