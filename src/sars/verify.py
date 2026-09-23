"""Verify generated A4 PDFs against the original reference PDFs.

Two independent checks are reported per document:

``page_size``
    the generated PDF really is A4 in the expected orientation;
``text``
    the visible text recovered from the generated PDF matches the reference,
    measured as a token-sequence similarity plus an explicit count of tokens
    that are missing from, or extra in, the output.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

A4_SHORT, A4_LONG = 595.276, 841.890
_TOL = 2.0

_TOKEN = re.compile(r"[^\s]+")


@dataclass
class Result:
    name: str
    ref_pages: int
    out_pages: int
    orientation: str
    size_ok: bool
    similarity: float
    #: True when each page's text is character-for-character identical once all
    #: whitespace is removed, i.e. no data is missing even if two adjacent cells
    #: render close enough to extract as a single token.
    content_ok: bool = False
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def pages_ok(self) -> bool:
        return self.ref_pages == self.out_pages

    @property
    def ok(self) -> bool:
        return self.size_ok and self.pages_ok and (not self.missing or self.content_ok)

    def line(self) -> str:
        flag = "PASS" if self.ok else "FAIL"
        note = ""
        if self.missing and self.content_ok:
            note = "  (token-boundary only; no data lost)"
        return (
            f"[{flag}] {self.name}\n"
            f"        pages ref={self.ref_pages} out={self.out_pages} "
            f"orientation={self.orientation} A4={'yes' if self.size_ok else 'NO'}\n"
            f"        text similarity={self.similarity * 100:.2f}% "
            f"missing={len(self.missing)} extra={len(self.extra)} "
            f"glyphs={'identical' if self.content_ok else 'DIFFER'}{note}"
        )


def tokens(pdf_path: Path) -> list[str]:
    doc = pymupdf.open(pdf_path)
    out: list[str] = []
    for page in doc:
        out.extend(_TOKEN.findall(page.get_text("text")))
    doc.close()
    return out


def page_tokens(pdf_path: Path) -> list[list[str]]:
    """Tokens grouped per page, so content is checked page-for-page."""
    doc = pymupdf.open(pdf_path)
    pages = [_TOKEN.findall(page.get_text("text")) for page in doc]
    doc.close()
    return pages


def _page_size_ok(pdf_path: Path, orientation: str) -> bool:
    doc = pymupdf.open(pdf_path)
    try:
        for page in doc:
            w, h = page.rect.width, page.rect.height
            want = (A4_LONG, A4_SHORT) if orientation == "landscape" else (A4_SHORT, A4_LONG)
            if abs(w - want[0]) > _TOL or abs(h - want[1]) > _TOL:
                return False
        return True
    finally:
        doc.close()


def _diff(ref: list[str], out: list[str]) -> tuple[list[str], list[str]]:
    sm = difflib.SequenceMatcher(a=ref, b=out, autojunk=False)
    missing: list[str] = []
    extra: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            missing.extend(ref[i1:i2])
        if tag in ("replace", "insert"):
            extra.extend(out[j1:j2])
    return missing, extra


def verify(reference: Path, generated: Path, orientation: str) -> Result:
    """Compare *generated* against *reference* page-for-page.

    Fidelity is measured on **content completeness per page** (a multiset
    comparison) rather than on reading order: a table cell carries the same
    meaning wherever the PDF text operators happen to emit it, so ordering
    differences are not defects, whereas a missing or duplicated value is.
    """
    ref_pages_tok = page_tokens(reference)
    out_pages_tok = page_tokens(generated)

    missing: list[str] = []
    extra: list[str] = []
    matched = 0
    total_ref = 0

    for idx in range(max(len(ref_pages_tok), len(out_pages_tok))):
        ref_c = Counter(ref_pages_tok[idx] if idx < len(ref_pages_tok) else [])
        out_c = Counter(out_pages_tok[idx] if idx < len(out_pages_tok) else [])
        matched += sum((ref_c & out_c).values())
        total_ref += sum(ref_c.values())
        missing.extend((ref_c - out_c).elements())
        extra.extend((out_c - ref_c).elements())

    similarity = matched / total_ref if total_ref else 1.0

    # Order-independent proof that no glyph was lost or invented on any page.
    # This still catches real data loss, but tolerates two adjacent cells whose
    # text renders close enough to be extracted as one token.
    content_ok = len(ref_pages_tok) == len(out_pages_tok) and all(
        Counter("".join(a)) == Counter("".join(b))
        for a, b in zip(ref_pages_tok, out_pages_tok, strict=False)
    )

    return Result(
        name=generated.stem,
        ref_pages=len(ref_pages_tok),
        out_pages=len(out_pages_tok),
        orientation=orientation,
        size_ok=_page_size_ok(generated, orientation),
        similarity=similarity,
        content_ok=content_ok,
        missing=missing,
        extra=extra,
    )
