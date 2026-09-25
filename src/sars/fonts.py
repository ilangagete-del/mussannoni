"""Access to the reference font assets: families, advances, baseline offsets.

``tools/build_fonts.py`` derives, from the reference PDFs themselves, the font
files that MuPDF actually draws when it rasterises those PDFs (the real embedded
Arial / Times / Arial Narrow / Calibri for the region reports; URW Nimbus with
the PDF's own ``/Widths`` for the council reports, which embed nothing). This
module is the read side of that work:

* :func:`family` — the CSS family that reproduces a report's font *role*
  (``arial``, ``arial-bold``, ``times-bold``, ``arial-narrow-bold``, …);
* :func:`advance` / :func:`text_width` — that face's exact advance widths, so a
  renderer can measure a string the way the reference measured it and place
  centred / right-aligned text at the same x it used;
* :func:`baseline_offset` — how far below an absolutely positioned box's top
  edge WeasyPrint puts the first baseline, measured empirically by rendering a
  probe and reading the glyph origin back out of the produced PDF. That makes
  "put this baseline at exactly y" a solved problem rather than a guess.

Nothing here is a *style*: it is metric information about the reference's own
fonts, which is what makes exact placement possible.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets" / "fonts"
MANIFEST_PATH = ASSETS / "manifest.json"
CALIBRATION_PATH = ASSETS / "calibration.json"

#: Font size used for the baseline calibration probe (large = less rounding).
PROBE_SIZE = 100.0
#: The CSS every renderer must apply so shaping matches the reference: no
#: kerning, no ligatures, no optional features — the reference positioned each
#: run from raw advances.
SHAPING_RESET = (
    "font-kerning:none;font-variant-ligatures:none;font-variant:normal;"
    'font-feature-settings:"kern" 0,"liga" 0,"clig" 0,"calt" 0'
)


class FontAssetsMissing(RuntimeError):
    """Raised when the font assets have not been built yet."""


@lru_cache(maxsize=1)
def manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise FontAssetsMissing(
            "font assets missing — run `uv run python tools/build_fonts.py` "
            "(it derives them from the reference PDFs)"
        )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def asset(report: str, role: str) -> dict:
    """The asset record reproducing *role* for *report*."""
    data = manifest()
    entry = data["reports"].get(report, {}).get(role)
    if entry is None:
        available = ", ".join(sorted(data["reports"].get(report, {}))) or "none"
        raise KeyError(f"{report!r} has no font role {role!r}; available: {available}")
    return data["assets"][entry["asset"]]


def asset_for_pdf_font(report: str, pdf_font: str) -> dict:
    """The asset record for a font as *named inside* the reference PDF."""
    data = manifest()
    entry = data.get("by_pdf_font", {}).get(report, {}).get(pdf_font)
    if entry is None:
        raise KeyError(f"{report!r} does not use PDF font {pdf_font!r}")
    return data["assets"][entry["asset"]]


def role_for_pdf_font(report: str, pdf_font: str) -> str:
    """The role name for a font as the reference PDF names it.

    The region reports call their embedded fonts ``CIDFont+F1…F5``; the real face
    inside is Arial / Arial Bold / Times New Roman Bold / Arial Narrow Bold /
    Calibri, and the manifest keys roles by that real name. This resolves one to
    the other so a tool reading the reference's own text runs can ask for the
    right role.
    """
    data = manifest()
    entry = data.get("by_pdf_font", {}).get(report, {}).get(pdf_font)
    if entry is None:
        raise KeyError(f"{report!r} does not use PDF font {pdf_font!r}")
    wanted = entry["asset"]
    for role, record in data["reports"].get(report, {}).items():
        if record["asset"] == wanted:
            return role
    raise KeyError(f"no role for {pdf_font!r} in {report!r}")


def family(report: str, role: str) -> str:
    """CSS font-family string for a report's role."""
    return asset(report, role)["family"]


def advance(report: str, role: str, char: str) -> float:
    """Advance width of *char* in 1/1000 em, as the reference PDF declares it."""
    return float(asset(report, role)["advances"].get(str(ord(char)), 0.0))


def text_width(text: str, report: str, role: str, size_pt: float) -> float:
    """Width of *text* in points at *size_pt*, from the reference's advances.

    Characters the reference never used have no recorded advance; they fall back
    to the average of the recorded ones so a never-before-seen value still lands
    in a sensible place instead of at width 0.
    """
    advances = asset(report, role)["advances"]
    if not advances:
        return 0.0
    fallback = sum(float(v) for v in advances.values()) / len(advances)
    total = 0.0
    for char in text:
        total += float(advances.get(str(ord(char)), fallback))
    return total * size_pt / 1000.0


@lru_cache(maxsize=1)
def _calibration() -> dict:
    if CALIBRATION_PATH.exists():
        return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    return {}


def probe_char(css_family: str) -> str:
    """A character the face really contains, for calibration probes.

    Some reference faces are subsets with a 19-character cmap; probing them with
    a letter they do not carry makes the renderer fall back to another font and
    the measured baseline belongs to the wrong face (this cost 0.2pt of vertical
    drift before it was found).
    """
    data = manifest()
    for record in data["assets"].values():
        if record["family"] != css_family:
            codes = None
            continue
        codes = {int(code) for code in record["advances"]}
        for preferred in "HNXO0123456789ABCDEFGIJKLMPQRSTUVWYZ":
            if ord(preferred) in codes:
                return preferred
        if codes:
            return chr(sorted(codes)[0])
    return "H"


def _measure_baseline(css_family: str, size_pt: float, engine: str) -> float:
    """Render a probe and read back where WeasyPrint put the baseline.

    Returns the baseline offset as a fraction of the font size, for a box styled
    ``line-height:0`` (the styling :func:`sars.templates.fixedlayout.text` uses).
    """
    import pymupdf

    from .printing import print_pdf

    sample = probe_char(css_family)
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        "@page{size:612pt 792pt;margin:0}html,body{margin:0;padding:0}"
        f".p{{position:absolute;left:0;top:0;line-height:0;white-space:pre;"
        f"font-family:'{css_family}';font-size:{size_pt:.4f}pt;{SHAPING_RESET}}}"
        f"</style></head><body><div class='p'>{sample}</div></body></html>"
    )
    pdf_bytes = print_pdf(html, engine=engine)
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        spans = [s for s in doc[0].get_texttrace() if s["type"] == 0 and s["chars"]]
        if not spans:
            raise RuntimeError(f"calibration probe produced no text for {css_family!r}")
        return spans[0]["chars"][0][2][1]


def baseline_offset(css_family: str, size_pt: float, engine: str = "weasyprint") -> float:
    """Distance from an absolutely positioned box's top to its first baseline.

    Measured per (family, size) — WeasyPrint's half-leading for ``line-height:0``
    is not perfectly proportional to the font size, and a 0.2pt error is a
    visible half-pixel at the gate's raster — by rendering a probe through
    WeasyPrint and reading the glyph origin back out of the produced PDF. The
    results are cached in ``assets/fonts/calibration.json``, so placement is
    calibrated against the real renderer instead of inferred from font metrics.
    """
    key = f"{engine}|{css_family}@{size_pt:.4f}"
    cache = dict(_calibration())
    offset = cache.get(key)
    if offset is None:
        offset = _measure_baseline(css_family, size_pt, engine)
        _store_calibration(key, offset)
    return offset


def _store_calibration(key: str, offset: float) -> None:
    """Add one measurement to the cache, safely for concurrent renderers.

    Reports are rendered in parallel, so several processes can measure different
    (family, size) pairs at once. Two things make that safe: the file is re-read
    immediately before writing, so a sibling's entries are not thrown away, and it
    is replaced atomically, so a reader never sees a half-written file. A key lost
    to a race is merely measured again next time; a truncated file would break
    every renderer.
    """
    import os
    import tempfile

    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, float] = {}
    if CALIBRATION_PATH.exists():
        try:
            merged = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            merged = {}
    merged[key] = offset
    handle, temporary = tempfile.mkstemp(
        dir=str(CALIBRATION_PATH.parent), prefix=".calibration-", suffix=".json"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(merged, stream, indent=1, sort_keys=True)
        os.replace(temporary, CALIBRATION_PATH)
    except BaseException:
        os.unlink(temporary)
        raise
    _calibration.cache_clear()
