# Conversion approach decision (FEAT-002 checkpoint)

**Decision: `per-file` precise conversion.**

Keep `src/sars_convert/converter.py` as a geometry **assist/scaffold** tool
(matrix parsing + row/column clustering helpers), not as the batch production
converter. Each report is converted with a small, precise per-document builder
that emits pure semantic HTML+CSS, verified against its reference PDF.

## Why (evidence from the S1051 sample)

The prototype generic converter was run on
`data/sars/S1051-MKOLANI SECONDARY SCHOOL.html` (13 pages, ~3271 runs,
landscape 1056x816). It correctly parsed every run (text + X/Y from
`transform:matrix(...)` + resolved `.cN` font info) and its row clustering is
solid: sub-pixel baseline jitter (e.g. name at Y=303.8 next to its number
cells at Y=304.4) is absorbed cleanly, so **rows are reliable**.

**Columns and blocks are not.** A single geometric table model per page is the
wrong shape for these reports. Concrete, reproduced failure modes:

1. **Multiple distinct tables share one page.** Page 0 holds a *title block*
   (5 centred lines), a *DIVISION PERFORMANCE SUMMARY* pivot (SEX rows F/M/T x
   division columns I/II/III/IV + totals), and the *main student results* table
   (CNO, CANDIDATE FULL NAME, SEX, AGGT, DIV, POS, DETAILED SUBJECTS). Pooling
   every run's X across the whole page produces **13 misaligned column bands**
   — none of the three blocks actually has 13 columns. The pivot's columns and
   the results table's columns do not line up, so the merged model is garbage.
2. **Non-table blocks get forced into a table.** The title lines become table
   rows padded with ~20 empty cells each.
3. **Multi-row / grouped headers are not handled.** "DETAILED SUBJECTS" sits on
   its own Y (279.5) above the CNO/NAME/... header row (288.5); the SEX label
   spans the F/M/T rows of the pivot. A flat one-header-row model cannot express
   these spans.
4. **Fixed-tolerance 1-D X clustering is inherently fragile.** When a header's X
   differs from its data column's X (common here), the single logical column
   splits into multiple bands. This is demonstrated by
   `test_column_clustering_is_fragile_when_header_and_data_x_differ`.
5. **Free-text and sentinel cells.** DETAILED SUBJECTS is one long free-text run
   per student; ABS/blank rows (e.g. S1051-0019) shift the AGGT/DIV/POS cells.
   These need per-column semantics, not generic geometry.
6. **Rotated `.vec` layers** exist and must be filtered (the prototype already
   drops rotated runs), but any rotated *text* would need bespoke handling.

Making the generic detector robust would mean building block segmentation,
multi-row header inference, per-block column models, free-text column
detection and sentinel handling — a large, fragile surface that the user
explicitly warned against ("if we shall lose much time designing the detector
... better convert them one by one with precision"). Faithfulness of the final
output is the priority, and per-file conversion reaches faithful output faster
and more reliably here.

The good news: the reports are **highly regular within a category**. The region
files are a single wrapping table; the council files are a few tables. So a
per-file (really per-*template*) builder is cheap: a handful of parameterised
layouts covers the whole batch.

## Plan for FEAT-003

1. Reuse the tested helpers from `converter.py` (`parse_matrix`, `parse_runs`,
   `parse_font_classes`, `parse_page_size`, `cluster_rows`) as the parsing/geometry
   substrate — rows are trustworthy, so lean on them.
2. Build a small precise per-template builder (e.g. `builders/` or functions in
   a module) that, for each known report layout:
   - segments the page into blocks by Y gaps (title / summary pivot / results);
   - emits the title block as centred `<h1>/<h2>` headings (not a table);
   - emits the summary pivot with its correct grouped header
     (SEX x I/II/III/IV + totals);
   - emits the results table with the fixed, known column set
     (CNO, CANDIDATE FULL NAME, SEX, AGGT, DIV, POS, DETAILED SUBJECTS),
     assigning runs to those known column X-anchors rather than to
     auto-discovered bands, and keeping DETAILED SUBJECTS as free text;
   - repeats the header per page and concatenates page bodies.
3. Emit pure semantic HTML + external/embedded CSS (no absolute positioning, no
   transforms, no `.cN` pooled classes) with the correct `@page` size/orientation
   per document (portrait: `Mwanza f2 Mock Mobility 2026`,
   `Mwanza School Rank-EDK`, `Mwanza School Rank-English Language`,
   `MWANZA CC SCHOOLS RANK SUBJECTWISE`; all others landscape).
4. Verify each generated HTML by rendering with WeasyPrint (FEAT-004) and
   comparing to the reference PDF page-by-page with pymupdf rasterisation
   (FEAT-005); iterate the per-template builder until faithful.
5. Start with the S1051 / region single-table template (it covers the most
   files), then add the council multi-table template.
