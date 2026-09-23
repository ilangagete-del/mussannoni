"""Tests for :mod:`sars_convert.verify` (FEAT-006 fidelity verification).

The headline test runs the real pipeline for one document
(``MWANZA CC 10 BEST SCHOOLS`` - a canonical, known-faithful council report):
extract its IR from the reference PDF, build clean HTML, render it to a PDF with
WeasyPrint, then verify that PDF against the ground-truth reference. It asserts
the primary text/value fidelity meets the pass threshold (all reference values
present) and the advisory image similarity clears a sane floor.

Two lighter tests cover the tokeniser/recall helpers and the report writer so
the scoring and Markdown/JSON output are exercised without the full pipeline.
"""

from __future__ import annotations

import json
import os

from sars_convert import build_html, extract, render, verify

CANONICAL_STEM = "MWANZA CC 10 BEST SCHOOLS"
CANONICAL_REF = os.path.join("data", "sars", "council_pdf", f"{CANONICAL_STEM}.pdf")


def _pipeline_render(stem: str, reference_pdf: str, category: str, out_dir: str) -> str:
    """Run extract -> build -> render for one document into ``out_dir``.

    Returns the path of the generated PDF. Exercises the real production code
    (no fixtures) so the verification test reflects the actual output.
    """
    ir = extract.extract_document(stem, reference_pdf, category)
    html = build_html.build_document_html(extract._ir_to_dict(ir))

    html_path = os.path.join(out_dir, f"{stem}.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    # the clean HTML links styles.css relatively, so write it alongside
    with open(os.path.join(out_dir, build_html.STYLESHEET), "w", encoding="utf-8") as fh:
        fh.write(build_html.STYLES_CSS)

    pdf_path = os.path.join(out_dir, f"{stem}.pdf")
    render.render(html_path, pdf_path)
    return pdf_path


def test_verify_canonical_council_document(tmp_path):
    """The known-faithful council report passes text fidelity and clears the
    advisory image-similarity floor when compared to its reference PDF."""
    assert os.path.exists(CANONICAL_REF), "reference PDF must be present (ground truth)"

    generated_pdf = _pipeline_render(CANONICAL_STEM, CANONICAL_REF, "council", str(tmp_path))

    text = verify.verify_text(generated_pdf, CANONICAL_REF)
    # Every reference *value* token (numbers, GPAs, percentages, codes) must be
    # present - this is the tabular payload.
    assert text.value_recall == 1.0, f"missing values: {text.missing_values}"
    # Weighted text fidelity passes the defined threshold.
    assert text.passed
    assert text.score >= verify.TEXT_PASS

    image = verify.verify_image(generated_pdf, CANONICAL_REF)
    assert image >= verify.IMAGE_FLOOR

    result = verify.verify_document(CANONICAL_STEM, generated_pdf, CANONICAL_REF)
    assert result.text_passed
    assert result.category == "council"
    assert result.error is None


def test_tokenise_and_recall_helpers():
    """The tokeniser separates value vs word tokens and recall is exact."""
    values, words = verify._tokenise("MUSABE BOYS 225 100 1.4418 S1051-0001")
    assert "225" in values and "100" in values and "1.4418" in values
    assert "S1051-0001" in values  # candidate code counts as a value token
    assert "MUSABE" in words and "BOYS" in words
    # digits alone are not word tokens
    assert "225" not in words

    recall, missing = verify._recall({"A", "B", "C", "D"}, {"A", "B"})
    assert recall == 0.5
    assert missing == ["C", "D"]
    # empty reference is trivially full recall
    assert verify._recall(set(), {"X"}) == (1.0, [])


def test_write_report_emits_markdown_and_json(tmp_path):
    """write_report produces a VERIFICATION.md and JSON summary for results."""
    results = [
        verify.DocResult(
            stem="DOC ONE",
            category="council",
            generated_pdf="output/pdf/DOC ONE.pdf",
            reference_pdf="data/sars/council_pdf/DOC ONE.pdf",
            gen_pages=2,
            ref_pages=3,
            text_passed=True,
            text_score=0.99,
            value_recall=1.0,
            word_recall=0.97,
            image_similarity=0.96,
            notes=["page count differs (expected)"],
        ),
        verify.DocResult(
            stem="DOC TWO",
            category="region",
            generated_pdf="output/pdf/DOC TWO.pdf",
            reference_pdf="data/sars/region_pdf/DOC TWO.pdf",
            gen_pages=1,
            ref_pages=1,
            text_passed=False,
            text_score=0.80,
            value_recall=0.79,
            word_recall=0.90,
            image_similarity=0.95,
            notes=["121 reference value token(s) not found"],
        ),
    ]

    md_path = tmp_path / "VERIFICATION.md"
    json_path = tmp_path / "verify_report.json"
    verify.write_report(results, str(md_path), str(json_path))

    md = md_path.read_text(encoding="utf-8")
    assert "# Fidelity verification report" in md
    assert "DOC ONE" in md and "DOC TWO" in md
    assert "PASS" in md and "FAIL" in md
    assert "Text fidelity PASS: **1** / 2" in md

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["summary"]["documents"] == 2
    assert data["summary"]["text_pass"] == 1
    assert data["summary"]["text_fail"] == 1
    assert len(data["documents"]) == 2
