# mussannoni — SARS report conversion to pure HTML + CSS

Converts Mwanza **Form Two Mock Assessment** result reports from messy,
machine-generated HTML into **pure, clean HTML + CSS** that preserves the
original data positions and all styling, and prints through **WeasyPrint** to
**A4 landscape or portrait**.

---

## The problem

The repository ships 19 report documents (`data/sars/`), each as a pair:

| Set | Documents | Content |
|---|---|---|
| `council_html/` + `council_pdf/` | 7 | Mwanza City Council reports |
| `region_html/` + `region_pdf/` | 11 | Mwanza Region reports |
| `S1051-MKOLANI SECONDARY SCHOOL.{html,pdf}` | 1 | Single-school result slip |

The supplied `.html` files are **`pdf2html` fixed-layout dumps**. Their own
stylesheet comment says it plainly:

> `pdf2html base stylesheet — fixed-layout, faithful page reproduction`

Concretely, each such file:

- wraps every page in a `.page` absolute-positioning context sized in pixels;
- emits **every text run** as an absolutely-positioned `<div class="t cN">`
  whose position is carried in a `transform: matrix(a,b,c,d,X,Y)`;
- pools font family / size / colour into opaque `.c1 … .cN` classes;
- paints table rules and cell shading as **`.vec` SVG layers**, not borders.

So the files are visually close to the original but structurally meaningless.
There are **no `<table>`, `<tr>`, or `<th>` elements at all** — rows and columns
exist only as a coincidence of X/Y coordinates. They do not reflow, cannot be
restyled, are up to 3.8 MB each, and carry no semantics for accessibility,
search, or re-use.

## The approach: let the PDF define the structure

Reconstructing tables by clustering X/Y coordinates out of the HTML was
evaluated and rejected — page-wide column clustering produces misaligned bands,
merges unrelated tables, and shatters grouped headers into empty cells.

Instead this project reads structure from the **original PDFs, which are the
ground truth**, using [`pdfplumber`](https://github.com/jsvine/pdfplumber).
These PDFs draw every cell as an explicit filled rectangle, so the table grid
is *stated*, not guessed:

1. **Grid recovery** — `page.find_tables()` returns real cell rectangles. The
   sorted unique X and Y edges form the logical column/row lattice; every cell's
   bbox maps onto it to yield exact **`colspan` / `rowspan`**. This is how
   grouped headers such as `NUMBER OF CANDIDATES → REGISTERED | SAT → F | M | T`
   are recovered losslessly.
2. **Content + style per cell** — text, font name, size, weight, text colour and
   the cell's fill colour are read from the characters and rectangles inside
   each cell bbox.
3. **Domain classification** — these are school results aggregated up a known
   hierarchy (*school → ward → council → region*), which makes the roles of rows
   and columns unambiguous: banner/title blocks, grouped header bands, ranking
   and GPA columns, and `TOTAL` / summary rows are labelled accordingly and
   emitted as `<thead>` / `<th scope>` / `<tfoot>`.
4. **Pure HTML + CSS emission** — one semantic `<table>` per detected table,
   with `table-layout: fixed` and a `<colgroup>` whose widths come from the true
   cell geometry, so **positions are preserved**; and CSS carrying **all original
   styles** (fonts, sizes, weights, text colours, cell shading, alignment,
   rotated rank labels, background washes). No `transform: matrix()`, no opaque
   per-run positional classes — the data is real table markup. Each generated
   file is **self-contained**: its complete stylesheet (the shared structural
   rules plus that document's own pooled per-cell classes) is inlined into its
   own `<head>`, so there is no shared `styles.css` and no external stylesheet
   link.
5. **Print to A4** — each document declares `@page { size: A4 landscape }` or
   `A4 portrait` to match its source, and is rendered with **WeasyPrint**.
6. **Verify against the reference PDF** — the generated PDF is compared with the
   original page-for-page, so the result is provably faithful.

The reference PDFs are read-only inputs and are never modified.

### How positioning works

Each *block* — a semantic table or a heading — is placed at the coordinates it
occupies in the source PDF. Blocks are positioned rather than stacked in normal
flow for two concrete reasons found while building this:

- report pages legitimately contain blocks whose bounding boxes overlap, which
  normal flow cannot represent; and
- stacking accumulates every sub-point rounding difference until content spills
  onto an extra page, silently changing the pagination.

This positions **whole blocks only**. Inside a block, the tabular data is
ordinary semantic table markup laid out by the CSS table algorithm — which is
the essential difference from the pdf2html source, where *every individual text
run* was separately positioned with a transform matrix.

### Row heights

Row height is expressed as `line-height` on the cells rather than `height` on
`<tr>`. WeasyPrint honours an explicit row height by *dropping* rows that no
longer fit, which silently lost ~17% of the data on the densest report. The
rule width is deducted from each line box because a CSS border sits outside it,
which keeps the row pitch identical to the PDF.

## Page size and orientation

Source page boxes are US-Letter (`792×612 pt` landscape, `612×792 pt` portrait).

| Path | Page box |
|---|---|
| conversion (`sars all`) | normalised to **A4** in the matching orientation |
| templated (`sars template`) | the reference's **own US-Letter box**, verbatim |

The templated path deliberately does *not* resize: a page scaled from Letter to A4
can never be pixel-identical to the reference, and the gate hard-fails on a page
size difference for that reason. Each report's layout spec carries the page box it
recovered, and the document declares it (`@page{size:792pt 612pt}`), so portrait
reports stay `612×792` and landscape ones `792×612`.

| Orientation | Documents |
|---|---|
| **portrait** | `MWANZA CC SCHOOLS RANK SUBJECTWISE`, `Mwanza School Rank-EDK`, `Mwanza School Rank-English Language`, `Mwanza f2 Mock Mobility 2026` |
| **landscape** | all 15 others |

## Layout

```
sars.zip              the supplied archive (source of truth, committed)
data/sars/            extracted HTML + reference PDFs (ground truth, read-only)
src/sars/             conversion package
  unpack.py           extracts sars.zip into data/sars
  model.py            Document / Page / Table / Cell / Line / Style
  extract.py          pdfplumber grid + PyMuPDF style recovery
  classify.py         school-results domain logic (headers, totals, banners)
  html_out.py         pure HTML + CSS emission
  render.py           WeasyPrint -> A4 PDF
  verify.py           fidelity check against reference PDFs
  cli.py              command line entry point
  fonts.py            the reference faces: families, advances, baseline offsets
  binding.py          which data field a recovered column carries
  layout.py           fixed-layout drawing mechanism (boxes and baselines)
  layout_spec.py      render a report from its recovered spec + data
  printing.py         print HTML with WeasyPrint or Chromium
  templates/layouts/  ONE recovered layout spec per report (.json.gz)
tests/                unit tests, end-to-end fidelity test, the gate (`-m slow`)
tools/probe.py        read-only PDF diagnostic
tools/compare.py      one REFERENCE | TEMPLATE | DIFF image per report
tools/fidelity_gate.py   THE acceptance gate: per-page pixel identity, all reports
tools/fidelity_report.py honest per-report table -> docs/FIDELITY_REPORT.md
tools/build_fonts.py     derive the reference faces from the reference PDFs
tools/build_layout_specs.py  recover each report's chrome into its layout spec
tools/drift.py           glyph- and rectangle-level differences vs the reference
tools/replay.py          oracle replay: the ceiling this toolchain can reach
tools/engine_bakeoff.py  WeasyPrint vs Chromium, per report, measured
assets/fonts/         derived font assets + manifest (build output, not committed)
assets/engine_choice.json  the measured print engine per report
output/html/          generated self-contained clean HTML (styles inlined per file)
output/pdf/           generated A4 PDFs
output/compare/       one visual comparison image per report
output/fidelity/      gate results as JSON (baseline and current)
```

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
python tools/build_fonts.py          # REQUIRED: derive + install the reference faces
```

Requires Python ≥ 3.11. WeasyPrint needs the system Pango / Cairo / HarfBuzz
libraries, which are present in this environment.

`tools/build_fonts.py` is not optional. The reference documents are rendered in
Arial / Times New Roman / Arial Narrow / Calibri; the region files embed those
faces and the council files rely on the reader substituting URW Nimbus with the
PDF's own `/Widths`. The tool reproduces both cases out of the committed
`sars.zip` and installs the result where fontconfig (and therefore WeasyPrint)
finds it. Without it every report prints in whatever the system happens to have —
which is how an earlier round of this work ended up 38–90% wrong while reporting
success. See `docs/FIDELITY_NOTES.md`.

## Usage

```bash
sars unpack             # extract sars.zip into data/sars (done automatically)
sars convert            # messy HTML sources -> pure HTML + CSS in output/html
sars render             # output/html -> A4 PDFs in output/pdf
sars verify             # compare output/pdf against the reference PDFs
sars all                # convert + render + verify
sars data               # extract each report's DATA to JSON in output/data
sars template           # data -> template -> HTML + PDF (output/template_{html,pdf})
```

`sars.zip` is the single source of truth in the repository. `data/` is a
git-ignored build artefact rebuilt from the archive on demand, while `output/`
is intentionally committed so the results are reviewable on GitHub without
running anything. Every command extracts the archive automatically if needed.

`sars list` prints the document inventory. Target a single document with
`--only`:

```bash
sars all --only "MWANZA CC 10 BEST SCHOOLS"
```

Inspect or eyeball a document:

```bash
python tools/probe.py "10 BEST SCHOOLS"      # grid, fonts, fill colours
python tools/compare.py "10 BEST SCHOOLS" 1  # reference | output, page 1
pytest -q -m "not slow"                      # unit + conversion fidelity tests
pytest -q -m slow                            # THE gate: per-page pixel identity
```

## The only acceptance criterion: `tools/fidelity_gate.py`

Text similarity, page size and page count are **diagnostics**. The one criterion
that decides whether a report is reproduced is per-page pixel identity against
its reference PDF, measured by `tools/fidelity_gate.py`, which rasterises every
page of every report and exits non-zero unless all of them are a 100% visible
match. `pytest -m slow` runs it, so the suite cannot be green while any report is
imperfect.

Current honest state — **PASS 0/19, worst page 90.93% visible** (from 38.86% at
the start of this work; every report improved by 9.8 to 56.2 points). The full
per-report table is `docs/FIDELITY_REPORT.md`; what the remaining error is made
of, and the ceiling this toolchain can reach, is documented with measurements in
`docs/FIDELITY_NOTES.md`. Nothing here should be described as finished until the
gate exits 0.

## Result of the conversion path

All 19 documents reproduce their reference PDF's *content* exactly:

```
summary  19/19 documents pass; mean text similarity 100.00%
```

For every document `sars verify` confirms:

- the same **page count** as the reference;
- pages that really are **A4** in the expected orientation;
- **100 % text similarity** — a per-page multiset comparison of every token;
- `glyphs=identical` — a per-page character-multiset check proving no glyph was
  lost or invented.

Fidelity is measured on content per page rather than on reading order, because a
cell means the same thing wherever the PDF's text operators happen to emit it,
whereas a missing or duplicated value is a real defect.

The clean output is also far smaller than the fixed-layout source: 18.1 MiB of
pdf2html dumps become roughly 4.6 MiB of self-contained HTML (about 26 %), while
gaining semantic tables, real headers, and restylable CSS. Each file now inlines
its own styles, so there is no longer a shared `output/html/styles.css`.

---

# Data-driven templates

The conversion path above redraws *one specific PDF* faithfully. The templated
path does the opposite: it holds a report type's **static chrome** once and is
handed only **data**, so a report can be regenerated — or generated for the
first time, from a database — without any source PDF.

```
data (JSON / dataclass)  ->  template  ->  HTML  ->  [WeasyPrint | Chromium]  ->  PDF
```

## What is data and what is chrome

Everything that varies is data: the region (`Mwanza`), the council
(`Mwanza CC`), the exam name, every school, ward, candidate, mark, count, GPA,
rank and competency label. Chrome is only the fixed furniture: the ministry
masthead, the column headings, and the `TOTAL` / `% PASS` row *labels* — the
numbers on those rows are still data.

Each report's chrome is **recovered from its own reference PDF** into its own
layout spec (`src/sars/templates/layouts/<report>.json.gz`, built by
`tools/build_layout_specs.py`): its page box, every rectangle it paints in the
order it paints them, every fixed caption at the exact origin the reference draws
it, and per band the column boxes, row pitch, fills, fonts, sizes, alignment and
baseline offsets. A report's renderer (`src/sars/templates/<report family>.py`)
then supplies nothing but the data.

So each report remains **fully self-contained and independent**: its own spec, its
own page geometry, its own palette, its own fonts, and its own inline `<style>`
listing exactly the faces, sizes and colours *that* document uses. No report
shares a stylesheet, a structure or a look with another; what is shared is
mechanism only — `sars.layout` (place a box, put a baseline at a y),
`sars.layout_spec` (walk a spec, ask for data), `sars.fonts` (the reference faces
and their advances). The one data-derived colour, the competency band, is
computed deterministically from the label / GPA (`sars.competency`) and is
**never stored** in the data; for the rows the reference itself drew, the
recovered wash wins, because a few documents tint a band differently and the
reference is the authority on its own page.

Which column carries which data field is **also recovered** rather than
hand-written: `tools/build_layout_specs.py` flattens the extracted data, matches
it against the text the reference actually printed in each column, and stores the
winning field path in the spec (`sars.binding`).

## Two print engines, and the reference picks

`sars.printing` can print any report's HTML with **WeasyPrint** or **Chromium**
(headless print-to-PDF). `tools/engine_bakeoff.py` renders every report with both,
gates both against the reference and records the winner in
`assets/engine_choice.json`, which the pipeline then honours. Measured here,
WeasyPrint wins all 19 by 3–20 points; Chromium quantises text positions on its
own grid. The choice is a measurement, so it can be re-run whenever either
engine changes.

## Template-maker API

```python
from sars import template_maker
from sars.extract import extract_document
from sars.extract_data import extract_report

data = extract_report(extract_document(pdf, html), name)   # or build/load it yourself

html  = template_maker.render_html("schools_rank", data)    # -> str
path  = template_maker.render_pdf("schools_rank", data, "out.pdf")   # -> Path
blob  = template_maker.render_pdf("schools_rank", data)     # -> PDF bytes
html2 = template_maker.make(data)      # infers the report type from the data
```

| Function | Signature | Returns |
|---|---|---|
| `render_html` | `(report_type, data)` | the HTML document as a `str` |
| `render_pdf` | `(report_type, data, out_path=None)` | `Path` when given a path, else PDF `bytes` |
| `make` | `(data)` | HTML, inferring the report type from the data |

## Templates by level and purpose

Templates are selected by a name that says which level it serves and what it
does (`sars.templates.TEMPLATE_NAMES` maps each name to its renderer). Where
private / overall / government share a structure they are *variants* of one
template; only a genuinely different structure gets its own.

| Template name | Report type | Data shape |
|---|---|---|
| `school_result_slip` | `school_result_slip` | `SchoolResultSlip` |
| `council_top_10_schools`, `region_top_10_schools` | `top_schools` | `SchoolsRankReport` |
| `council_schools_rank`, `region_schools_rank_overall`, `region_schools_rank_government` | `schools_rank` | `SchoolsRankReport` |
| `council_top_10_students`, `region_best_students_overall` | `best_students` | `BestStudentsReport` |
| `council_top_10_students_subjectwise`, `region_best_students_subjectwise` | `best_students_subjectwise` | `BestStudentsReport` |
| `council_subjects_rank`, `region_subjects_rank_overall` | `subjects_rank` | `SubjectsRankReport` |
| `council_schools_rank_subjectwise`, `region_school_rank_subject` | `subject_school_rank` | `GenericTabularReport` |
| `council_wards_rank` | `wards_rank` | `GenericTabularReport` |
| `region_district_performance` | `district_performance` | `GenericTabularReport` |
| `region_mock_mobility` | `mock_mobility` | `GenericTabularReport` |

Overall and subjectwise best-students lists are separate templates because the
structure really differs: an overall list ranks a candidate on `AGGT` /
`DIVISION` and prints a `DETAILED SUBJECTS` breakdown, while a subjectwise list
ranks candidates *within one subject* on that subject's `MARKS` / `GRADE` /
`COMPETENCY LEVEL`.

## Data schemas

`sars.schema` defines one schema per report family, and every schema
round-trips losslessly through JSON (`schema.to_json` / `schema.from_dict`).

- **`SchoolResultSlip`** — `centre_no`, `school_name`, `division_summary`,
  `students` (`StudentRow`), `performance` (`PerformanceTable`).
- **`SchoolsRankReport`** — `rows` of `SchoolRankRow` (`sno`, `ward`, `council`,
  `school_name`, `ownership`, `registered`/`sat` as `GenderCounts`, `sat_pct`,
  a `division` map, `gpa`, `competency`, `council_rank`, `regional_rank`),
  plus `totals` and the `summary` performance block.
- **`BestStudentsReport`** — `sections` of `BestStudentsSection`, each a `title`
  and `students`. `StudentRow` carries the overall fields (`cno`, `aggregate`,
  `division`, `detailed_subjects`, parsed `subjects`) *and* the subjectwise ones
  (`sno`, `council`, `id_no`, `category`, `marks`, `grade`, `competency`).
- **`SubjectsRankReport`** — `rows` of `SubjectRankRow` (`subject_name`, a
  `grades` map, `gpa`, `competency`, `rank`), plus `totals`.
- **`GenericTabularReport`** — the header-driven fallback so no report is ever
  left unextracted: `sections` of `TabularSection`, each with `column_headers`,
  `rows` (values keyed by column header) and `totals`.

Dump any document's data with `sars data --only "<name>"`.

## Competency colours are deterministic

The competency cell's background is **never stored**. It is computed from the
competency label (or, failing that, the GPA band) by `sars.competency`:

| GPA band | Grade | Label | Background |
|---|---|---|---|
| 1.0 – 1.5 | A | Excellent | `#00b050` |
| 1.6 – 2.5 | B | Very Good | `#92d050` |
| 2.6 – 3.5 | C | Good | `#ffff00` |
| 3.6 – 4.5 | D | Satisfactory | `#ffc000` |
| 4.6 – 5.0 | F | Fail | `#ff0000` |

Everything else keeps the styling recovered from the source. A few reports tint
a band differently; those variants are recorded in
`sars.competency.KNOWN_VARIANTS`, and the *conversion* path always prefers the
colour it actually recovered from the PDF, so no report regresses.

## Fixed structure, elastic row count

Templated tables are drawn at the coordinates the reference used — a cell box, a
baseline, a run placed with the reference font's own advance widths — rather than
reflowed by the CSS table algorithm, which rounds column widths and resolves row
heights from content and so cannot land on the reference's lattice.

What stays elastic is the row *count*: a band repeats at its recovered row pitch,
so data longer or shorter than the reference still paints correctly (with the
competency wash then derived from the value rather than replayed). For the rows
the reference itself had, its own row edges are used verbatim, because real row
heights vary by hundredths of a point.

## Measuring the templated path

Pixels decide (`tools/fidelity_gate.py`, above). These are the diagnostics that
say *what* is wrong when they do not agree:

```bash
python tools/drift.py "<name>"            # per-glyph and per-rectangle differences
python tools/replay.py --only "<name>"    # the ceiling: replay the reference's own runs
python tools/pixel_diff.py "<name>" --template   # MAE / RMSE / PSNR for one page
python tools/template_audit.py            # per-document content completeness
python tools/template_missing.py "<name>" # which tokens differ, and why
python tools/compare.py                   # reference | template | diff, one image each
```

## Every document has output

All 19 documents are generated on **both** paths, and all of it is committed so
it can be reviewed on GitHub without running anything:

| Directory | What it holds | Rebuild with |
|---|---|---|
| `output/data/` | each report's extracted **data** as JSON (19) | `sars data` |
| `output/template_html/` | HTML rebuilt **from that data** (19) | `sars template` |
| `output/template_pdf/` | those templates printed to A4 (19) | `sars template` |
| `output/html/`, `output/pdf/` | the conversion path's output (19 each) | `sars all` |
| `output/compare/` | **one** image per report, `<name>.jpg`, overwritten in place: a single `REFERENCE \| TEMPLATE \| DIFF` panel (19) | `tools/compare.py` (add `--conversion` for the conversion PDF) |

Each report has exactly one comparison file, `output/compare/<name>.jpg`, and it
is overwritten on every run — no per-page, per-kind, or diagnostic variants pile
up. The panel shows the reference PDF, the data-driven template output, and a
lossless red-on-white diff heatmap whose label carries the exact / visible
pixel-match percentages (or a "size mismatch" notice when page sizes differ).
`tools/pixel_diff.py` prints the detailed numeric metrics (MAE/RMSE/PSNR, exact
and visible match) and writes no image files.

The conversion path is unaffected and still reports `19/19 documents pass; mean
text similarity 100.00%`.

### Known remaining gaps in the templated path

Measured, per report, in `docs/FIDELITY_REPORT.md`. In summary:

- **Nothing is at 100% yet**, so the gate fails and the work is IN PROGRESS by
  the definition in `docs/FIDELITY_SPEC.md` §10. The worst page across all 19 is
  90.93% visible; nine reports are at or above 98%.
- Geometry and colour are already exact where the rebuild landed: e.g.
  `MWANZA CC SCHOOLS RANK` reproduces 762/762 of the reference's rectangles
  identically, `MWANZA CC Wards Rank` 337/337.
- The bulk of the residual is sub-pixel glyph-edge antialiasing: the oracle replay
  in `tools/replay.py`, which places the reference's own glyphs at the
  reference's own origins, itself tops out at 99.95% visible on a page — that is
  this toolchain's ceiling, and it is documented with measurements in
  `docs/FIDELITY_NOTES.md` §4.
- `S1051-MKOLANI SECONDARY SCHOOL` (90.93%) and `MWANZA CC 10 BEST STUDENTS`
  (93.83%) still have bands whose recovered data binding is partly wrong — a
  handful of values land in the wrong row group and a few are missing. These two
  need the one-report-at-a-time treatment `docs/FIDELITY_SPEC.md` §8 prescribes.

## Note on duplicate input

`Mwanza Schools Rank For Governments.html` and
`Mwanza Schools Rank For Governments (1).html` are byte-identical copies of the
same report; both are converted so the output set mirrors the input set.
