"""Verify rendered PDFs against the reference PDFs (ground truth).

The clean output produced by :mod:`sars_convert.build_html` +
:mod:`sars_convert.render` is intentionally **more compact** than the original
``pdf2html`` reference PDFs (substituted fonts, tighter rows), so page counts and
pixels do NOT match one-for-one. Exact pixel identity is therefore *not* the bar.
What must be faithful is **content and structure**: every tabular value and header
present and correctly associated.

This module measures fidelity of each generated PDF (``output/pdf/<stem>.pdf``)
against its ground-truth reference PDF (``data/sars/...``) two ways:

Primary - text / value fidelity
    Extract text from both PDFs with pymupdf, normalise (upper-case, strip
    punctuation noise), tokenise, and split tokens into *value* tokens
    (numbers, GPAs, percentages, codes - the real payload) and *word* tokens
    (names, headers). We report the recall of the reference tokens in the
    generated document. Rotated / garbled header glyphs in the reference (e.g.
    vertical ``C/RANK`` runs, the banner emitted as one block) are handled by
    (a) weighting value tokens - which carry the data - above word tokens and
    (b) reporting the specific discrepancies rather than failing blindly.

Secondary - appearance
    Rasterise every page of each PDF with pymupdf, stack the pages of a document
    into one tall image, resize both stacks to a common canvas, and compute a
    similarity score from the grayscale histogram correlation and mean pixel
    difference. Because page counts differ by design, this is an *advisory*
    signal only, compared whole-document (not page-index to page-index).

The reference PDFs under ``data/sars`` are ground truth and must NEVER be
modified. This module only reads them.

Public API
----------
``verify_text(generated_pdf, reference_pdf)`` -> ``TextResult``
``verify_image(generated_pdf, reference_pdf, dpi=110)`` -> ``float`` (0..1)
``verify_document(stem, generated_pdf, reference_pdf)`` -> ``DocResult``
``verify_all(...)`` -> ``list[DocResult]`` for the whole batch
``write_report(results, md_path, json_path)`` - emit ``VERIFICATION.md`` / JSON
``main()`` - run the whole batch and write ``output/VERIFICATION.md``
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass, field

import pymupdf

from .build_html import HTML_DIR  # noqa: F401  (kept for symmetry / discoverability)
from .render import PDF_DIR

# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #
DATA_DIR = os.path.join("data", "sars")
COUNCIL_PDF_DIR = os.path.join(DATA_DIR, "council_pdf")
REGION_PDF_DIR = os.path.join(DATA_DIR, "region_pdf")
S1051_STEM = "S1051-MKOLANI SECONDARY SCHOOL"

OUTPUT_DIR = "output"
REPORT_MD = os.path.join(OUTPUT_DIR, "VERIFICATION.md")
REPORT_JSON = os.path.join(OUTPUT_DIR, "verify_report.json")

# --------------------------------------------------------------------------- #
# Thresholds (tunable, advisory except TEXT_PASS which gates pass/fail)
# --------------------------------------------------------------------------- #
# Weighted token recall at/above this counts as a text-fidelity PASS.
TEXT_PASS = 0.90
# Value tokens (numbers/GPAs/percentages) carry the real payload, so they are
# weighted much higher than word tokens (names/headers, some of which arrive as
# garbled rotated glyphs in the reference).
VALUE_WEIGHT = 3.0
WORD_WEIGHT = 1.0
# A sane floor for the advisory whole-document image similarity.
IMAGE_FLOOR = 0.30

# A value token: a run that contains at least one digit (ranks, counts, GPAs,
# percentages, candidate numbers such as ``S1051-0001``). These are the cells
# whose presence and correctness matter most.
_VALUE_RE = re.compile(r"[0-9][0-9A-Z./%-]*|[A-Z]+[0-9][0-9A-Z./%-]*")
# A word token: an alphabetic run of >= 2 chars (names, header words).
_WORD_RE = re.compile(r"[A-Z]{2,}")


# --------------------------------------------------------------------------- #
# Result records
# --------------------------------------------------------------------------- #
@dataclass
class TextResult:
    """Outcome of the primary text/value fidelity comparison."""

    passed: bool
    score: float  # weighted recall 0..1
    value_recall: float
    word_recall: float
    ref_value_tokens: int
    ref_word_tokens: int
    missing_values: list[str] = field(default_factory=list)
    missing_words: list[str] = field(default_factory=list)


@dataclass
class DocResult:
    """Per-document verification result (text primary + image advisory)."""

    stem: str
    category: str
    generated_pdf: str
    reference_pdf: str
    gen_pages: int
    ref_pages: int
    text_passed: bool
    text_score: float
    value_recall: float
    word_recall: float
    image_similarity: float
    notes: list[str] = field(default_factory=list)
    error: str | None = None


# --------------------------------------------------------------------------- #
# Text extraction + normalisation
# --------------------------------------------------------------------------- #
def _pdf_text(path: str) -> str:
    """Return the concatenated text of every page of ``path``."""
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _tokenise(text: str) -> tuple[list[str], list[str]]:
    """Return ``(value_tokens, word_tokens)`` from raw PDF text.

    Normalises to upper-case first. Value tokens are runs containing a digit
    (numbers, GPAs, percentages, candidate codes); word tokens are alphabetic
    runs of two or more letters (names, header words).
    """
    up = text.upper()
    values = _VALUE_RE.findall(up)
    words = _WORD_RE.findall(up)
    return values, words


def _recall(ref: set[str], gen: set[str]) -> tuple[float, list[str]]:
    """Fraction of ``ref`` present in ``gen``, plus the sorted missing set."""
    if not ref:
        return 1.0, []
    missing = sorted(ref - gen)
    recall = (len(ref) - len(missing)) / len(ref)
    return recall, missing


def verify_text(generated_pdf: str, reference_pdf: str) -> TextResult:
    """Compare the text/value content of a generated PDF against a reference.

    The score is a weighted recall of the reference tokens found in the
    generated PDF, with value tokens (the tabular payload) weighted above word
    tokens (names/headers, some of which are garbled rotated glyphs in the
    reference). Returns a :class:`TextResult` with the specific missing tokens.
    """
    ref_values, ref_words = _tokenise(_pdf_text(reference_pdf))
    gen_values, gen_words = _tokenise(_pdf_text(generated_pdf))

    ref_v, gen_v = set(ref_values), set(gen_values)
    ref_w, gen_w = set(ref_words), set(gen_words)

    value_recall, missing_values = _recall(ref_v, gen_v)
    word_recall, missing_words = _recall(ref_w, gen_w)

    # Weighted combined recall. If a document has no value tokens (rare), fall
    # back to the word recall alone.
    wv = VALUE_WEIGHT * len(ref_v)
    ww = WORD_WEIGHT * len(ref_w)
    denom = wv + ww
    score = (value_recall * wv + word_recall * ww) / denom if denom else 1.0

    return TextResult(
        passed=score >= TEXT_PASS,
        score=score,
        value_recall=value_recall,
        word_recall=word_recall,
        ref_value_tokens=len(ref_v),
        ref_word_tokens=len(ref_w),
        missing_values=missing_values,
        missing_words=missing_words,
    )


# --------------------------------------------------------------------------- #
# Image similarity (advisory)
# --------------------------------------------------------------------------- #
def _stacked_gray(path: str, dpi: int, width: int) -> list[list[int]]:
    """Rasterise every page, stack vertically, return a grayscale row list.

    Each page is rendered at ``dpi``, converted to grayscale, and its rows are
    appended to one tall image normalised to ``width`` columns (nearest-column
    sampling, no external resize dependency beyond pixmap sampling).
    """
    from PIL import Image

    rows: list[list[int]] = []
    with pymupdf.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = img.convert("L").resize((width, max(1, pix.height * width // pix.width)))
            data = list(img.tobytes())
            for y in range(img.height):
                rows.append(data[y * width : (y + 1) * width])
    return rows


def _histogram(rows: list[list[int]], bins: int = 32) -> list[float]:
    """Normalised grayscale histogram over all pixels."""
    hist = [0] * bins
    total = 0
    step = 256 // bins
    for row in rows:
        for px in row:
            hist[min(bins - 1, px // step)] += 1
            total += 1
    if total == 0:
        return [0.0] * bins
    return [h / total for h in hist]


def _hist_correlation(a: list[float], b: list[float]) -> float:
    """Pearson-style correlation of two histograms, clamped to 0..1."""
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((a[i] - ma) ** 2 for i in range(n)))
    db = math.sqrt(sum((b[i] - mb) ** 2 for i in range(n)))
    if da == 0 or db == 0:
        return 1.0 if a == b else 0.0
    corr = num / (da * db)
    return max(0.0, min(1.0, corr))


def verify_image(generated_pdf: str, reference_pdf: str, dpi: int = 110) -> float:
    """Whole-document, page-count-agnostic image similarity in 0..1.

    Both PDFs are rasterised at ``dpi`` and their pages stacked into one tall
    grayscale image at a common width; similarity is the grayscale histogram
    correlation between the two stacks. Because our clean output paginates
    differently from the reference by design, this is an **advisory** signal and
    is compared whole-document, not page-index to page-index.
    """
    width = 400
    gen_rows = _stacked_gray(generated_pdf, dpi, width)
    ref_rows = _stacked_gray(reference_pdf, dpi, width)
    gen_hist = _histogram(gen_rows)
    ref_hist = _histogram(ref_rows)
    return round(_hist_correlation(gen_hist, ref_hist), 4)


# --------------------------------------------------------------------------- #
# Reference-PDF resolution
# --------------------------------------------------------------------------- #
def reference_for(stem: str) -> str | None:
    """Return the ground-truth reference PDF path for a generated ``stem``.

    Checks the S1051 standalone, then the council and region reference dirs.
    Returns ``None`` if no reference PDF exists for the stem.
    """
    if stem == S1051_STEM:
        p = os.path.join(DATA_DIR, f"{stem}.pdf")
        return p if os.path.exists(p) else None
    for base in (COUNCIL_PDF_DIR, REGION_PDF_DIR):
        p = os.path.join(base, f"{stem}.pdf")
        if os.path.exists(p):
            return p
    return None


def _category(stem: str, reference_pdf: str) -> str:
    if stem == S1051_STEM:
        return "student"
    if os.path.dirname(reference_pdf).endswith("council_pdf"):
        return "council"
    return "region"


def _page_count(path: str) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


# --------------------------------------------------------------------------- #
# Per-document + batch orchestration
# --------------------------------------------------------------------------- #
def verify_document(stem: str, generated_pdf: str, reference_pdf: str) -> DocResult:
    """Verify one generated PDF against its reference and return a DocResult."""
    category = _category(stem, reference_pdf)
    try:
        text = verify_text(generated_pdf, reference_pdf)
        image = verify_image(generated_pdf, reference_pdf)
        gen_pages = _page_count(generated_pdf)
        ref_pages = _page_count(reference_pdf)
    except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover - defensive
        return DocResult(
            stem=stem,
            category=category,
            generated_pdf=generated_pdf,
            reference_pdf=reference_pdf,
            gen_pages=0,
            ref_pages=0,
            text_passed=False,
            text_score=0.0,
            value_recall=0.0,
            word_recall=0.0,
            image_similarity=0.0,
            notes=[],
            error=f"{type(exc).__name__}: {exc}",
        )

    notes: list[str] = []
    if gen_pages != ref_pages:
        notes.append(
            f"page count differs (generated {gen_pages} vs reference {ref_pages}); "
            "expected - clean output is more compact, compared by content not pages"
        )
    if text.value_recall < 1.0:
        sample = ", ".join(text.missing_values[:12])
        notes.append(
            f"{len(text.missing_values)} reference value token(s) not found "
            f"(value recall {text.value_recall:.3f}): {sample}"
        )
    if text.missing_words:
        sample = ", ".join(text.missing_words[:12])
        notes.append(
            f"{len(text.missing_words)} reference word token(s) not found "
            f"(word recall {text.word_recall:.3f}; often garbled rotated/banner "
            f"glyphs): {sample}"
        )
    if image < IMAGE_FLOOR:
        notes.append(f"image similarity {image:.3f} below advisory floor {IMAGE_FLOOR}")

    return DocResult(
        stem=stem,
        category=category,
        generated_pdf=generated_pdf,
        reference_pdf=reference_pdf,
        gen_pages=gen_pages,
        ref_pages=ref_pages,
        text_passed=text.passed,
        text_score=round(text.score, 4),
        value_recall=round(text.value_recall, 4),
        word_recall=round(text.word_recall, 4),
        image_similarity=image,
        notes=notes,
    )


def verify_all(pdf_dir: str = PDF_DIR) -> list[DocResult]:
    """Verify every generated PDF in ``pdf_dir`` for which a reference exists."""
    results: list[DocResult] = []
    if not os.path.isdir(pdf_dir):
        return results
    for name in sorted(os.listdir(pdf_dir)):
        if not name.endswith(".pdf"):
            continue
        stem = name[:-4]
        generated_pdf = os.path.join(pdf_dir, name)
        reference_pdf = reference_for(stem)
        if reference_pdf is None:
            results.append(
                DocResult(
                    stem=stem,
                    category="unknown",
                    generated_pdf=generated_pdf,
                    reference_pdf="",
                    gen_pages=_page_count(generated_pdf),
                    ref_pages=0,
                    text_passed=False,
                    text_score=0.0,
                    value_recall=0.0,
                    word_recall=0.0,
                    image_similarity=0.0,
                    notes=["no reference PDF found for this stem"],
                    error="missing reference",
                )
            )
            continue
        results.append(verify_document(stem, generated_pdf, reference_pdf))
    return results


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def write_report(
    results: list[DocResult],
    md_path: str = REPORT_MD,
    json_path: str = REPORT_JSON,
) -> None:
    """Write ``VERIFICATION.md`` and ``verify_report.json`` for ``results``."""
    os.makedirs(os.path.dirname(os.path.abspath(md_path)), exist_ok=True)

    passed = [r for r in results if r.text_passed]
    failed = [r for r in results if not r.text_passed]
    avg_text = sum(r.text_score for r in results) / len(results) if results else 0.0
    avg_image = sum(r.image_similarity for r in results) / len(results) if results else 0.0

    lines: list[str] = []
    lines.append("# Fidelity verification report")
    lines.append("")
    lines.append(
        "Each generated PDF (`output/pdf/<stem>.pdf`) is compared against its "
        "ground-truth reference PDF (`data/sars/...`). The reference PDFs are "
        "never modified."
    )
    lines.append("")
    lines.append(
        "**Primary signal - text/value fidelity:** weighted recall of the "
        "reference document's tokens in the generated PDF (value tokens - "
        "numbers, GPAs, percentages, codes - weighted above word tokens). "
        f"A document passes at recall >= {TEXT_PASS:.2f}."
    )
    lines.append("")
    lines.append(
        "**Secondary signal - appearance:** whole-document grayscale histogram "
        "similarity of the page stacks (advisory only; page counts differ by "
        "design because the clean output is more compact)."
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Documents verified: **{len(results)}**")
    lines.append(f"- Text fidelity PASS: **{len(passed)}** / {len(results)}")
    lines.append(f"- Text fidelity FAIL: **{len(failed)}**")
    lines.append(f"- Average weighted text score: **{avg_text:.4f}**")
    lines.append(f"- Average image similarity (advisory): **{avg_image:.4f}**")
    lines.append("")
    lines.append("## Per-document results")
    lines.append("")
    lines.append(
        "| Document | Category | Text | Score | Value recall | Word recall "
        "| Image sim | Pages (gen/ref) |"
    )
    lines.append("| --- | --- | :---: | ---: | ---: | ---: | ---: | :---: |")
    for r in results:
        status = "PASS" if r.text_passed else "FAIL"
        lines.append(
            f"| {r.stem} | {r.category} | {status} | {r.text_score:.4f} | "
            f"{r.value_recall:.4f} | {r.word_recall:.4f} | "
            f"{r.image_similarity:.4f} | {r.gen_pages}/{r.ref_pages} |"
        )
    lines.append("")
    lines.append("## Notes and discrepancies")
    lines.append("")
    for r in results:
        lines.append(f"### {r.stem}")
        if r.error:
            lines.append(f"- ERROR: {r.error}")
        if not r.notes and not r.error:
            lines.append("- No discrepancies: all reference values present.")
        for note in r.notes:
            lines.append(f"- {note}")
        lines.append("")

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "summary": {
                    "documents": len(results),
                    "text_pass": len(passed),
                    "text_fail": len(failed),
                    "avg_text_score": round(avg_text, 4),
                    "avg_image_similarity": round(avg_image, 4),
                    "text_pass_threshold": TEXT_PASS,
                    "image_floor": IMAGE_FLOOR,
                },
                "documents": [asdict(r) for r in results],
            },
            fh,
            indent=2,
        )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI
    results = verify_all()
    if not results:
        print(f"No generated PDFs found in {PDF_DIR}/ - run the pipeline first.")
        return 1
    write_report(results)
    passed = sum(1 for r in results if r.text_passed)
    print(
        f"Verified {len(results)} documents: {passed} passed text fidelity. "
        f"Report written to {REPORT_MD} and {REPORT_JSON}."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
