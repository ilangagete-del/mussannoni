"""Tests for :mod:`sars_convert.render` (FEAT-005 WeasyPrint rendering).

These render tiny clean HTML documents (with an embedded ``@page`` A4 rule) to
PDF and assert the output is a valid, non-empty PDF whose page size and
orientation match the embedded rule, as reported by pymupdf. They run without
touching the recovered IR or the reference PDFs.
"""

from __future__ import annotations

import os

import pymupdf

from sars_convert import render as R

# A4 in points: 210x297 mm -> 595x842 pt (portrait), swapped for landscape.
A4_SHORT = 595
A4_LONG = 842
TOL = 3  # WeasyPrint rounds to the nearest point.


def _clean_html(orientation: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>@page {{ size: A4 {orientation}; margin: 10mm; }}"
        "table{border-collapse:collapse} td,th{border:1px solid #000;padding:2px}"
        "</style></head><body>"
        "<h1>SAMPLE REPORT</h1>"
        "<table><thead><tr><th>S/NO.</th><th>SCHOOL</th><th>GPA</th></tr></thead>"
        "<tbody><tr><td>1</td><td>MKOLANI</td><td>2.10</td></tr></tbody></table>"
        "</body></html>"
    )


def _write_html(directory: str, stem: str, orientation: str) -> str:
    path = os.path.join(directory, f"{stem}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_clean_html(orientation))
    return path


def _assert_valid_pdf(path: str) -> None:
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0
    with open(path, "rb") as fh:
        assert fh.read(5) == b"%PDF-"


def test_render_landscape_a4(tmp_path):
    html_path = _write_html(str(tmp_path), "landscape-doc", "landscape")
    out_path = os.path.join(str(tmp_path), "landscape-doc.pdf")

    R.render(html_path, out_path)

    _assert_valid_pdf(out_path)
    doc = pymupdf.open(out_path)
    rect = doc[0].rect
    assert abs(rect.width - A4_LONG) <= TOL
    assert abs(rect.height - A4_SHORT) <= TOL
    assert rect.width > rect.height  # landscape


def test_render_portrait_a4(tmp_path):
    html_path = _write_html(str(tmp_path), "portrait-doc", "portrait")
    out_path = os.path.join(str(tmp_path), "portrait-doc.pdf")

    R.render(html_path, out_path)

    _assert_valid_pdf(out_path)
    doc = pymupdf.open(out_path)
    rect = doc[0].rect
    assert abs(rect.width - A4_SHORT) <= TOL
    assert abs(rect.height - A4_LONG) <= TOL
    assert rect.height > rect.width  # portrait


def test_render_all_writes_one_pdf_per_html(tmp_path):
    html_dir = tmp_path / "html"
    out_dir = tmp_path / "pdf"
    html_dir.mkdir()
    _write_html(str(html_dir), "a", "landscape")
    _write_html(str(html_dir), "b", "portrait")
    # A stylesheet in the dir must be ignored (only .html documents render).
    (html_dir / "styles.css").write_text("body{color:#000}", encoding="utf-8")

    written = R.render_all(str(html_dir), str(out_dir))

    assert len(written) == 2
    for path in written:
        _assert_valid_pdf(path)
    assert sorted(os.path.basename(p) for p in written) == ["a.pdf", "b.pdf"]
