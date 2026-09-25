# Packaging: install it, call it, get a document

```console
$ pip install sars-convert
```

```python
from sars import api

pdf = api.render_pdf(data, report_type="schools_rank", out_path="rank.pdf")
```

That is the whole point of the package, and it works from a clean install with
nothing else configured — verified by `tests/test_api_and_packaging.py`.

| built artefact | size |
|---|---:|
| wheel | **7.1 MB** |
| sdist | 6.8 MB |
| installed, uncompressed | 16.1 MB |

Well inside the 100 MB ceiling, with all 56 reference faces and all 19 recovered
layouts included.

---

## The public API

`sars.api` is the supported surface. Everything else is machinery.

| function | does |
|---|---|
| `render_html(data, report_type=None, *, stage=None, grow=False)` | a standalone HTML document |
| `render_pdf(data, report_type=None, out_path=None, *, stage=None, grow=False)` | a PDF: bytes, or the path written |
| `report_types(stage=None)` | what can be rendered |
| `available_reports(stage=None)` | every layout + the descriptor that selects it |
| `data_contract(layout)` | the exact field paths a layout reads |

`data` may be a `sars.schema` instance, a `dict`, or a JSON string — all three
produce identical output. `docs/DATA_STRUCTURE.md` is the contract for its shape.

Two things are refused rather than guessed, because a wrong document that looks
right is worse than an error:

* an unknown `report_type` raises `api.UnknownReportType` listing what *is*
  renderable — it does **not** fall back to the generic table renderer;
* an unresolvable layout raises `layout_spec.LayoutSpecMissing` listing what
  exists — it does **not** print your data in the shape of another report.

---

## Fonts: bundled, because there is no fallback

### Why they ship inside the package

The reference documents embed real Arial, Arial Bold, Arial Narrow Bold, Times
New Roman Bold, Calibri and Tahoma Bold (and name URW Nimbus for the ones that
embed nothing). Every x position in a rendered report is computed from *those*
faces' advance widths, and every baseline from a calibration measured against
them.

Without them nothing crashes — and that is the danger. WeasyPrint silently
substitutes whatever it finds and still produces a plausible PDF. Measured, that
costs about **twelve points of fidelity**: every report falls from ~99% to ~87%
visible match with `max_delta 255`. A silent near-miss is this project's worst
failure mode, so:

* the faces are **package data** at `src/sars/assets/fonts/`, so a wheel install
  is sufficient;
* every API entry point calls `fontsetup.ensure()` first, which registers them
  with fontconfig once (idempotently, into the user font dir — never a privileged
  step) and then **verifies**;
* a face that cannot be resolved raises `fontsetup.FontsUnavailable` naming the
  missing families. It is never caught internally to substitute something else.

```console
$ sars fonts          # register + report; rendering does this automatically
fonts    56 face(s) installed -> ~/.local/share/fonts/sars
         all 56 reference face(s) resolvable
```

### The licensing position, stated plainly

Arial, Times New Roman, Calibri and Tahoma are **Monotype/Microsoft
proprietary faces**. The files here were extracted from the source PDFs, which
embed them as subsets. Redistributing them is **not** clearly ours to do, and
this repository previously excluded them from version control for exactly that
reason.

They are included now as a **deliberate, reversible decision**: the package is
meant to be installed and *verified* against the original documents, and it
cannot be without them. That trade-off is recorded here so it is a decision and
not an accident.

Nothing about the code depends on that choice. To ship without the proprietary
faces:

1. drop `src/sars/assets/fonts/SARS_Arial*`, `SARS_Times*`, `SARS_Calibri*` and
   `SARS_Tahoma*` from `[tool.setuptools.package-data]`;
2. keep `manifest.json` — it carries the advance widths and role mapping, which
   are measurements, not the fonts;
3. keep `upstream/Nimbus*.otf` (URW Nimbus is AGPL/GPL-with-font-exception and
   redistributable);
4. have the installer obtain the faces locally and run `sars fonts`.

`fontsetup.verify()` then does the right thing on its own: it reports precisely
which families are absent and refuses to render, instead of producing a document
in the wrong typeface. **No fallback font is added in that path either** — that is
the one line that must not be crossed, whatever else changes.

### The alternative that was considered

Embedding each face via `@font-face` with a `file://` URL would avoid touching
the user's font directory. It was not adopted because font *resolution* is the
one thing measured to be worth ~12 points of fidelity, and changing it is a
change to the thing the fidelity gate exists to protect. It is a reasonable
future change — behind the gate, with before/after numbers.

---

## Layouts are package data too

`src/sars/secondary/templates/layouts/*.json.gz` (2.8 MB, 19 files) is each
source document's recovered geometry: page sizes, the rectangle lattice, per-cell
fonts and colours, and the reference's own glyph origins. It cannot be
re-derived without the source PDFs, so it ships in the wheel.

A report type with no bundled layout cannot be rendered — `available_reports()`
is the definitive list, and asking for anything else raises.

---

## Module layout, and room for primary schools

Everything so far reproduces **secondary** school reports. Primary is coming. The
package is arranged so that it arrives as an addition, never a rename:

```
sars/
  api.py            the public surface
  stages.py         the seam: which stages exist, and what each owns
  layout.py         ─┐
  layout_spec.py     │  stage-agnostic mechanism.
  fonts.py           │  None of these know what a school is.
  printing.py        │
  binding.py         │
  schema.py         ─┘  (data has no stage)
  secondary/        one stage's own knowledge
    reports.py        which documents exist, and their classification
    competency.py     this stage's bands and GPA cut-offs
    templates/        a renderer per report type
      layouts/        each document's recovered geometry
  primary/          registered, planned, documented, empty
  assets/fonts/     the reference faces
```

The split is by **who owns the knowledge**, not by convenience. A stage owns its
documents, its layouts, its renderers and its grading scale; the drawing
mechanism is shared because placing a box and a baseline is the same work at any
stage.

Adding primary is therefore: write `sars/primary/` mirroring `sars/secondary/`
(the module docstring lists exactly what), register it in `stages.py`, and change
nothing else. `layout_spec` already searches every implemented stage for a
layout, and `api` already takes `stage=`. `tests/test_api_and_packaging.py`
asserts the seam holds — including that no shared module imports a stage at
module level, which is what would quietly re-couple them.

Primary is **not** assumed to share secondary's competency bands or GPA
cut-offs; that is precisely why grading lives per stage.

---

## Release checklist

The fidelity gate is the release gate. Nothing ships that lowers it.

```console
$ sars fonts                                   # faces resolvable
$ sars template                                # rebuild all 19 (~2m, parallel)
$ python tools/fidelity_gate.py --json output/fidelity/current.json
$ pytest -q                                    # includes the slow gate test
$ uv build && python -c "import zipfile,glob; \
    print(len(zipfile.ZipFile(glob.glob('dist/*.whl')[0]).namelist()))"
```

Then confirm against the previous numbers in `docs/FIDELITY_REPORT.md`: **no
report's worst page may drop, ever.** Tag before anything risky so it can be
undone in one command — `git tag pre-<change>` is the convention already in use
(`pre-generalize-templates-baseline`, `flexibility-green`, `data-contract-green`,
`parallel-green`).
