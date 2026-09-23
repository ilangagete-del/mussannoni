"""Pair each messy source HTML with its ground-truth reference PDF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "sars"
OUT_HTML = ROOT / "output" / "html"
OUT_PDF = ROOT / "output" / "pdf"


@dataclass(frozen=True)
class SourcePair:
    name: str
    html: Path
    pdf: Path
    group: str

    def __str__(self) -> str:
        return f"{self.group}/{self.name}"


def _pair_dir(html_dir: Path, pdf_dir: Path, group: str) -> list[SourcePair]:
    pairs: list[SourcePair] = []
    for h in sorted(html_dir.glob("*.html")):
        p = pdf_dir / f"{h.stem}.pdf"
        if p.exists():
            pairs.append(SourcePair(name=h.stem, html=h, pdf=p, group=group))
    return pairs


def discover() -> list[SourcePair]:
    """All 19 document pairs: council, region and the standalone school slip."""
    pairs: list[SourcePair] = []
    for h in sorted(DATA.glob("*.html")):
        p = DATA / f"{h.stem}.pdf"
        if p.exists():
            pairs.append(SourcePair(name=h.stem, html=h, pdf=p, group="school"))
    pairs += _pair_dir(DATA / "council_html", DATA / "council_pdf", "council")
    pairs += _pair_dir(DATA / "region_html", DATA / "region_pdf", "region")
    return pairs


def select(only: str | None = None) -> list[SourcePair]:
    pairs = discover()
    if not only:
        return pairs
    needle = only.lower()
    hits = [p for p in pairs if needle in p.name.lower()]
    if not hits:
        raise SystemExit(f"no document matches {only!r}")
    return hits
