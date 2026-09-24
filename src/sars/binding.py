"""Bind a report's data fields to the columns the reference put them in.

A recovered layout spec knows *where* a value goes: the column box, the baseline,
the font, the alignment. What it cannot know from geometry alone is *which* data
field belongs in which column — and every report family has a different data
shape (``SchoolsRankReport`` rows with nested gender counts and a division map,
``BestStudentsReport`` sections of students, ``SubjectsRankReport`` rows with a
grade map, the header-keyed generic sections).

Rather than hand-maintain a column map per family, the binding is *recovered*:
``tools/build_layout_specs.py`` flattens each data row to ``path -> value`` with
:func:`flatten`, compares those values against the text the reference actually
printed in each column, and stores the winning path in the spec. This module
provides both halves of that: the flattener, and the row groups a report's data
presents in document order.

Nothing here is presentational; it is purely "which field, which column".
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any


def flatten(obj: Any, prefix: str = "") -> dict[str, str]:
    """Flatten a schema row to ``dotted.path -> string value``.

    ``SchoolRankRow`` becomes ``sno``, ``school_name``, ``registered.f``,
    ``division.I.t``, ``division.I-III%``, … — one addressable path per value a
    column could carry.
    """
    out: dict[str, str] = {}

    def add(path: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str | int | float):
            out[path] = str(value)
            return
        if is_dataclass(value):
            for spec in fields(value):
                add(f"{path}.{spec.name}" if path else spec.name, getattr(value, spec.name))
            return
        if isinstance(value, dict):
            for key, item in value.items():
                add(f"{path}.{key}" if path else str(key), item)
            return
        if isinstance(value, list | tuple):
            for index, item in enumerate(value):
                add(f"{path}[{index}]" if path else f"[{index}]", item)
            return

    add(prefix, obj)
    return out


def _performance_rows(table: Any) -> list[dict[str, str]]:
    headers = list(getattr(table, "column_headers", []) or [])
    rows: list[dict[str, str]] = []
    for row in getattr(table, "rows", []) or []:
        values = dict(getattr(row, "values", {}) or {})
        flat = {str(key): str(value) for key, value in values.items()}
        for index, header in enumerate(headers):
            if str(index) in flat:
                flat[f"header:{header}"] = flat[str(index)]
        rows.append(flat)
    return rows


def row_groups(data: Any) -> list[dict[str, Any]]:
    """The row groups a report's data presents, in the order the report prints.

    Each group is ``{"name": str, "rows": [flattened row, …]}``. Groups are what a
    spec band binds to: the ranked rows, a section's students, a totals row, a
    summary performance block.
    """
    groups: list[dict[str, Any]] = []

    def push(name: str, rows: list[dict[str, str]]) -> None:
        if rows:
            groups.append({"name": name, "rows": rows})

    # Header-keyed generic sections
    sections = getattr(data, "sections", None)
    if sections and all(hasattr(section, "column_headers") for section in sections):
        for index, section in enumerate(sections):
            headers = list(section.column_headers)
            rows = []
            for row in section.rows:
                values = dict(row.values)
                flat = {str(key): str(value) for key, value in values.items()}
                for position, header in enumerate(headers):
                    if header in values:
                        flat[f"col:{position}"] = str(values[header])
                rows.append(flat)
            push(f"section{index}", rows)
            totals = list(section.totals.values())
            total_rows = []
            for row in totals:
                if isinstance(row, dict):
                    total_rows.append({str(k): str(v) for k, v in row.items()})
                else:
                    total_rows.append({f"col:{i}": str(v) for i, v in enumerate(row)})
            push(f"section{index}_totals", total_rows)
        return groups

    # Best-students sections (students per section)
    if sections and all(hasattr(section, "students") for section in sections):
        for index, section in enumerate(sections):
            push(f"students{index}", [flatten(student) for student in section.students])
        return groups

    # Schools-rank / top-schools
    rows = getattr(data, "rows", None)
    if rows:
        push("rows", [flatten(row) for row in rows])
    totals = getattr(data, "totals", None)
    if isinstance(totals, dict) and totals:
        total_rows = []
        for row in totals.values():
            if isinstance(row, dict):
                total_rows.append({str(k): str(v) for k, v in row.items()})
            elif isinstance(row, list | tuple):
                total_rows.append({f"col:{i}": str(v) for i, v in enumerate(row)})
        push("totals", total_rows)

    # Summary / performance blocks (schools rank, school result slip)
    for attribute in ("summary", "performance"):
        tables = getattr(data, attribute, None) or []
        for index, table in enumerate(tables):
            push(f"{attribute}{index}", _performance_rows(table))

    # School result slip specifics
    students = getattr(data, "students", None)
    if students:
        push("students", [flatten(student) for student in students])
    division_summary = getattr(data, "division_summary", None)
    if division_summary:
        push("division_summary", [flatten(row) for row in division_summary])

    return groups
