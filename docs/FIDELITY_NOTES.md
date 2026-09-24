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
differs by a fraction of a point, and 100% *visible* needs glyph positions to be
right to the last hundredth of a point.** That is the honest limit this work runs
into, and it is why the gate still fails (see `docs/FIDELITY_REPORT.md`).

### The ceiling per report, and what is still winnable

The replay was measured for all 19 (`output/fidelity/ceiling.txt`) and its numbers
are a column in `docs/FIDELITY_REPORT.md`, so "how much is left" is explicit
rather than a guess:

* one report, `Mwanza School Rank-EDK`, replays at **100.0000% visible** — proof
  that the spec's target is physically reachable at least there, and that its
  remaining 0.83 pt is our renderer's, not the toolchain's;
* the other ceilings sit between **99.54% and 99.98%** visible;
* our renderers are now **0.09 to 2.87 pt** below their own ceiling; four reports
  are within 0.2 pt of it (`Mwanza Top 10 Schools` +0.09, `MWANZA CC SUBJECTS
  RANK` +0.16, `MWANZA CC SCHOOLS RANK` +0.17, `MWANZA CC 10 BEST SCHOOLS` +0.19).

On the page in the review (`MWANZA CC SCHOOLS RANK`, 8431 glyphs at 4 pt) the
breakdown is: 762/762 rectangles identical, no missing text, 0.51% of pixels
visibly different, of which 79% lie within one pixel of reference ink (glyph and
rule edges) and no 8x8 block is wholly wrong — i.e. no wrong fill and nothing
missing, only sub-pixel edges. The replay of that same page scores 99.66% against
our 99.49%.

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

## 6a. Advances: what the reference *declares* is not what it *does*

A `/Widths` array is not the last word on how wide the reference steps. The school
slip declares several font objects for Arial with different width arrays, and MuPDF
steps text with whichever one that run references — so a run could start in exactly
the right place and still walk up to 1.2 pt out of position by the end of a long
cell (`HTM - 54'C' BUSI - 23'F' …`). Measured on the slip: Arial `H` steps 714/1000
where `/Widths` says 722, `T` 624 vs 611, the space 285 vs 278.

`tools/build_fonts.py` therefore **measures** advances from the reference's own
consecutive glyph origins (median per character, per document) and writes those
into the asset's `hmtx`, falling back to `/Widths` for characters never seen twice
in a row. The asset key includes those measurements, so two documents that name
the same face but step it differently get their own asset.

Effect: the school slip went from **90.93% → 97.14%** visible, and the worst page
across all 19 reports from **90.93% → 96.997%**.

## 6b. Values are audited, not assumed: `tools/slot_audit.py`

The pixel gate says a page is 9% wrong; it does not say "the TOTAL row lost its
387". `tools/slot_audit.py` walks every band of every report, asks the renderer's
own data provider for each row, and compares against the text the reference printed
in that cell — classifying each disagreement as `EMPTY` / `DIFFERENT` / `UNBOUND`,
and saying whether the printed text exists anywhere in the extracted data (a gap)
or not (chrome). It found four distinct defects that pixels alone had hidden:

1. **TOTAL rows silently blank.** A band was bound to one row group, so columns
   whose values live elsewhere in the data (the label `TOTAL`, the summary
   percentages `2.98 / 48.99 / 97.02`, the school count `387`) had no binding at
   all. Bindings are now resolved **per column**, each to the group that can
   supply it.
2. **Repeated column headings eating data rows.** Reports reprint their headings
   part-way down a page, inside the drawn band. Walking band and data in lockstep
   put every later row on the wrong data row — 336 of one report's 730 printed
   values were blank. Rows are now aligned greedily; a row no nearby data row
   explains is moved into the chrome (drawn exactly where the reference draws it)
   and does not consume a data row.
3. **Two values welded into one.** A school name wider than its column has its
   centre in the *next* column, so cell matching on centres stole it and
   interleaved it with that column's own value (`STAR REACHERS GIRLS APRIVATE`,
   ownership left empty). Spans are now matched to the cell they *start* in, and
   split at real run boundaries (`sars.extract.run_starts`).
4. **Rowspan cells collapsing their rows.** A cell spanning four rows with one
   line per row was joined into `IMEPANDA IMEPANDA IMEPANDA IMEPANDA` on the first
   row, leaving three blank. Lines are now distributed across the rows they span.

Result across all 19 reports: **79 190 of 79 408 printed values reproduced
exactly, 16 of 19 reports with zero content disagreements** (was 862 disagreements,
including 514 outright blanks).

## 6c. Cells are drawn as the reference draws them

Two more fidelity rules came out of this:

* Cell samples are read from the **clipped** extraction, because these documents
  clip a value to its cell — the raw operators carry glyphs the reference hides.
* A cell's text is stored as **pieces**, one per run with its own x. A subject
  breakdown is drawn as several runs with wide gaps; re-emitting it as one string
  spaces those pieces by our own space advance instead of the reference's gaps.

## 7. Where the remaining error is

Per report numbers live in `docs/FIDELITY_REPORT.md`. The shape of the residual:

* **Everything geometric is already exact** on every rebuilt report: e.g.
  `MWANZA CC SCHOOLS RANK` reproduces 762/762 of the reference's rectangles
  identically, `MWANZA CC Wards Rank` 337/337, the school slip 2671/2671 on page 1
  and 3983/3983 on page 12 — no missing, no shifted.
* **Content is essentially exact**: 79 190 / 79 408 printed values, with 16 of 19
  reports at zero disagreements. The residue is 218 values in three reports:
  * `Mwanza f2 Mock Mobility 2026` — 168 cells of a rowspan column where the
    reference prints a status per row and the extractor still yields one;
  * `Mwanza Top 10 Schools` — 15 numbers on page 2 whose column binding is
    ambiguous (many equal values voted for the wrong field path);
  * `S1051-MKOLANI SECONDARY SCHOOL` — 5 cells, and
    `MWANZA CC SCHOOLS RANK SUBJECTWISE` — 8 cells, at page boundaries.
* The rest is **sub-pixel glyph-edge antialiasing**, which is the ceiling measured
  in §4: the oracle replay, placing the reference's own glyphs at the reference's
  own origins, itself reaches 99.95% visible and ~80% exact. Several reports are
  now within a few hundredths of a point of that ceiling (`Mwanza Top 10 Schools`
  99.81%, `MWANZA CC 10 BEST SCHOOLS` 99.74%, `MWANZA CC Wards Rank` 99.65%).

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
uv run python tools/slot_audit.py            # every printed value, checked
uv run python tools/replay.py | grep ceiling > output/fidelity/ceiling.txt
uv run python tools/fidelity_report.py output/fidelity/current.json \
    --baseline output/fidelity/baseline.json --ceiling output/fidelity/ceiling.txt
```

Diagnostics: `tools/slot_audit.py` (is every value the reference prints actually
filled in?), `tools/drift.py` (glyph and rectangle level differences),
`tools/replay.py` (the ceiling), `tools/engine_bakeoff.py` (engine choice),
`tools/pixel_diff.py` (single-page metrics).
