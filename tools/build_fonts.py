"""Build the font assets required to reproduce the reference PDFs exactly.

Why this exists
---------------
The reference PDFs are Microsoft output (Excel LTSC / "Microsoft: Print To PDF")
and they come in two flavours, which the fidelity gate rasterises through MuPDF:

* the **region** reports embed the REAL fonts (Arial, Arial Bold, Times New
  Roman Bold, Arial Narrow Bold, Calibri) as full TrueType files with
  ``Identity-H`` CID encoding. MuPDF therefore draws the real Arial outlines.
  Reproducing them means using *those very font files*, so this tool extracts
  them out of the reference PDFs.
* the **council** reports and the school slip do NOT embed Arial / Times New
  Roman at all; they only name them. MuPDF then substitutes its built-in URW
  Nimbus base-14 fonts and takes the glyph advances from the PDF's own
  ``/Widths`` array. Reproducing *that* rendering means using Nimbus Sans /
  Nimbus Roman (byte-identical to MuPDF's built-ins - verified) with the PDF's
  ``/Widths`` written into the font's ``hmtx``, which this tool synthesises.
  (The embedded Arial Narrow / Tahoma subsets in those files are extracted as
  usual.)

Without this, WeasyPrint renders every report in the only family installed in
this sandbox (Noto Sans), which is why the honest baseline was 38-90% wrong.

Output
------
``assets/fonts/*.ttf|otf``  the font files, installed into the user font dir so
                            fontconfig (and therefore WeasyPrint) finds them.
``assets/fonts/manifest.json``  per report: which CSS family reproduces which
                            reference font, plus that font's exact per-character
                            advance widths (per 1000 units) so a renderer can
                            measure text the way the reference did.

The assets are *derived from the committed reference documents* and are rebuilt
on demand; they are not committed (see .gitignore).

Usage::

    uv run python tools/build_fonts.py            # build + install
    uv run python tools/build_fonts.py --no-install
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ASSETS = ROOT / "src" / "sars" / "assets" / "fonts"
UPSTREAM = ASSETS / "upstream"
INSTALL_DIR = Path.home() / ".local" / "share" / "fonts" / "sars"
MANIFEST = ASSETS / "manifest.json"

#: MuPDF's base-14 substitutes for the fonts the Microsoft output does not
#: embed. The URW Nimbus files were verified byte-identical in rendering to
#: PyMuPDF's built-ins (see docs/FIDELITY_NOTES.md).
NIMBUS_SOURCES: dict[str, tuple[str, str]] = {
    "helv": ("NimbusSans-Regular.otf", "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusSans-Regular.otf"),
    "hebo": ("NimbusSans-Bold.otf", "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusSans-Bold.otf"),
    "tiro": ("NimbusRoman-Regular.otf", "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusRoman-Regular.otf"),
    "tibo": ("NimbusRoman-Bold.otf", "https://raw.githubusercontent.com/ArtifexSoftware/urw-base35-fonts/master/fonts/NimbusRoman-Bold.otf"),
}

#: Which base-14 face MuPDF substitutes for a named, non-embedded font.
SUBSTITUTES: dict[str, str] = {
    "ArialMT": "helv",
    "Arial": "helv",
    "Helvetica": "helv",
    "Arial-BoldMT": "hebo",
    "Arial,Bold": "hebo",
    "Helvetica-Bold": "hebo",
    "TimesNewRomanPSMT": "tiro",
    "TimesNewRoman": "tiro",
    "TimesNewRomanPS-BoldMT": "tibo",
    "TimesNewRomanPS-BoldItalicMT": "tibo",
}

#: Roles a renderer can ask for, derived from the reference font's PostScript
#: name. The role is what a template names; the manifest resolves it to the CSS
#: family of the asset that reproduces it for THAT report.
ROLES: dict[str, str] = {
    "ArialMT": "arial",
    "Arial": "arial",
    "Arial-BoldMT": "arial-bold",
    "TimesNewRomanPSMT": "times",
    "TimesNewRomanPS-BoldMT": "times-bold",
    "ArialNarrow-Bold": "arial-narrow-bold",
    "ArialNarrow": "arial-narrow",
    "Tahoma-Bold": "tahoma-bold",
    "Tahoma": "tahoma",
    "Calibri": "calibri",
    "Calibri-Bold": "calibri-bold",
}


def strip_subset_tag(name: str) -> str:
    """``BCDEEE+ArialNarrow-Bold`` -> ``ArialNarrow-Bold``."""
    return name.split("+", 1)[1] if "+" in name and len(name.split("+", 1)[0]) == 6 else name


@dataclass
class FontUse:
    """One font as used by one reference PDF."""

    pdf_name: str          # /BaseFont as written in the PDF
    psname: str            # subset tag stripped
    embedded: bool
    buffer: bytes | None
    widths: dict[int, float]            # PDF advance widths, per 1000 units
    widths_key: str                     # "code" (WinAnsi codepoint) or "gid"
    observed: dict[int, int] = field(default_factory=dict)  # unicode -> glyph id
    #: Advances measured from the reference's own glyph positions, per 1000 em
    #: units: ``unicode -> [observation, ...]``. These are the ground truth for
    #: how wide the reference actually stepped, which a ``/Widths`` array does not
    #: always tell you - a document can carry several font objects for the same
    #: face with different width arrays, and text inside a run then walks out of
    #: position by up to a point by the end of a long cell.
    measured: dict[int, list[float]] = field(default_factory=dict)


def _obj_value(doc: pymupdf.Document, xref: int, key: str) -> str:
    value = doc.xref_get_key(xref, key)
    return value[1] if value and value[0] != "null" else ""


def _parse_number_list(text: str) -> list[float]:
    out: list[float] = []
    for token in text.replace("[", " ").replace("]", " ").split():
        try:
            out.append(float(token))
        except ValueError:
            pass
    return out


def _simple_widths(doc: pymupdf.Document, xref: int) -> dict[int, float]:
    first = _obj_value(doc, xref, "FirstChar")
    widths = _obj_value(doc, xref, "Widths")
    if not first or not widths:
        return {}
    if widths.strip().endswith("R"):  # indirect array
        ref = int(widths.split()[0])
        widths = doc.xref_object(ref)
    values = _parse_number_list(widths)
    start = int(float(first))
    return {start + i: v for i, v in enumerate(values)}


def _cid_widths(doc: pymupdf.Document, xref: int) -> dict[int, float]:
    desc = _obj_value(doc, xref, "DescendantFonts")
    if not desc:
        return {}
    if desc.strip().endswith("R"):
        desc_xref = int(desc.split()[0])
        w_text = _obj_value(doc, desc_xref, "W")
    else:
        # inline array: [ << ... >> ]
        inner = desc
        w_text = ""
        marker = inner.find("/W")
        if marker >= 0:
            w_text = inner[marker + 2 :]
    if not w_text:
        # The descendant may itself be an inline dict reachable via /W below it.
        return {}
    if w_text.strip().startswith("[") is False and w_text.strip().endswith("R"):
        w_text = doc.xref_object(int(w_text.split()[0]))
    return _parse_cid_w(w_text)


def _parse_cid_w(text: str) -> dict[int, float]:
    tokens: list[str] = []
    buf = ""
    depth = 0
    for ch in text:
        if ch == "[":
            depth += 1
            if depth > 1:
                tokens.append("[")
            if buf.strip():
                tokens.append(buf.strip())
            buf = ""
            continue
        if ch == "]":
            if buf.strip():
                tokens.append(buf.strip())
            buf = ""
            depth -= 1
            if depth >= 1:
                tokens.append("]")
            if depth <= 0:
                break
            continue
        if ch in " \r\n\t":
            if buf.strip():
                tokens.append(buf.strip())
            buf = ""
            continue
        buf += ch
    if buf.strip():
        tokens.append(buf.strip())

    out: dict[int, float] = {}
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in "[]":
            i += 1
            continue
        try:
            start = int(float(token))
        except ValueError:
            i += 1
            continue
        i += 1
        if i < len(tokens) and tokens[i] == "[":
            i += 1
            cid = start
            while i < len(tokens) and tokens[i] != "]":
                try:
                    out[cid] = float(tokens[i])
                except ValueError:
                    pass
                cid += 1
                i += 1
            i += 1
        elif i + 1 < len(tokens):
            end = int(float(tokens[i]))
            width = float(tokens[i + 1])
            i += 2
            for cid in range(start, min(end, start + 65535) + 1):
                out[cid] = width
    return out


def collect_uses(pdf: Path) -> dict[str, FontUse]:
    """All fonts a reference PDF uses, with widths and observed glyph ids."""
    uses: dict[str, FontUse] = {}
    with pymupdf.open(pdf) as doc:
        seen_xref: set[int] = set()
        for pno in range(doc.page_count):
            for xref, ext, subtype, basefont, _name, _enc in doc.get_page_fonts(pno):
                if xref in seen_xref:
                    continue
                seen_xref.add(xref)
                psname = strip_subset_tag(basefont)
                buffer = None
                if ext != "n/a":
                    buffer = doc.extract_font(xref)[3] or None
                # Widths are only *overridden* for the fonts MuPDF substitutes:
                # there the advances come from the PDF, not from the substitute
                # face. For the embedded fonts the PDF's /W array was verified
                # to agree with the font's own hmtx on every reference document
                # (see docs/FIDELITY_NOTES.md), so the file is used untouched.
                if buffer is not None and subtype == "Type0":
                    widths, key = {}, "gid"
                elif buffer is not None:
                    widths, key = {}, "code"
                elif subtype == "Type0":
                    widths, key = _cid_widths(doc, xref), "gid"
                else:
                    widths, key = _simple_widths(doc, xref), "code"
                uses[basefont] = FontUse(
                    pdf_name=basefont,
                    psname=psname,
                    embedded=buffer is not None,
                    buffer=buffer,
                    widths=widths,
                    widths_key=key,
                )
        for pno in range(doc.page_count):
            for span in doc[pno].get_texttrace():
                if span["type"] not in (0, 2):
                    continue
                use = uses.get(span["font"]) or uses.get(strip_subset_tag(span["font"]))
                if use is None:
                    continue
                size = span["size"]
                horizontal = abs(span["dir"][1]) < 0.5
                previous: tuple | None = None
                for char in span["chars"]:
                    use.observed[char[0]] = char[1]
                    if horizontal and previous is not None and size > 0:
                        step = (char[2][0] - previous[2][0]) / size
                        # Only consecutive glyphs of one run: a repositioning
                        # between cells is not an advance.
                        if 0.05 <= step <= 2.0:
                            use.measured.setdefault(previous[0], []).append(step * 1000)
                    previous = char
    return uses


def _font_from(use: FontUse) -> tuple[TTFont, bytes, str]:
    """The TTFont that MuPDF effectively draws for this reference font."""
    if use.embedded and use.buffer:
        return TTFont(io.BytesIO(use.buffer)), use.buffer, "embedded"
    code = SUBSTITUTES.get(use.psname)
    if code is None:
        code = "hebo" if "bold" in use.psname.lower() else "helv"
    filename, url = NIMBUS_SOURCES[code]
    path = UPSTREAM / filename
    if not path.exists():
        UPSTREAM.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sfL", "-o", str(path), url], check=True)
    data = path.read_bytes()
    return TTFont(io.BytesIO(data)), data, f"nimbus:{code}"


def _apply_widths(font: TTFont, use: FontUse) -> int:
    """Set the font's advances to the ones the reference actually stepped.

    Measured advances (from consecutive glyph origins in the reference) win over
    the ``/Widths`` array, because they are what MuPDF will draw: a document can
    declare several width arrays for one face, and a run then drifts inside a
    cell even though it starts in exactly the right place. ``/Widths`` fills in
    any character never seen twice in a row.
    """
    upem = font["head"].unitsPerEm
    order = font.getGlyphOrder()
    cmap = font.getBestCmap() or {}
    hmtx = font["hmtx"]

    targets: dict[int, float] = dict(use.widths)
    for code, samples in use.measured.items():
        if not samples:
            continue
        targets[code] = statistics.median(samples)

    changed = 0
    for key, width in targets.items():
        target = round(width * upem / 1000)
        glyph = None
        if use.widths_key == "gid" and key in use.observed:
            gid = use.observed[key]
            glyph = order[gid] if gid < len(order) else None
        if glyph is None:
            # WinAnsi code == unicode over the ranges these reports use.
            glyph = cmap.get(key)
        if glyph is None and use.widths_key == "gid":
            glyph = order[key] if key < len(order) else None
        if glyph is None or glyph not in hmtx.metrics:
            continue
        advance, lsb = hmtx[glyph]
        if advance != target:
            hmtx[glyph] = (target, lsb)
            changed += 1
    if changed:
        font["hhea"].advanceWidthMax = max(a for a, _ in hmtx.metrics.values())
    return changed


def _ensure_cmap(font: TTFont, use: FontUse) -> int:
    """Make sure every character the reference used is reachable by unicode."""
    order = font.getGlyphOrder()
    added = 0
    tables = [t for t in font["cmap"].tables if t.isUnicode()]
    if not tables:
        return 0
    for ucs, gid in use.observed.items():
        glyph = order[gid] if gid < len(order) else None
        if glyph is None:
            continue
        for table in tables:
            if table.cmap.get(ucs) != glyph:
                table.cmap[ucs] = glyph
                added += 1
    return added


def _rename(font: TTFont, family: str, bold: bool) -> None:
    subfamily = "Bold" if bold else "Regular"
    full = f"{family} {subfamily}" if bold else family
    psname = full.replace(" ", "")
    name = font["name"]
    for platform, encoding, language in ((3, 1, 0x409), (1, 0, 0)):
        name.setName(family, 1, platform, encoding, language)
        name.setName(subfamily, 2, platform, encoding, language)
        name.setName(f"{psname}-{abs(hash(family)) % 99999}", 3, platform, encoding, language)
        name.setName(full, 4, platform, encoding, language)
        name.setName(psname, 6, platform, encoding, language)
        name.setName(family, 16, platform, encoding, language)
        name.setName(subfamily, 17, platform, encoding, language)
    os2 = font["OS/2"]
    os2.usWeightClass = 700 if bold else 400
    os2.fsSelection = (os2.fsSelection & ~0x41) | (0x20 if bold else 0x40)
    font["head"].macStyle = (font["head"].macStyle & ~0x3) | (0x1 if bold else 0)



def _real_psname(font: TTFont, fallback: str) -> str:
    """The font's own PostScript name — the truth for an embedded CID subset.

    The region reports name their embedded fonts ``CIDFont+F1…F5``, which says
    nothing; the file inside is real Arial / Arial Bold / Times New Roman Bold /
    Arial Narrow Bold / Calibri, and *that* is the name a renderer needs.
    """
    try:
        name = font["name"].getDebugName(6) or font["name"].getDebugName(4)
    except Exception:  # pragma: no cover - defensive
        name = None
    return (name or fallback).replace(" ", "")


def _is_bold(psname: str, font: TTFont) -> bool:
    lowered = psname.lower()
    if "bold" in lowered or "gras" in lowered:
        return True
    try:
        return bool(font["OS/2"].usWeightClass >= 600)
    except Exception:  # pragma: no cover - defensive
        return False


def build(install: bool = True) -> dict:
    """Build one asset per distinct (face, widths) pair and map reports onto them."""
    from sars import sources

    ASSETS.mkdir(parents=True, exist_ok=True)
    for stale in ASSETS.glob("SARS_*"):
        stale.unlink()

    pairs = sources.discover()

    # --- pass 1: collect every font use, keyed by the face + widths it implies.
    groups: dict[str, dict] = {}
    per_report: dict[str, dict[str, str]] = {}
    by_pdf_font: dict[str, dict[str, str]] = {}
    for pair in pairs:
        uses = collect_uses(pair.pdf)
        per_report[pair.name] = {}
        for pdf_name, use in sorted(uses.items()):
            font, raw, provenance = _font_from(use)
            psname = _real_psname(font, use.psname) if use.embedded else use.psname
            # The key includes the advances measured from this document, because
            # two documents can name the same face and step it differently; a
            # shared asset would then be wrong for one of them.
            measured_signature = json.dumps(
                sorted(
                    (code, round(statistics.median(samples), 1))
                    for code, samples in use.measured.items()
                    if samples
                )
            )
            key = hashlib.sha1(
                raw
                + json.dumps(sorted(use.widths.items())).encode()
                + measured_signature.encode()
            ).hexdigest()[:10]
            group = groups.setdefault(
                key,
                {
                    "psname": psname,
                    "provenance": provenance,
                    "raw": raw,
                    "widths": use.widths,
                    "widths_key": use.widths_key,
                    "observed": {},
                    "measured": {},
                    "bold": _is_bold(psname, font),
                    "reports": [],
                },
            )
            group["observed"].update(use.observed)
            for code, samples in use.measured.items():
                group["measured"].setdefault(code, []).extend(samples)
            group["reports"].append(pair.name)
            role = ROLES.get(psname, psname.lower())
            per_report[pair.name][role] = key
            # The name the PDF itself uses, so a tool replaying the reference's
            # own text runs can resolve the face from ``get_texttrace``.
            # Both the raw /BaseFont and the subset-tag-stripped name, because
            # ``get_page_fonts`` reports ``BCDEEE+ArialNarrow-Bold`` while
            # ``get_texttrace`` reports ``ArialNarrow-Bold``.
            by_pdf_font.setdefault(pair.name, {})[pdf_name] = key
            by_pdf_font[pair.name].setdefault(strip_subset_tag(pdf_name), key)
            by_pdf_font[pair.name].setdefault(psname, key)

    # --- pass 2: build each asset once, with the union of observed characters.
    manifest: dict[str, dict] = {"assets": {}, "reports": {}}
    for key, group in sorted(groups.items()):
        font = TTFont(io.BytesIO(group["raw"]))
        use = FontUse(
            pdf_name=group["psname"],
            psname=group["psname"],
            embedded=group["provenance"] == "embedded",
            buffer=None,
            widths=group["widths"],
            widths_key=group["widths_key"],
            observed=group["observed"],
            measured=group["measured"],
        )
        overrides = _apply_widths(font, use)
        cmap_adds = _ensure_cmap(font, use)
        family = f"SARS {group['psname'].replace(',', '-')} {key}"
        _rename(font, family, group["bold"])
        suffix = ".otf" if font.sfntVersion == "OTTO" else ".ttf"
        out = ASSETS / f"{family.replace(' ', '_')}{suffix}"
        font.save(out)

        upem = font["head"].unitsPerEm
        order = font.getGlyphOrder()
        metrics = font["hmtx"].metrics
        advances = {}
        for ucs, gid in sorted(group["observed"].items()):
            glyph = order[gid] if gid < len(order) else None
            if glyph in metrics:
                advances[str(ucs)] = round(metrics[glyph][0] * 1000 / upem, 4)
        manifest["assets"][key] = {
            "family": family,
            "file": out.name,
            "psname": group["psname"],
            "bold": group["bold"],
            "provenance": group["provenance"],
            "upem": upem,
            "width_overrides": overrides,
            "cmap_additions": cmap_adds,
            "ascender": font["hhea"].ascender / upem,
            "descender": font["hhea"].descender / upem,
            "os2_typo_ascender": font["OS/2"].sTypoAscender / upem,
            "os2_typo_descender": font["OS/2"].sTypoDescender / upem,
            "advances": advances,
            "used_by": sorted(set(group["reports"])),
        }
        print(
            f"{family:52s} {group['provenance']:14s} "
            f"widths_overridden={overrides:4d} cmap_added={cmap_adds:3d} "
            f"chars={len(advances):3d} reports={len(set(group['reports']))}"
        )

    for name, roles in per_report.items():
        manifest["reports"][name] = {
            role: {
                "asset": key,
                "family": manifest["assets"][key]["family"],
                "bold": manifest["assets"][key]["bold"],
            }
            for role, key in sorted(roles.items())
        }
    manifest["by_pdf_font"] = {
        name: {
            pdf_font: {"asset": key, "family": manifest["assets"][key]["family"]}
            for pdf_font, key in sorted(mapping.items())
        }
        for name, mapping in sorted(by_pdf_font.items())
    }

    MANIFEST.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"\n{len(manifest['assets'])} font asset(s) -> {ASSETS.relative_to(ROOT)}")
    print("roles per report:")
    for name, roles in sorted(manifest["reports"].items()):
        print(f"    {name}: " + ", ".join(sorted(roles)))

    if install:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        for old in INSTALL_DIR.glob("*"):
            old.unlink()
        for asset in manifest["assets"].values():
            shutil.copy2(ASSETS / asset["file"], INSTALL_DIR / asset["file"])
        subprocess.run(
            ["fc-cache", "-f", str(INSTALL_DIR)], check=False, stdout=subprocess.DEVNULL
        )
        print(f"installed -> {INSTALL_DIR}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-install", action="store_true", help="build assets only")
    args = parser.parse_args()
    build(install=not args.no_install)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
