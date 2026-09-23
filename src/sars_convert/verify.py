"""Verify rendered PDFs against the reference PDFs (ground truth).

Placeholder module. Filled by a later feature.

Planned responsibility
-----------------------
Rasterise both the generated PDF and the reference PDF (via pymupdf or poppler)
to page images and compare them visually/structurally so the fidelity of the
final output can be measured. The reference PDFs under ``data/sars`` are ground
truth and must never be modified.
"""

from __future__ import annotations


def verify(generated_pdf: str, reference_pdf: str) -> float:
    """Compare a generated PDF against a reference PDF; return a similarity score.

    Not implemented yet - placeholder for a later feature.
    """
    raise NotImplementedError("verify.verify is implemented in a later feature")
