"""Catalogue of the Mwanza Form Two mock report *types*.

These reports aggregate results up a fixed hierarchy - *school -> ward ->
council -> region* - and each supplied document is an instance of one of a
small number of recurring report *types*. This module names those types and
maps every one of the 19 supplied documents onto a :class:`ReportSpec` that
records:

* ``report_type`` - a stable id for the family of report (used to pick the
  schema and, in FEAT-004, the template);
* ``level``       - the hierarchy level the report summarises
  (``school`` | ``council`` | ``region``);
* ``variant``     - the flavour within the family (``overall`` /
  ``government`` / ``subjectwise`` / ``best_students`` / ...).

Only the *classification* lives here; the data extracted from a document lives
in :mod:`sars.schema`, and the routing from a report type to its schema lives in
:mod:`sars.extract_data`.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The region every supplied document belongs to. Stored as data on each
#: schema, but recorded here too as the catalogue's shared default.
DEFAULT_REGION = "Mwanza"
#: The council the ``council``-level documents belong to.
DEFAULT_COUNCIL = "Mwanza CC"


@dataclass(frozen=True)
class ReportSpec:
    """Classification of one supplied document.

    ``report_type`` groups documents that share a data shape (and therefore a
    schema); ``level`` and ``variant`` distinguish instances within a type.
    """

    #: Exact source document name (``SourcePair.name``) this spec describes.
    name: str
    #: Stable family id, e.g. ``schools_rank`` or ``best_students``.
    report_type: str
    #: Hierarchy level: ``school`` | ``council`` | ``region``.
    level: str
    #: Flavour within the family, e.g. ``overall`` | ``government`` | ``edk``.
    variant: str


#: Every supplied document, classified. Keyed by report type family:
#:
#: * ``school_result_slip`` - one school's candidate result slip;
#: * ``schools_rank``       - schools ranked with candidate/division/GPA figures;
#: * ``top_schools``        - the top ten schools (same columns as schools_rank);
#: * ``best_students``      - top-ten best candidates (overall / subjectwise);
#: * ``subjects_rank``      - subjects ranked by grade performance and GPA;
#: * ``subject_school_rank``- schools ranked *within a single subject*;
#: * ``wards_rank``         - a council's wards summary pivot;
#: * ``district_performance``- councils/districts ranked within the region;
#: * ``mock_mobility``      - FTNA-vs-Mock GPA movement per school.
_SPECS: tuple[ReportSpec, ...] = (
    # -- school level -------------------------------------------------------
    ReportSpec("S1051-MKOLANI SECONDARY SCHOOL", "school_result_slip", "school", "single_school"),
    # -- council level ------------------------------------------------------
    ReportSpec("MWANZA CC 10 BEST SCHOOLS", "top_schools", "council", "overall"),
    ReportSpec("MWANZA CC 10 BEST STUDENTS", "best_students", "council", "overall"),
    ReportSpec(
        "MWANZA CC 10 BEST STUDENTS SUBJECTWISE",
        "best_students",
        "council",
        "subjectwise",
    ),
    ReportSpec("MWANZA CC SCHOOLS RANK", "schools_rank", "council", "overall"),
    ReportSpec(
        "MWANZA CC SCHOOLS RANK SUBJECTWISE",
        "subject_school_rank",
        "council",
        "subjectwise",
    ),
    ReportSpec("MWANZA CC SUBJECTS RANK", "subjects_rank", "council", "overall"),
    ReportSpec("MWANZA CC Wards Rank", "wards_rank", "council", "overall"),
    # -- region level -------------------------------------------------------
    ReportSpec("Mwanza Best Students-Overall", "best_students", "region", "overall"),
    ReportSpec("Mwanza Best students-Subjectwise", "best_students", "region", "subjectwise"),
    ReportSpec("Mwanza Overall Subjects Performance", "subjects_rank", "region", "overall"),
    ReportSpec("Mwanza School Rank-EDK", "subject_school_rank", "region", "edk"),
    ReportSpec(
        "Mwanza School Rank-English Language",
        "subject_school_rank",
        "region",
        "english",
    ),
    ReportSpec(
        "Mwanza Schools Rank For Governments (1)",
        "schools_rank",
        "region",
        "government",
    ),
    ReportSpec("Mwanza Schools Rank For Governments", "schools_rank", "region", "government"),
    ReportSpec("Mwanza Top 10 Schools", "top_schools", "region", "overall"),
    ReportSpec("Mwanza f2 District Performance", "district_performance", "region", "overall"),
    ReportSpec("Mwanza f2 Mock Mobility 2026", "mock_mobility", "region", "overall"),
    ReportSpec("Mwanza schools rank Overall", "schools_rank", "region", "overall"),
)

#: The catalogue as a name -> :class:`ReportSpec` mapping.
CATALOGUE: dict[str, ReportSpec] = {spec.name: spec for spec in _SPECS}


def spec_for(name: str) -> ReportSpec:
    """Return the :class:`ReportSpec` for a document name.

    Falls back to a best-effort spec (``report_type='generic'``) for any name
    not explicitly catalogued, using the ``Mwanza CC`` prefix to guess the
    level, so the pipeline never crashes on an unknown document.
    """
    spec = CATALOGUE.get(name)
    if spec is not None:
        return spec
    upper = name.upper()
    if upper.startswith("MWANZA CC"):
        level = "council"
    elif upper.startswith("MWANZA"):
        level = "region"
    else:
        level = "school"
    return ReportSpec(name, "generic", level, "unknown")


def report_types() -> set[str]:
    """The distinct report-type ids present in the catalogue."""
    return {spec.report_type for spec in _SPECS}
