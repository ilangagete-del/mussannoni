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
   per-run positional classes — the data is real table markup.
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

## Page orientation

Source page boxes are US-Letter (`792×612 pt` landscape, `612×792 pt` portrait);
output is normalised to A4 in the matching orientation.

| Orientation | Documents |
|---|---|
| **A4 portrait** | `MWANZA CC SCHOOLS RANK SUBJECTWISE`, `Mwanza School Rank-EDK`, `Mwanza School Rank-English Language`, `Mwanza f2 Mock Mobility 2026` |
| **A4 landscape** | all 15 others |

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
tests/                unit tests + end-to-end fidelity test
tools/probe.py        read-only PDF diagnostic
tools/compare.py      side-by-side reference/output page images
output/html/          generated clean HTML + styles.css
output/pdf/           generated A4 PDFs
output/compare/       visual comparison images
```

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
```

Requires Python ≥ 3.11. WeasyPrint needs the system Pango / Cairo / HarfBuzz
libraries, which are present in this environment.

## Usage

```bash
sars unpack             # extract sars.zip into data/sars (done automatically)
sars convert            # messy HTML sources -> pure HTML + CSS in output/html
sars render             # output/html -> A4 PDFs in output/pdf
sars verify             # compare output/pdf against the reference PDFs
sars all                # convert + render + verify
```

`sars.zip` is the single source of truth in the repository. `data/` and
`output/` are build artefacts and are not committed; every command extracts the
archive automatically if needed.

`sars list` prints the document inventory. Target a single document with
`--only`:

```bash
sars all --only "MWANZA CC 10 BEST SCHOOLS"
```

Inspect or eyeball a document:

```bash
python tools/probe.py "10 BEST SCHOOLS"      # grid, fonts, fill colours
python tools/compare.py "10 BEST SCHOOLS" 1  # reference | output, page 1
pytest -q                                    # unit + fidelity tests
```

## Result

All 19 documents reproduce their reference PDF exactly:

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

The clean output is also far smaller than the fixed-layout source: **18.1 MiB of
pdf2html dumps become 4.6 MiB of HTML + one 1 KB stylesheet (26 %)**, while
gaining semantic tables, real headers, and restylable CSS.

## Two implementations

The repository carries **two independent implementations** of the conversion,
built in parallel from the same brief. Both are installed by
`pip install -e .`, each with its own console script.

| | `sars` (`src/sars/`) | `sars-convert` (`src/sars_convert/`) |
|---|---|---|
| Console script | `sars` | `sars-convert` |
| Reads structure from | the **reference PDFs** — `pdfplumber` returns the cell rectangles the PDF itself draws | the **messy pdf2html HTML** — parses `transform:matrix()` runs, then clusters rows/columns |
| Per-report code | none; one generic path serves all 19 documents | a precise builder per report layout |
| Styling | recovered from the PDF (fonts, sizes, weights, text colour, cell fills) | authored per report family, with value-based shading on percentage cells |
| Documents covered | all 19, verified at 100 % text similarity | S1051 + region single-table layout, council layout in progress |

`sars` is the line this project continues on: reading the grid from the PDFs
makes it general, and recovering the fills from the PDF means the output's
colours are the report's real colours rather than a re-theme.

`src/sars_convert/` is kept because its analysis is worth preserving.
[`DECISION.md`](DECISION.md) records, with reproduced failure modes, *why*
clustering X/Y coordinates out of the pdf2html HTML was evaluated and rejected —
the evidence behind the "let the PDF define the structure" choice described
above. Its `converter.py` geometry helpers and its test suite document those
failure modes directly.

## Note on duplicate input

`Mwanza Schools Rank For Governments.html` and
`Mwanza Schools Rank For Governments (1).html` are byte-identical copies of the
same report; both are converted so the output set mirrors the input set.
