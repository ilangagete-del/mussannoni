# Decisions, with the measurements that settled them

Each entry records what was measured, not what was expected. Reproduce any of
them with the tool named in the entry.

---

## 1. Jinja2 does not own the row loop

**Decision: keep this project's own layout mechanism. Do not add Jinja2 as a
runtime dependency.**

Not because it is less faithful — it is provably *equally* faithful — but because
it cannot own the part of the work that matters, and buys nothing measurable.

Reproduce: `python tools/templating_bakeoff.py`

| report | byte-identical | ours | jinja2 | assembly as % of `render_pdf` |
|---|---|---:|---:|---:|
| MWANZA CC 10 BEST STUDENTS | **yes** | 0.067s | 0.073s | 0.3% |
| MWANZA CC SCHOOLS RANK | **yes** | 0.033s | 0.020s | 0.4% |
| MWANZA CC SUBJECTS RANK | **yes** | 0.007s | 0.004s | 0.3% |

### What the measurement shows

1. **Fidelity is not the discriminator.** A Jinja2 port produces a
   byte-for-byte identical document on every report tried, so it would not move
   the pixel comparison at all. (The first run reported a 1-byte difference; it
   was Jinja2 stripping the template's trailing newline —
   `keep_trailing_newline=True` — not a rendering difference. Worth stating
   plainly, because it would have been easy to mistake for evidence against
   Jinja2.)
2. **Speed cannot be the discriminator either.** HTML assembly is **0.3–0.4%**
   of producing a PDF. Jinja2 is sometimes slightly faster and sometimes
   slightly slower at it; either way it is rounding error against the ~99% spent
   in WeasyPrint.
3. **It cannot do the looping by itself — and this is the real reason.** Jinja2
   reached byte-identity only because it was handed a *draw list that Python had
   already positioned*. Every interesting decision in a row is a measurement:
   the x of a centred value comes from the reference font's own advance widths,
   the y from a baseline offset calibrated by rendering a probe through the
   engine, and the horizontal squeeze from comparing a measured string against
   the room the reference used. A template language cannot measure a string, so
   the loop would stay in Python and Jinja2 would only re-emit what Python had
   already decided.

### On "only the competency colour differs per row"

That is true of the *data*, and it is already how the code works: one loop over
rows, one set of cells per row, and the single per-row variation — the competency
wash — derived from the label by `sars.competency`. The looping is not the hard
part and never was.

It is *not* true of the emitted markup, which is why a template language buys
less here than it looks like it should: when a value equals the one the reference
printed, the cell replays the reference's **own glyph origins**, emitting one
positioned element per glyph rather than one per cell. That path is what makes
those cells pixel-exact, and it is per-glyph arithmetic, not markup repetition.

### If this is ever revisited

The bake-off tool stays in the repo, and Jinja2 stays in the `dev` extra, so the
claim can be re-measured rather than re-argued. The bar for adopting it: it must
stay byte-identical **and** show a benefit that is not rounding error against
WeasyPrint.

---

## 2. Reports are rendered in parallel; that is where the speed was

**Decision: render documents across worker processes, one per CPU by default.**

Reproduce: `time sars template` versus `time sars template --jobs 1`

| | wall clock |
|---|---:|
| sequential (previous behaviour) | **8m 54s** |
| parallel, 8 CPUs | **2m 06s** |

A 4.2× speed-up, with **byte-identical HTML and an unchanged fidelity gate**
(19/19 ≥98%, worst page 98.9822% before and after).

### Why here and nowhere else

Measured over all 19 reports, a full run is 526.8s, split:

| stage | time | share |
|---|---:|---:|
| WeasyPrint printing the PDF | 443.1s | **84%** |
| extracting data from the source | 83.6s | 16% |
| assembling the HTML | ~1.9s | **0.4%** |

Optimising HTML assembly — the part a templating change would touch — could at
best win 0.4%. Documents are independent, so the 84% parallelises directly.

The floor is now the single slowest document (`S1051-MKOLANI SECONDARY SCHOOL`,
~88s), which is what a 2m06s wall clock reflects. Going below it would mean
making one document's PDF cheaper, and the honest lever there is emitting fewer
elements — which the per-glyph replay path deliberately does not do, because that
path is what buys the fidelity. **Speed is not permitted to spend fidelity.**

### What made parallelism safe

* Longest documents are submitted first, so the slowest is never the last thing
  running while workers idle.
* The baseline-calibration cache is shared, so its write was made atomic
  (write-temp-then-`os.replace`) and merging (re-read before write). A key lost
  to a race is simply measured again; a truncated file would have broken every
  renderer.
* `--jobs 1` keeps the sequential path for debugging.

---

## 3. No fallback fonts, and a cut value is never marked

**Decision: a missing face is an error. Truncated text gets no ellipsis.**

The reference faces are *subsets* — several carry a cmap of about 19 characters.
Appending `…` to a value that had to be cut would make the renderer draw that one
glyph from some **other** family, which is a fallback font by the back door. A cut
value is therefore a clean prefix of the original.

This is also why font installation is checked rather than assumed: with the faces
missing, WeasyPrint silently substitutes Noto Sans and every report still renders
— at ~87% instead of ~99%, with `max_delta 255`. Silent near-success is the worst
possible failure mode for this project, so absence is made loud.
