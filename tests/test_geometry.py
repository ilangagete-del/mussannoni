"""Unit tests for the geometry helpers in :mod:`sars_convert.converter`.

These exercise the matrix parsing and the row/column clustering on a small but
*real* inline fixture modelled on the S1051 source (a title line, a two-column
header and two data rows with sub-pixel Y jitter), so the geometry logic is
covered regardless of the generic-vs-per-file decision recorded in FEAT-002.
"""

from __future__ import annotations

from sars_convert.converter import (
    FontInfo,
    Run,
    assign_column,
    cluster_columns,
    cluster_rows,
    is_rotated,
    parse_font_classes,
    parse_matrix,
    parse_page_size,
)


def test_parse_matrix_reads_translation() -> None:
    matrix = parse_matrix("z-index:5;transform:matrix(1,0,0,1,441.19,75.87)")
    assert matrix is not None
    a, b, c, d, x, y = matrix
    assert (a, b, c, d) == (1.0, 0.0, 0.0, 1.0)
    assert x == 441.19
    assert y == 75.87


def test_parse_matrix_missing_returns_none() -> None:
    assert parse_matrix("z-index:5") is None
    assert parse_matrix("transform:matrix(1,0,0,1)") is None


def test_is_rotated_detects_off_diagonal() -> None:
    assert not is_rotated((1, 0, 0, 1, 10, 20))
    assert is_rotated((0, 1, -1, 0, 10, 20))  # 90-degree rotation


def test_parse_font_classes_resolves_pooled_style() -> None:
    style = (
        ".c4{font-family:Arial, Helvetica, sans-serif;font-size:9.76px;"
        "font-weight:700;color:#002060}"
        ".c13{font-family:Arial;font-size:9.76px;color:#ffffff}"
    )
    fonts = parse_font_classes(style)
    assert fonts["c4"].size == 9.76
    assert fonts["c4"].weight == "700"
    assert fonts["c4"].color == "#002060"
    assert fonts["c13"].color == "#ffffff"


def test_parse_page_size_landscape() -> None:
    assert parse_page_size("@page{size:1056px 816px;margin:0}") == (1056.0, 816.0)


def _fixture_runs() -> list[Run]:
    f = FontInfo()
    # A two-column table with sub-pixel baseline jitter between paired runs,
    # mirroring the S1051 "name at Y=303.8 / number at Y=304.4" pattern.
    return [
        Run("CNO", x=66.0, y=288.5, rotated=False, font=f),
        Run("NAME", x=122.5, y=288.5, rotated=False, font=f),
        Run("S1051-0001", x=66.4, y=304.4, rotated=False, font=f),
        Run("ABIGAEL", x=122.9, y=303.8, rotated=False, font=f),
        Run("S1051-0002", x=66.4, y=321.7, rotated=False, font=f),
        Run("ADELINA", x=122.9, y=321.1, rotated=False, font=f),
    ]


def test_cluster_rows_absorbs_baseline_jitter() -> None:
    rows = cluster_rows(_fixture_runs(), tolerance=4.0)
    # Three visual rows: header + two data rows (jitter must not split them).
    assert len(rows) == 3
    header_texts = [r.text for r in rows[0].runs]
    assert header_texts == ["CNO", "NAME"]
    assert [r.text for r in rows[1].runs] == ["S1051-0001", "ABIGAEL"]


def test_cluster_columns_finds_two_bands() -> None:
    rows = cluster_rows(_fixture_runs())
    bands = cluster_columns(rows, tolerance=12.0)
    assert len(bands) == 2
    # First band groups the CNO column (~66), second the name column (~123-148).
    assert bands[0] < 100 < bands[1]


def test_assign_column_picks_nearest_band() -> None:
    bands = [66.0, 130.0]
    assert assign_column(66.4, bands) == 0
    assert assign_column(122.9, bands) == 1
    assert assign_column(200.0, bands) == 1


def test_column_clustering_is_fragile_when_header_and_data_x_differ() -> None:
    """Document the fragility that drove the FEAT-002 decision.

    When a header run and its data run start at meaningfully different X
    (a left-aligned header over a differently-indented value, or two logically
    distinct tables sharing a page), fixed-tolerance 1-D X clustering splits
    what is one logical column into several bands. This is why a naive generic
    detector over-fragments the S1051 page into ~13 bands.
    """
    f = FontInfo()
    runs = [
        Run("HEADER", x=100.0, y=10.0, rotated=False, font=f),
        Run("value", x=140.0, y=30.0, rotated=False, font=f),
    ]
    rows = cluster_rows(runs)
    bands = cluster_columns(rows, tolerance=12.0)
    # 40px apart with a 12px tolerance -> two bands for one logical column.
    assert len(bands) == 2
