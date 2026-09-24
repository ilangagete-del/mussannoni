# Fidelity notes — what the reference documents actually are, and what that costs

Working notes for the pixel-fidelity work required by `docs/FIDELITY_SPEC.md`.
Everything here is measured in this repository with the tools named; nothing is
assumed. Read it before touching a renderer — several of these findings cost
hours to recover and are invisible from the code.

## 1. The reference PDFs are two different animals

| Set | Producer | Fonts |
|---|---|---|
| 7 council sheets + the school slip | `Microsoft® Excel® LTSC` | Arial / Arial Bold / Times New Roman Bold are **named but not embedded**; Arial Narrow Bold and Tahoma Bold *are* embedded as subsets |
| 11 region sheets | `Microsoft: Print To PDF` | the real **Arial, Arial Bold, Times New Roman Bold, Arial Narrow Bold, Calibri, Calibri Bold are embedded in full** (`Identity-H` CID fonts, 90–580 KB each) |

Consequences for reproduction, since the gate rasterises through MuPDF:

* For the **region** files MuPDF draws the embedded faces. Reproducing them means
  using *those very files* — so `tools/build_fonts.py` extracts them out of the
  reference PDFs. Their `/W` widths were verified to agree with the fonts' own
  `hmtx` on every document, so the files are used untouched.
* For the **council** files MuPDF substitutes its built-in URW Nimbus base-14
  faces and takes advances from the PDF's `/Widths` array. So the reproduction
  needs Nimbus **with those widths written into `hmtx`** — which is what the tool
  synthesises. The Arial Narrow / Tahoma subsets in those files are extracted as
  usual.

Verified: the URW `NimbusSans-Regular/Bold` and `NimbusRoman-Regular/Bold` OTFs
from [ArtifexSoftware/urw-base35-fonts](https://github.com/ArtifexSoftware/urw-base35-fonts)
rasterise **bit-identically** (100.0000% exact, max delta 0) to PyMuPDF's
built-in `helv` / `hebo` / `tiro` / `tibo`. That is why they are a legitimate
stand-in for what MuPDF draws.

## 2. The sandbox had no Arial at all

Only Noto Sans is installed here (`fc-list`), so before this work *every*
templated report was printed in Noto Sans while the reference showed Arial. That
single fact explains most of the honest 38–90% baseline: the geometry was only
part of the problem.

`tools/build_fonts.py` installs the derived faces into
`~/.local/share/fonts/sars` and runs `fc-cache`, so WeasyPrint finds them by
family name. The faces are **not committed**: they are build output derived from
the committed `sars.zip`, and redistributing Monotype's Arial is not ours to do.

## 3. Placing a baseline exactly requires calibration, not arithmetic

An absolutely positioned box's top edge is not its baseline. The distance between
them depends on the engine's half-leading rules and the font's metrics, so
`sars.fonts.baseline_offset` **measures** it: it renders a one-glyph probe through
the print engine, reads the glyph origin back out of the produced PDF, and caches
the number per `(engine, family, size)` in `assets/fonts/calibration.json`.

Two lessons paid for in pixels:

* Calibrating once and scaling by font size leaves ~0.2 pt of error (WeasyPrint's
  half-leading is not exactly proportional). Calibrate per size.
* The probe glyph must exist in the face. Several reference faces are subsets
  with a 15–20 character cmap; probing them with `x` fell back to another font
  and calibrated the *wrong* face — again ~0.2 pt, which is a visible half pixel
  at the gate's raster.

## 4. How close this toolchain can get: the oracle replay

`tools/replay.py` rebuilds a reference page from the reference's **own**
primitives — every filled rectangle, every glyph at the exact origin the PDF
places it — as absolutely positioned HTML, prints it, and gates it. That is the
ceiling for any renderer here.

Measured on `MWANZA CC Wards Rank` page 1 (WeasyPrint):

| stage | visible | exact |
|---|---:|---:|
| all glyphs upright, wrong (substituted) fonts | 61.68% | — |
| correct faces + per-glyph origins | 99.58% | 79.47% |
| + rotated captions rotated | 99.76% | 79.60% |
| + per-size baseline calibration | 99.93% | 79.69% |
| + probe glyph present in the face | **99.95%** | 79.70% |

Glyph drift at that point: 2018/2018 glyphs matched, `dy` within 0.0001 pt,
`dx` within 0.0003 pt. The residual 0.05% is glyph-edge antialiasing, and the
gap between `exact` and `visible` is the same thing: a sub-pixel edge that lands
on a different side of a pixel boundary.

**So 100% exact is not reachable through an HTML engine while any glyph position
differs by a fraction of a point, and 100% *visible* is only reachable if every
glyph position is bit-identical.** That is the honest limit this work runs into,
and it is why the gate still fails (see `docs/FIDELITY_REPORT.md`).

## 5. WeasyPrint vs Chromium — measured, not assumed

Both engines are wired (`sars.printing`), and `tools/engine_bakeoff.py` prints
every report through both, gates both, and records the winner in
`assets/engine_choice.json`. Result: **WeasyPrint wins all 19**, by 3 to 20
points, e.g.

| Report | WeasyPrint | Chromium |
|---|---:|---:|
| Mwanza Schools Rank For Governments | 93.08% | 73.02% |
| MWANZA CC Wards Rank | 98.00% | 89.66% |
| Mwanza f2 District Performance | 98.56% | 95.54% |

Chromium's text placement drifts up to ~0.37 pt in both axes (0/2018 glyphs
within 0.01 pt, 15.7% within 0.1 pt), because it quantises positions on its own
grid. The engine choice stays in the code — it is measured per report and can be
re-measured if either engine changes.

## 6. What the recovered layout specs learned the hard way

`tools/build_layout_specs.py` writes `src/sars/templates/layouts/<report>.json.gz`:
the page box, the paint sequence of every rectangle, every chrome glyph at its
own origin, and for each band the column boxes, row pitch, per-row fills, fonts,
sizes, alignment, baseline offsets and the recovered data binding.

* **Paint order is not decorative.** These documents paint a column's
  full-height wash early and the hairline row rules late. Grouping a band's
  rectangles per row (instead of keeping the reference's order) let the next
  row's wash bury the previous row's rule and cost 3–4 points on six reports.
* **One owner per rectangle.** A rule sitting on a row boundary claimed by both
  neighbouring rows is drawn twice, at two offsets — stray black lines.
* **Merged cells centre in the merge**, not in their first lattice column; using
  the lattice column put values half a column off.
* **Samples must keep their spaces.** Recovered cell text is matched against the
  data to recover the binding; `Grade C (Good)` stripped to `GradeC(Good)`
  matches nothing, and the column silently loses its value.
* **Alignment is recovered, not guessed** (left / centre / right and the padding),
  and so is the residual `xfix`: the reference's cell box is not the rectangle
  lattice to the last fraction of a point, and that fraction is ~0.4 pt here —
  around one pixel at the gate's raster.
* Reference run starts are quantised on a ~0.02 pt grid, and the offsets within
  a column vary by ±0.05 pt in a way no simple formula reproduced. Where the data
  reproduces the string the reference printed, the spec's recovered position is
  used verbatim; only genuinely new values are placed by computation.

## 7. Where the remaining error is

Per report numbers live in `docs/FIDELITY_REPORT.md`. The shape of the residual:

* **Everything geometric is already exact** on the reports that were rebuilt:
  e.g. `MWANZA CC SCHOOLS RANK` reproduces 762/762 of the reference's rectangles
  identically, and `MWANZA CC Wards Rank` 337/337.
* The remaining diff is text: sub-pixel edge noise where positions agree, plus a
  minority of values placed a few tenths of a point off, plus — on
  `S1051-MKOLANI SECONDARY SCHOOL` and `MWANZA CC 10 BEST STUDENTS` — bands whose
  recovered data binding is still partly wrong (21–62 glyphs missing on a page,
  values landing in the wrong row group). Those two need the per-report treatment
  `docs/FIDELITY_SPEC.md` §8 prescribes.

## 8. Reproducing all of this

```bash
uv run python tools/build_fonts.py          # derive + install the reference faces
uv run sars data                            # extract each report's data
uv run python tools/build_layout_specs.py   # recover each report's chrome
uv run sars template                        # data -> HTML -> PDF
uv run python tools/compare.py              # one REFERENCE | TEMPLATE | DIFF image each
uv run python tools/fidelity_gate.py --json output/fidelity/current.json
uv run python tools/fidelity_report.py output/fidelity/current.json \
    --baseline output/fidelity/baseline.json
```

Diagnostics: `tools/drift.py` (glyph and rectangle level differences),
`tools/replay.py` (the ceiling), `tools/engine_bakeoff.py` (engine choice),
`tools/pixel_diff.py` (single-page metrics).
