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

## 3. Conversion approach and the pragmatism principle

The intended path is a **geometry-based table-reconstruction converter**: read
the `matrix(...)` offsets, cluster text runs into rows and columns, and emit clean
semantic HTML+CSS.

**Pragmatism steer (top priority = faithfulness of the FINAL OUTPUT):**

> Attempt the generic geometry-based converter, but **evaluate it on the standalone
> `S1051-MKOLANI SECONDARY SCHOOL` sample FIRST**. If that generic detector proves
> **fragile or time-costly**, do **not** keep polishing the detector - **fall back
> to precise, per-file hand conversion** instead. We would rather convert the
> documents one by one with precision and ship exact output than lose time
> designing a clever detector that converts foolishly. The fidelity of the final
> printed A4 PDF is what matters, not the elegance of the pipeline.

The decision (generic converter vs. per-file conversion) is made on S1051 first,
then applied to the rest.

The pipeline has three stages (see `src/sars_convert/`):

| Stage | Module | Responsibility |
| --- | --- | --- |
| Convert | `converter.py` | mess `pdf2html` HTML -> clean semantic HTML+CSS |
| Render | `render.py` | clean HTML -> A4 PDF via WeasyPrint (orientation per doc) |
| Verify | `verify.py` | compare rendered PDF vs. reference PDF (ground truth) |

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
│       ├── __main__.py       # CLI entry point (stub for now)
│       ├── converter.py      # placeholder (later feature)
│       ├── render.py         # placeholder (later feature)
│       └── verify.py         # placeholder (later feature)
├── output/
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
