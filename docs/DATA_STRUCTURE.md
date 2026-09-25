# The data you feed the templates

This is the contract between *your data* and *a rendered report*. Everything here
is checked by `tests/test_data_contract.py`, so the examples below run.

There are only three things to get right:

1. the **shape** — which dataclass (or plain `dict`) the report type expects;
2. the **layout** — which recovered page geometry to print it in;
3. the **mode** — reproduce a reference document, or render all of your own data.

```python
from sars import schema, template_maker

data = schema.from_dict({...})                      # 1. shape
pdf = template_maker.render_pdf(                    # 2. layout via meta, 3. mode
    data.meta.report_type, data, "out.pdf", grow=True
)
```

---

## 1. Shape: `report_type` → schema class

`report_type` picks both the schema and the renderer. These are the only valid
values (`sars.schema.SCHEMA_BY_TYPE`, `sars.templates.RENDERERS`):

| `report_type` | schema class | one row is |
|---|---|---|
| `school_result_slip` | `SchoolResultSlip` | a candidate on one school's slip |
| `best_students` | `BestStudentsReport` | a ranked candidate, in titled sections |
| `best_students_subjectwise` | `BestStudentsReport` | a candidate ranked within one subject |
| `schools_rank` | `SchoolsRankReport` | a school, with division counts + GPA |
| `top_schools` | `SchoolsRankReport` | a school (top-ten cut of the same shape) |
| `subjects_rank` | `SubjectsRankReport` | a subject, with grade counts + GPA |
| `subject_school_rank` | `GenericTabularReport` | a school within one subject |
| `wards_rank` | `GenericTabularReport` | a ward |
| `district_performance` | `GenericTabularReport` | a council/district |
| `mock_mobility` | `GenericTabularReport` | a school's FTNA→Mock GPA movement |
| `generic` | `GenericTabularReport` | anything header-driven |

Every class is a plain `@dataclass`, so `schema.to_dict` / `schema.from_dict`
round-trip it, and `schema.to_json` / `from_json` do the same through JSON.

### `ReportMeta` — required on every report

```python
schema.ReportMeta(
    name="MWANZA CC SCHOOLS RANK",   # selects a layout when it names a bundled one
    report_type="schools_rank",      # required: picks schema + renderer
    level="council",                 # school | council | region
    variant="overall",               # overall | government | subjectwise | edk | ...
    region="Mwanza",
    council="Mwanza CC",
    exam_name="REGIONAL FORM TWO MOCK ASSESSMENT RESULTS, JULY 2026",
    title="MWANZA CC SCHOOLS RANK",  # the report's own heading
)
```

`region`, `council`, `exam_name` and `title` are **data** — they are printed.
`name`, `report_type`, `level`, `variant` are **routing** — they choose the
layout and the renderer.

### What is data, and what is never data

Data carries **values and structure only**. Fonts, sizes, weights, colours,
alignment and row pitch belong to the recovered layout, never to your data.

The one apparent exception proves the rule: a competency cell's **background
colour is derived**, not supplied. You give the label (`"Grade C (Good)"`) or a
GPA; `sars.competency` maps it to a colour. Supplying a colour is not possible —
and this is the *only* thing that varies from one row to the next. Everything
else about a row's structure is identical for every row.

| competency label | colour |
|---|---|
| `Grade A (Excellent)` | `#00b050` |
| `Grade B (Very Good)` | `#92d050` |
| `Grade C (Good)` | `#ffff00` |
| `Grade D (Satisfactory)` | `#ffc000` |
| `Grade F (Fail)` / `Weak` / `Failed` | `#ff0000` |

Labels are matched case- and punctuation-insensitively, so `EXCELLENT`, `A` and
`Grade A (Excellent)` all resolve to the same band. A GPA is used when the label
is missing or unrecognised.

---

## 2. The row shapes

### Students — `StudentRow`

Used by `best_students` (via `BestStudentsSection`) and `school_result_slip`.
Every field is a string, printed verbatim; omit what a report does not show.

```python
schema.StudentRow(
    cno="S5344-0004",                 # candidate number
    name="ADETHA AMWESIGA TALEMWA",
    sex="F",
    aggregate="7",                    # AGGT
    division="I",
    position="1",
    school_name="MUSABE GIRLS",
    detailed_subjects="HTM - 97'A' BUSI - 80'A' GEO - 91'A'",
    # subjectwise lists use these instead of aggregate/division:
    sno="1", council="Mwanza CC", id_no="S5344-0004",
    category="GOVERNMENT", marks="97", grade="A",
    competency="Grade A (Excellent)",
)
```

`detailed_subjects` is the raw string as printed. `subjects` is an optional
parsed view (`list[SubjectResult]` of `subject` / `mark` / `grade`); the raw
string is what gets printed.

`best_students` groups students into **sections**, which is how one page carries
both "TOP TEN BEST STUDENTS" and "TOP TEN BEST FEMALE STUDENTS":

```python
schema.BestStudentsReport(
    meta=meta,
    sections=[
        schema.BestStudentsSection(title="MWANZA CC TOP TEN BEST STUDENTS OVERALL COUNCILWISE",
                                   students=[...]),
        schema.BestStudentsSection(title="TOP TEN BEST FEMALE STUDENTS OVERALL COUNCILWISE",
                                   students=[...]),
    ],
)
```

> One section per table on the page. A section with an empty `students` list
> prints its caption and an empty body — it does not collapse the page.

### Schools — `SchoolRankRow`

Used by `schools_rank` and `top_schools`. Note the two structured fields:
`registered` / `sat` are `GenderCounts` (`f` / `m` / `t`), and `division` is a
dict keyed by division label.

```python
schema.SchoolRankRow(
    sno="1", ward="NYAMAGANA", council="Mwanza CC",
    school_name="MUSABE GIRLS", ownership="PRIVATE",
    registered=schema.GenderCounts(f="50", m="0", t="50"),
    sat=schema.GenderCounts(f="49", m="0", t="49"),
    sat_pct="98.0",
    division={                        # label -> F/M/T triple
        "I":  {"f": "20", "m": "0", "t": "20"},
        "II": {"f": "15", "m": "0", "t": "15"},
        "I-III": {"f": "45", "m": "0", "t": "45"},
        "I-III%": "91.8",             # percentage columns use a '%' suffix key
    },
    gpa="2.29", competency="Grade C (Good)",
    council_rank="1", regional_rank="3",
)
```

`SchoolsRankReport` then holds `rows`, plus optional `totals`
(`{row label: [values]}`), `summary` (the aggregate block printed above the
table, as `PerformanceTable`) and `column_headers`.

### Subjects — `SubjectRankRow`

```python
schema.SubjectRankRow(
    sno="1", subject_name="BASIC MATHEMATICS",
    grades={"A": "12", "B": "40", "C": "88", "D": "60", "F": "15",
            "TOTAL": "215", "A-C": "140", "%A-C": "65.1"},
    gpa="2.85", competency="Grade C (Good)", rank="1",
)
```

### Anything else — `GenericTabularReport`

Header-driven: each row is `{column header: value}`. This covers `wards_rank`,
`district_performance`, `mock_mobility` and `subject_school_rank`, and is the
escape hatch for a table with no bespoke schema.

```python
schema.GenericTabularReport(
    meta=meta,
    column_headers=["S/NO.", "WARD", "REGISTERED", "SAT", "GPA"],
    rows=[schema.TabularRow(values={"S/NO.": "1", "WARD": "NYAMAGANA",
                                    "REGISTERED": "520", "SAT": "498",
                                    "GPA": "2.41"})],
    totals={"TOTAL": ["", "", "520", "498", ""]},
)
```

Use `sections` (`list[TabularSection]`) when one report prints several tables
with *different* column counts; the top-level `rows` / `totals` mirror the first
section, so single-table reports never need to touch `sections`.

> **The keys are not yours to choose.** A layout's bindings were recovered from
> the reference document, so a value is found by the reference's *own* field
> path — and for header-driven reports that path **is** the column's header
> label, with ` / ` between header levels. Invented keys bind to nothing and the
> row prints empty.

Ask the layout what it reads, rather than guessing:

```python
>>> from sars import layout_spec
>>> contract = layout_spec.data_contract("MWANZA CC Wards Rank")
>>> contract[0]["fields"][1]
'NO. OF / WARDS IN / COUNCIL'
>>> contract[0]["fields"][8]
'DIVISION PERFORMANCE / I-III / TOTAL'
```

So the wards example above must use those labels verbatim:

```python
schema.TabularRow(values={
    "NO. OF / WARDS IN / COUNCIL": "NYAMAGANA",
    "NUMBER OF CANDIDATES / REG": "520",
    "NUMBER OF CANDIDATES / SAT / TOTAL": "498",
    "DIVISION PERFORMANCE / I-III / TOTAL": "301",
})
```

`sars.binding.row_groups(data)` shows the paths your data actually offers, which
is how you diagnose a mismatch: compare it against `data_contract(layout)`.

The bespoke schemas (`SchoolRankRow`, `StudentRow`, `SubjectRankRow`) do not have
this problem — their bindings name real field names like `school_name` and `gpa`,
so you just fill in the dataclass.

### Which of your rows fills which table: row groups

A layout's band binds to a named **row group**, and the group names come from the
*position* of your data, so order matters. `data_contract(layout)` reports the
group each band wants, and `sars.binding.row_groups(data)` reports the groups your
data supplies:

| your data | groups it offers |
|---|---|
| `GenericTabularReport.sections` | `section0`, `section0_totals`, `section1`, … |
| `BestStudentsReport.sections` | `students0`, `students1`, … |
| `SchoolsRankReport` | `rows`, `totals`, `summary0`, … |
| `SchoolResultSlip` | `students`, `division_summary`, `performance0`, … |

So a generic report whose layout binds a band to `section1` needs a **second
section** — the second table is filled by `sections[1]`, not by top-level `rows`.
Supply an empty `TabularSection` to hold a position you do not use.

---

## 3. Layout: which geometry your data is printed in

A layout is recovered *from a reference document*, so it is keyed by that
document's name. `sars.layout_spec.resolve()` turns what you know into a layout:

```python
layout_spec.resolve("MWANZA CC SCHOOLS RANK")                  # exact document
layout_spec.resolve(None, report_type="best_students")         # by kind
layout_spec.resolve(None, report_type="best_students",
                    level="region", variant="subjectwise")     # narrowed
```

1. a `meta.name` that names a bundled layout wins — you are reproducing that
   document;
2. otherwise the best match for `report_type` → `level` → `variant` is used, so
   **your own data prints in the shape of a report of that kind**;
3. if nothing matches, `LayoutSpecMissing` is raised listing what exists. A
   layout is never silently substituted.

`layout_spec.catalogue()` lists all 19 bundled layouts with their descriptors.

---

## 4. Mode: `grow`

This is the one flag that changes structure, and the default is deliberate.

| | `grow=False` (default) | `grow=True` |
|---|---|---|
| pages | exactly the reference's | as many as the data needs |
| rows per band | exactly the reference's | all supplied rows |
| surplus data | not rendered | continues onto further pages |
| use it to | **reproduce a reference document** | **render your own data** |

`grow=False` exists because a recovered layout is not a promise that your data
has as many rows as the document printed. `MWANZA CC SCHOOLS RANK SUBJECTWISE`
is the proof: its extracted `section0` holds 65 rows while the reference page
prints 54. A renderer that grew whenever there were more rows would turn a
faithful 24-page reproduction into 30 pages. So growth is something you ask for.

Less data needs no flag: a short table prints its reference's empty ruled rows
and keeps its page count, in either mode.

---

## 5. What happens at the extremes

You do not have to pre-trim anything. Values are absorbed where they are drawn,
and the page geometry never moves.

| you supply | what happens |
|---|---|
| a value wider than its column | condensed horizontally (`scaleX`) about the run's start |
| a value too wide even condensed | condensed to the `MIN_CONDENSE` floor (0.55), then cut |
| a very long detailed-results string | condensed; a 213-character string keeps **every** character |
| more rows than the page holds | `grow=True`: continues onto further pages. `grow=False`: not rendered |
| fewer rows | reference's empty ruled rows remain; page count unchanged |
| an empty section | caption prints, body is empty |
| no rows at all | the reference shell still prints |

Two consequences worth knowing:

* **A cut value is never marked.** No `…` is appended, because the reference
  faces are subsets — an ellipsis would be drawn from a *different* family, and
  this project never allows a fallback font. A cut value is a clean prefix.
* **A value may use the room the reference's value used, not merely its cell.**
  Some reference cells legitimately overhang their own box (`Mwanza f2 Mock
  Mobility 2026` draws `GPA2.2969` in a box far narrower than the string), so
  clamping to the box would be *less* faithful than the reference.

---

## 6. A complete, minimal example

```python
from sars import schema, template_maker

report = schema.SchoolsRankReport(
    meta=schema.ReportMeta(
        name="MY COUNCIL SCHOOLS RANK 2027",   # not a bundled name -> resolved by kind
        report_type="schools_rank",
        level="council",
        variant="overall",
        region="Mwanza",
        council="My CC",
        exam_name="REGIONAL FORM TWO MOCK ASSESSMENT RESULTS, JULY 2027",
        title="MY COUNCIL SCHOOLS RANK",
    ),
    rows=[
        schema.SchoolRankRow(
            sno=str(i + 1),
            ward="NYAMAGANA",
            school_name=f"SCHOOL NUMBER {i + 1}",
            ownership="GOVERNMENT",
            registered=schema.GenderCounts(f="30", m="28", t="58"),
            sat=schema.GenderCounts(f="29", m="27", t="56"),
            sat_pct="96.6",
            division={"I": {"f": "5", "m": "4", "t": "9"}},
            gpa="2.90",
            competency="Grade C (Good)",      # colour derived from this label
            council_rank=str(i + 1),
        )
        for i in range(120)                    # more rows than the reference had
    ],
)

html = template_maker.render_html("schools_rank", report, grow=True)
template_maker.render_pdf("schools_rank", report, "my-council.pdf", grow=True)
```

---

## 7. Known limitations

* **A layout must already exist for the kind of report you want.** The 19
  bundled layouts are listed by `layout_spec.catalogue()`. A genuinely new report
  shape needs its geometry recovered from a reference PDF first
  (`tools/build_layout_specs.py`); it cannot be invented from data.
* **Fonts must be installed**, or the renderer will not produce the reference's
  glyphs. There is no fallback font by design — a missing face is an error, not a
  substitution.
* **Header-driven reports need the reference's own header labels** as keys, as
  described in §2. Use `layout_spec.data_contract(layout)` rather than guessing.
