# sars-convert

Convert the messy `pdf2html` fixed-layout HTML dumps of Tanzanian school-ranking
reports into **pure, clean, semantic HTML+CSS**, then print them with
**WeasyPrint** to **A4** (landscape or portrait per document). The original PDFs
that shipped alongside the HTML are kept only as **ground truth** to confirm, at
the very end, that the clean output reproduces them exactly.

---

## 1. Purpose

The `data/sars/` inputs are automated `pdf2html` conversions of school and
council/region performance reports (SARS - School Academic Ranking System style
reports). They *render* like the original PDFs, but the HTML underneath is a mess:
every glyph run is an absolutely-positioned `<div>` placed by a CSS transform,
there is no real document structure, and the "tables" carry no visual layout.

The goal of this project is to turn that mess into **pure clean HTML + CSS** that:

1. reproduces the source report **exactly** (same rows, columns, text, order), and
2. **prints via WeasyPrint** to an **A4** page in the correct orientation
   (landscape or portrait) for each document.

The report content is **mostly tabular** (rankings of schools, students, wards,
subjects), but the tables are complex (multi-column, grouped, sometimes multiple
tables per document). Reconstructing real `<table>` markup from the geometry is
the core of the work.

The reference PDFs are **ground truth used only to verify fidelity at the end**.
They must **never be modified**.

---

## 2. Source data model (what `pdf2html` produced)

Each source HTML is a "fixed-layout, faithful page reproduction" dump. Per page:

- A `.page` `<div>` sized in **pixels**. Each document declares its page box via
  `@page { size: <w>px <h>px }` at **96 DPI / US-Letter**:
  - `1056px 816px` = **landscape**
  - `816px 1056px` = **portrait**
- Text is emitted as many absolutely-positioned runs:
  `<div class="t cN">...text...</div>`.
- Position, rotation and scale of each run are carried by a CSS transform:
  `transform: matrix(a, b, c, d, X, Y)` where **X / Y are pixel offsets** of the
  run on the page.
- Font family, size and colour are **pooled** into generated classes (`.c0`,
  `.c1`, ... referenced as the `cN` in `class="t cN"`) defined in the page
  `<style>`.
- Coarse semantic markup **already exists** as
  `<table role="table" style="display:contents">` - but `display:contents` means
  it contributes **no visual layout**, and the grouping is coarse (region files
  wrap everything in a single table; council files use several).
- A few decorative `.vec` SVG layers may exist; the S1051 sample has no `.bg`/`.im`
  raster layers.

**Key insight for reconstruction:** runs that belong to the same table **row**
share (approximately) the same **Y** coordinate; **columns** are separated by
distinct **X** bands. So a clean table can be rebuilt by parsing X/Y out of each
`matrix(...)`, clustering runs into rows by Y, splitting rows into columns by X
bands, and emitting a real `<table>`.

---

## 3. Conversion approach

A generic geometry converter was prototyped and evaluated on the standalone
`S1051-MKOLANI SECONDARY SCHOOL` sample first (see `DECISION.md`). It proved
**fragile**: a single page-wide column model shatters the grouped multi-row
headers (e.g. `NUMBER OF CANDIDATES -> REGISTERED/SAT -> F/M/T/%` and
`DIVISION PERFORMANCE -> I/II/III/IV/0/I-III/I-IV -> F/M/T/%`) into dozens of
misaligned empty cells. Per the top priority - **faithfulness of the final
output** - we do **not** keep polishing a detector.

**The approach we use instead (per-document, precise, PDF-driven):**

1. **Recover the real tabular data and grid from the ORIGINAL reference PDFs**
   using [`pdfplumber`](https://github.com/jsvine/pdfplumber). The PDFs are the
   ground truth for *what data is tabular and how it is structured* - pdfplumber
   returns the full grouped header and every data cell cleanly, where the messy
   HTML geometry does not. ([Tabula](https://tabula-technology.github.io/) is a
   documented alternative for stubborn tables.)
2. **Label the recovered grid with domain sense.** These are school exam results
   aggregated across a hierarchy - **schools within wards, wards within councils,
   councils within regions** - so we know which cells are headers, which are
   ranking columns (`S/NO.`, `POS`, `C/RANK`), which are entity names
   (`SCHOOL NAME`, `CANDIDATE FULL NAME`, `WARD`), which are grouped numeric
   spans, which are totals, and which are free text (`DETAILED SUBJECTS`).
3. **Rebuild each document as pure, clean HTML+CSS** with real semantic
   `<table>`/`<thead>`/`<tbody>` and grouped spanned `<th>`, **preserving
   positions and all styles**: the original fonts, sizes, weights and colours,
   the cell borders and header tints, per-column alignment, the conditional
   percentage-cell shading (green ~100%, graded orange/red for lower values) and
   the rotated `C/RANK` header - so the clean output *looks like* the reference
   PDF, not a generic re-theme.
4. **Render to A4** (landscape or portrait per document) with WeasyPrint, and
5. **Verify** each generated PDF against its reference PDF (ground truth).

This is done **per document / per template**, not by a generic auto-detector.
The reports are highly regular within a category (S1051 student-list; council
multi-table reports; region single-table reports), so a small set of
per-category profiles covers the whole batch precisely. We prove the workflow on
S1051 first, then a council report, then apply it to the rest.

The pipeline stages (see `src/sars_convert/`):

| Stage | Module | Responsibility |
| --- | --- | --- |
| Extract | `extract.py` | recover tabular data + grouped-header structure from the **reference PDFs** via pdfplumber, into a domain-labelled IR (`output/ir/*.json`) |
| Build | `build_html.py` | IR -> pure, clean semantic HTML+CSS, preserving all styles |
| Render | `render.py` | clean HTML -> A4 PDF via WeasyPrint (orientation per doc) |
| Verify | `verify.py` | compare generated PDF vs. reference PDF (ground truth) |

`converter.py` is retained as a tested geometry **assist** (matrix/font/run
parsing used for cross-checking recovered text), not the production converter.

---

## 4. Repo layout

```
mussannoni/
├── README.md                 # this file (authored first)
├── pyproject.toml            # package + deps (Python >= 3.11)
├── .python-version           # pyenv local -> 3.11.15
├── .gitignore                # ignores output/ and caches; keeps data/sars/
├── sars.zip                  # original bundle (kept for provenance)
├── data/
│   └── sars/                 # extracted inputs + ground-truth PDFs (tracked)
│       ├── council_html/     # 7 source HTML (council reports)
│       ├── council_pdf/      # 7 reference PDFs (ground truth)
│       ├── region_html/      # 11 source HTML (region reports)
│       ├── region_pdf/       # 11 reference PDFs (ground truth)
│       ├── S1051-MKOLANI SECONDARY SCHOOL.html   # standalone sample
│       └── S1051-MKOLANI SECONDARY SCHOOL.pdf    # standalone reference
├── src/
│   └── sars_convert/
│       ├── __init__.py
│       ├── __main__.py       # CLI entry point (extract -> build -> render)
│       ├── converter.py      # tested geometry assist (matrix/font/run parsing)
│       ├── extract.py        # pdfplumber data + structure recovery -> IR
│       ├── build_html.py     # IR -> clean semantic HTML+CSS (style-preserving)
│       ├── render.py         # clean HTML -> A4 PDF via WeasyPrint
│       └── verify.py         # generated PDF vs. reference PDF fidelity check
├── output/
│   ├── ir/                   # recovered per-document IR JSON (git-ignored)
│   ├── html/                 # generated clean HTML (git-ignored)
│   └── pdf/                  # generated PDFs (git-ignored)
└── tests/
```

`output/` is a **build artifact** directory and is git-ignored. `data/sars/`
(source HTML + reference PDFs) is intentionally **tracked** - it is the input and
the ground truth.

---

## 5. Setup and usage

Requires **Python 3.11+**. A `pyenv local 3.11.15` is pinned via
`.python-version`; alternatively create a virtual environment.

```bash
cd mussannoni

# (option A) use the pinned pyenv version
pyenv local 3.11.15

# (option B) create a venv
python3.11 -m venv .venv && source .venv/bin/activate

# install the package (editable) plus dev tools
pip install -e '.[dev]'
```

WeasyPrint (with its native Pango / Cairo / HarfBuzz libraries) is expected to be
available in the environment; confirm with:

```bash
python -c "import weasyprint; print(weasyprint.__version__)"
```

For verification imaging you need to rasterise PDFs. `pymupdf` + `pillow` are
included in the `dev` extra; `poppler-utils` (`pdftoppm` / `pdfinfo`) is an
alternative if installed on the system.

Planned usage once the pipeline is implemented (later features):

```bash
# convert -> clean HTML in output/html/, render -> A4 PDF in output/pdf/
sars-convert
```

---

## 6. Per-document A4 orientation

Each document is printed to A4 in the orientation that matches its original page
box. **Portrait** documents (source `816px 1056px`); everything else is
**landscape** (source `1056px 816px`).

| Document | Orientation |
| --- | --- |
| Mwanza f2 Mock Mobility 2026 | **Portrait** |
| Mwanza School Rank-EDK | **Portrait** |
| Mwanza School Rank-English Language | **Portrait** |
| MWANZA CC SCHOOLS RANK SUBJECTWISE | **Portrait** |
| S1051-MKOLANI SECONDARY SCHOOL | Landscape |
| MWANZA CC 10 BEST SCHOOLS | Landscape |
| MWANZA CC 10 BEST STUDENTS | Landscape |
| MWANZA CC 10 BEST STUDENTS SUBJECTWISE | Landscape |
| MWANZA CC SCHOOLS RANK | Landscape |
| MWANZA CC SUBJECTS RANK | Landscape |
| MWANZA CC Wards Rank | Landscape |
| Mwanza Best Students-Overall | Landscape |
| Mwanza Best students-Subjectwise | Landscape |
| Mwanza f2 District Performance | Landscape |
| Mwanza Overall Subjects Performance | Landscape |
| Mwanza Schools Rank For Governments | Landscape |
| Mwanza Schools Rank For Governments (1) | Landscape |
| Mwanza schools rank Overall | Landscape |
| Mwanza Top 10 Schools | Landscape |

**Rule of thumb:** exactly four documents are portrait
(*Mwanza f2 Mock Mobility 2026*, *Mwanza School Rank-EDK*,
*Mwanza School Rank-English Language*, *MWANZA CC SCHOOLS RANK SUBJECTWISE*); all
other documents are landscape.
