# Data structure: what to feed each template

This is the authoritative specification of the **data** every template consumes.
Supply data in this shape and the templated path reproduces the corresponding
report's structure faithfully - the same page geometry, the same columns, the
same rows - for *your own* students, schools, subjects and councils, not just
the 19 bundled examples.

It is grounded in [`src/sars/schema.py`](../src/sars/schema.py); every field
below is a real dataclass field there. Worked instances live under
[`output/data/*.json`](../output/data) (regenerate with `python -m sars.cli
data`), and each is a lossless round-trip of the matching schema
(`schema.to_json` / `schema.from_json`).

## The one rule: data is data, not styles

The schema carries only the report's **data** (names, figures, ranks, counts,
GPA, competency *labels*) and its **structure** (which rows are totals, section
titles, column-header labels). It carries **no presentation**: no font, size,
weight, colour, background fill, alignment or row pitch. Those belong to each
report type's own self-contained template, recovered from its reference PDF.

In particular the **competency background colour is never supplied and never
stored**. It is a deterministic function of the competency *label* (or GPA),
computed at render time by [`sars.competency`](../src/sars/competency.py). You
supply the label text (`"Grade C (Good)"`); the colour is derived. See
[the looping contract](#the-looping-contract) below.

## How to call it

```python
from sars import schema, template_maker

data = schema.from_json(open("my_report.json").read())   # or build the dataclass directly
html = template_maker.render_html(data.meta.report_type, data)     # -> HTML string
pdf  = template_maker.render_pdf(data.meta.report_type, data, "out.pdf")  # -> writes PDF
# or let it infer the type from the schema instance:
html = template_maker.make(data)
```

`report_type` selects the template; `data` must be the schema instance that
template expects (table below). The report_type also lives inside the data at
`meta.report_type`, so `make(data)` and `from_json(...)` need nothing else.

## report_type -> schema class -> template

`report_type` comes from [`sars.reports.CATALOGUE`](../src/sars/reports.py); the
schema class is [`schema.SCHEMA_BY_TYPE`](../src/sars/schema.py); the template is
[`templates.RENDERERS`](../src/sars/templates/__init__.py) /
`templates.TEMPLATE_NAMES`.

| `report_type`         | schema class            | template          | example report                          |
| --------------------- | ----------------------- | ----------------- | --------------------------------------- |
| `school_result_slip`  | `SchoolResultSlip`      | `school_result_slip` | S1051-MKOLANI SECONDARY SCHOOL       |
| `best_students`       | `BestStudentsReport`    | `best_students`   | MWANZA CC 10 BEST STUDENTS              |
| `best_students` (subjectwise) | `BestStudentsReport` | `best_students_subjectwise` | MWANZA CC 10 BEST STUDENTS SUBJECTWISE |
| `schools_rank`        | `SchoolsRankReport`     | `schools_rank`    | MWANZA CC SCHOOLS RANK                  |
| `top_schools`         | `SchoolsRankReport`     | `top_schools`     | MWANZA CC 10 BEST SCHOOLS               |
| `subjects_rank`       | `SubjectsRankReport`    | `subjects_rank`   | MWANZA CC SUBJECTS RANK                 |
| `subject_school_rank` | `GenericTabularReport`  | `subject_school_rank` | MWANZA CC SCHOOLS RANK SUBJECTWISE  |
| `wards_rank`          | `GenericTabularReport`  | `wards_rank`      | MWANZA CC Wards Rank                    |
| `district_performance`| `GenericTabularReport`  | `district_performance` | Mwanza f2 District Performance     |
| `mock_mobility`       | `GenericTabularReport`  | `mock_mobility`   | Mwanza f2 Mock Mobility 2026            |
| `generic`             | `GenericTabularReport`  | (header-driven)   | any unmapped tabular report             |

`best_students` renders `best_students` or `best_students_subjectwise` depending
on the report's `variant` (`overall` vs `subjectwise`); both consume a
`BestStudentsReport`.

## Shared value objects

### `ReportMeta` (every report carries one)

| field         | data / chrome | meaning                                                    |
| ------------- | ------------- | ---------------------------------------------------------- |
| `name`        | data          | source document name; also the layout-spec key             |
| `report_type` | structure     | family id (table above); selects the template              |
| `level`       | structure     | `school` \| `council` \| `region`                          |
| `variant`     | structure     | flavour within the family (`overall` / `government` / `subjectwise` / ...) |
| `region`      | data          | region name, e.g. `Mwanza`                                 |
| `council`     | data          | council name, e.g. `Mwanza CC` (blank at region level)     |
| `exam_name`   | data          | the assessment line, e.g. the July 2026 mock results text  |
| `title`       | data          | the report's own heading                                   |

### `GenderCounts`

An `F` / `M` / `T` triple: `{"f": "12", "m": "9", "t": "21"}`. All strings, as
printed.

## Report schemas, field by field

### `BestStudentsReport` (`best_students`)

```
BestStudentsReport
  meta:     ReportMeta
  sections: [ BestStudentsSection ]
BestStudentsSection
  title:    str                 # section heading, e.g. "TOP TEN BEST FEMALE STUDENTS OVERALL COUNCILWISE"
  students: [ StudentRow ]       # the section's ranked candidates, in order
```

A best-students report is a **list of titled sections**, each a table of
`StudentRow`. Supply as many sections as your report prints (the bundled example
has 9: overall / female / male x all-schools / government / private). Each
section is rendered as its own table under its own caption; there is no shared
structure between sections beyond the column set.

### `StudentRow` (used by `school_result_slip` and `best_students`)

| field               | meaning                                                             |
| ------------------- | ------------------------------------------------------------------- |
| `cno`               | candidate number, e.g. `S1051-0001`                                 |
| `name`              | full name as printed                                                |
| `sex`               | `F` / `M`                                                           |
| `aggregate`         | aggregate points (`AGGT`), may be `ABS`                             |
| `division`          | division `I`..`IV` / `0` / `ABS`                                     |
| `position`          | overall position / ranking                                          |
| `school_name`       | owning school (present on best-students lists, blank on a slip)     |
| `subjects`          | `[ SubjectResult ]` parsed per-subject results                      |
| `detailed_subjects` | the raw `DETAILED SUBJECTS` text, kept verbatim                     |
| `sno`               | serial number within a subjectwise section (`S/NO.`)                |
| `council`           | owning council (region-level subjectwise lists name it per row)     |
| `id_no`             | candidate id on subjectwise lists (`ID NO.`)                        |
| `category`          | school ownership (`GOVERNMENT` / `PRIVATE`)                         |
| `marks`             | the subject mark (subjectwise lists)                                |
| `grade`             | the subject grade letter (subjectwise lists)                        |
| `competency`        | competency label; **colour is derived, never supplied**             |

`SubjectResult`: `{"subject": "KISW", "mark": "42", "grade": "D"}`.

### `SchoolResultSlip` (`school_result_slip`)

```
SchoolResultSlip
  meta:             ReportMeta
  centre_no:        str
  school_name:      str
  division_summary: [ DivisionSummaryRow ]   # F/M/T division counts
  students:         [ StudentRow ]           # every candidate on the slip
  performance:      [ PerformanceTable ]     # school + per-subject summary blocks
```

`DivisionSummaryRow`: `{"sex": "F", "divisions": {"I": "3", "II": "5", ...}}`.
`PerformanceTable`: `{"column_headers": [...], "rows": [ PerformanceRow ]}` where
`PerformanceRow` is `{"values": {"<header>": "<value>"}}`.

### `SchoolsRankReport` (`schools_rank`, `top_schools`)

```
SchoolsRankReport
  meta:           ReportMeta
  rows:           [ SchoolRankRow ]
  totals:         { "<row label>": ["cell", "cell", ...] }   # DATA of TOTAL rows; label is the key (chrome)
  summary:        [ PerformanceTable ]                        # optional summary-performance block above the table
  column_headers: [ str ]                                     # the report's own captions, in order (chrome)
```

`SchoolRankRow` fields: `sno`, `ward`, `council`, `school_name`, `ownership`,
`registered` (`GenderCounts`), `sat` (`GenderCounts`), `sat_pct`, `division`
(a dict keyed by division label -> F/M/T triple, with `<label>%` keys for the
percentage columns), `gpa`, `competency` (colour derived), `council_rank`,
`regional_rank`.

### `SubjectsRankReport` (`subjects_rank`)

```
SubjectsRankReport
  meta:           ReportMeta
  rows:           [ SubjectRankRow ]
  totals:         { "<row label>": [ ... ] }
  column_headers: [ str ]
SubjectRankRow
  sno, subject_name, gpa, competency, rank
  grades: { "A": "..", "B": "..", ..., "TOTAL": "..", "A-C": "..", "%A-C": ".." }
```

### `GenericTabularReport` (`subject_school_rank`, `wards_rank`, `district_performance`, `mock_mobility`, `generic`)

```
GenericTabularReport
  meta:           ReportMeta
  column_headers: [ str ]              # first (main) section's headers, mirrored for convenience
  rows:           [ TabularRow ]       # first (main) section's rows, mirrored
  totals:         { "<label>": [...] } # first (main) section's totals, mirrored
  sections:       [ TabularSection ]   # EVERY table block, in reading order
TabularRow      : { "values": { "<header>": "<value>" } }
TabularSection  : { "column_headers": [...], "rows": [ TabularRow ], "totals": {...}, "title": "..." }
```

Any report without a bespoke schema is captured header-driven and losslessly:
each value is keyed by its column header label. A report that prints several
different table blocks (different column counts) puts each block in its own
`TabularSection`; the top-level `column_headers` / `rows` / `totals` mirror the
first block, so single-block reports need not index into `sections`.

## Multiple tables / sections on one page

Several report families draw **more than one logical table on a page** - the
best-students lists stack an overall table and a female table (and a male table)
on the same page, separated only by a caption. The data model already expresses
this: one `BestStudentsSection` (or one `TabularSection`) per logical table.

The template mechanism binds **one data band per logical section, in document
order**: the first section fills the first table, the second section fills the
second table, and so on, however many there are. Supply more sections and more
tables render; supply fewer and fewer render. You never special-case a report -
the looping is generic. (This is the FEAT-002 fix: previously a page's second
table was drawn empty because the two logical tables were welded into one and
bound to a single section.)

## The looping contract

For **students, subjects and schools, rendering is just looping over rows.**
Every row of a section repeats the *same* structure - the same columns, the same
fonts, the same alignment, the same baseline. **The only thing that changes
between rows is the competency background colour**, and even that is not part of
the row's data: it is derived at render time from the row's competency label /
GPA via [`sars.competency`](../src/sars/competency.py). Concretely:

* You supply N rows; the template repeats its recovered row band N times.
* Each row's values are placed by column, measured with the reference font's own
  advances, on the reference's baseline.
* The competency cell's wash is computed from `competency` (or `gpa`); supply a
  different label and the colour follows the documented mapping. Supply no
  competency and no wash is drawn.
* Nothing else varies row to row. There is no per-row styling to supply.

This is why the same template reproduces the report for *any* data: the
structure is fixed and recovered from the reference; only the row values (and the
derived competency colour) change.

## A copy-pasteable example per family

### Best students (`best_students`) - two sections on a page

```json
{
  "meta": {
    "name": "MY COUNCIL 10 BEST STUDENTS",
    "report_type": "best_students",
    "level": "council",
    "variant": "overall",
    "region": "Mwanza",
    "council": "My CC",
    "exam_name": "REGIONAL FORM TWO MOCK ASSESSMENT RESULTS, JULY 2026",
    "title": "MY CC TOP TEN BEST STUDENTS OVERALL COUNCILWISE"
  },
  "sections": [
    {
      "title": "MY CC TOP TEN BEST STUDENTS OVERALL COUNCILWISE",
      "students": [
        {
          "cno": "S9999-0001", "name": "AMINA JUMA HASSANI", "sex": "F",
          "aggregate": "7", "division": "I", "position": "1",
          "school_name": "EXAMPLE SEC",
          "subjects": [
            {"subject": "HTM", "mark": "97", "grade": "A"},
            {"subject": "GEO", "mark": "91", "grade": "A"}
          ],
          "detailed_subjects": "HTM - 97'A' GEO - 91'A'"
        }
      ]
    },
    {
      "title": "TOP TEN BEST FEMALE STUDENTS OVERALL COUNCILWISE",
      "students": [
        {
          "cno": "S9999-0002", "name": "NEEMA PETRO MOSHA", "sex": "F",
          "aggregate": "8", "division": "I", "position": "1",
          "school_name": "EXAMPLE GIRLS",
          "subjects": [{"subject": "KISW", "mark": "88", "grade": "A"}],
          "detailed_subjects": "KISW - 88'A'"
        }
      ]
    }
  ]
}
```

### Schools rank (`schools_rank`) / top schools (`top_schools`)

```json
{
  "meta": {
    "name": "MY COUNCIL SCHOOLS RANK", "report_type": "schools_rank",
    "level": "council", "variant": "overall", "region": "Mwanza",
    "council": "My CC", "exam_name": "...", "title": "MY CC SCHOOLS RANK"
  },
  "rows": [
    {
      "sno": "1", "ward": "MJINI", "council": "My CC",
      "school_name": "EXAMPLE SEC", "ownership": "GOVERNMENT",
      "registered": {"f": "40", "m": "35", "t": "75"},
      "sat": {"f": "40", "m": "34", "t": "74"}, "sat_pct": "98.67",
      "division": {"I": {"f": "5", "m": "4", "t": "9"}, "I-III%": "82.43"},
      "gpa": "2.98", "competency": "Grade C (Good)",
      "council_rank": "1", "regional_rank": "12"
    }
  ],
  "totals": {"TOTAL": ["", "", "", "2.98", "48.99", "97.02", "387"]},
  "summary": [],
  "column_headers": []
}
```

### Subjects rank (`subjects_rank`)

```json
{
  "meta": {
    "name": "MY COUNCIL SUBJECTS RANK", "report_type": "subjects_rank",
    "level": "council", "variant": "overall", "region": "Mwanza",
    "council": "My CC", "exam_name": "...", "title": "MY CC SUBJECTS RANK"
  },
  "rows": [
    {
      "sno": "1", "subject_name": "KISWAHILI",
      "grades": {"A": "12", "B": "40", "C": "80", "TOTAL": "200", "A-C": "132", "%A-C": "66.00"},
      "gpa": "3.10", "competency": "Grade C (Good)", "rank": "1"
    }
  ],
  "totals": {},
  "column_headers": []
}
```

### School result slip (`school_result_slip`)

```json
{
  "meta": {
    "name": "S9999-EXAMPLE SECONDARY SCHOOL", "report_type": "school_result_slip",
    "level": "school", "variant": "single_school", "region": "Mwanza",
    "council": "My CC", "exam_name": "...", "title": "..."
  },
  "centre_no": "S9999",
  "school_name": "EXAMPLE SECONDARY SCHOOL",
  "division_summary": [
    {"sex": "F", "divisions": {"I": "5", "II": "8", "III": "10", "IV": "6", "0": "1"}}
  ],
  "students": [
    {
      "cno": "S9999-0001", "name": "AMINA JUMA HASSANI", "sex": "F",
      "aggregate": "18", "division": "II", "position": "3",
      "subjects": [{"subject": "KISW", "mark": "72", "grade": "B"}],
      "detailed_subjects": "KISW - 72'B'"
    }
  ],
  "performance": []
}
```

### Generic tabular (`district_performance`, `wards_rank`, `mock_mobility`, `subject_school_rank`, `generic`)

```json
{
  "meta": {
    "name": "MY DISTRICT PERFORMANCE", "report_type": "district_performance",
    "level": "region", "variant": "overall", "region": "Mwanza",
    "council": "", "exam_name": "...", "title": "DISTRICT PERFORMANCE"
  },
  "column_headers": ["S/NO", "DISTRICT", "GPA", "RANK"],
  "rows": [
    {"values": {"S/NO": "1", "DISTRICT": "ILEMELA", "GPA": "3.01", "RANK": "1"}}
  ],
  "totals": {},
  "sections": [
    {
      "column_headers": ["S/NO", "DISTRICT", "GPA", "RANK"],
      "rows": [
        {"values": {"S/NO": "1", "DISTRICT": "ILEMELA", "GPA": "3.01", "RANK": "1"}}
      ],
      "totals": {},
      "title": "DISTRICT PERFORMANCE"
    }
  ]
}
```

## Round-trip guarantee

Every schema instance serialises losslessly:

```python
text = schema.to_json(data)
assert schema.to_json(schema.from_json(text)) == text
```

`from_dict` / `from_json` pick the schema class from
`data["meta"]["report_type"]` via `schema.SCHEMA_BY_TYPE`, so a JSON file written
by `python -m sars.cli data` reconstructs the exact instance the template
expects.
