"""Unpack ``sars.zip`` into ``data/sars/``.

The archive is the single source of truth in the repository; the extracted tree
is a build artefact, so it is reproduced here rather than committed twice.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .sources import DATA, ROOT

ARCHIVE = ROOT / "sars.zip"
NESTED = ("council_html", "council_pdf", "region_html", "region_pdf")


def _flatten(directory: Path) -> None:
    """Lift a single nested directory's contents up one level."""
    inner = [p for p in directory.iterdir() if p.is_dir()]
    if len(inner) != 1:
        return
    for item in inner[0].iterdir():
        shutil.move(str(item), str(directory / item.name))
    inner[0].rmdir()


def unpack(force: bool = False) -> Path:
    """Extract the archive (and its nested archives) into ``data/sars``."""
    if not ARCHIVE.exists():
        raise SystemExit(f"archive not found: {ARCHIVE}")

    if DATA.exists() and not force:
        return DATA
    if DATA.exists():
        shutil.rmtree(DATA)

    target = DATA.parent
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE) as zf:
        zf.extractall(target)

    for name in NESTED:
        inner_zip = DATA / f"{name}.zip"
        if not inner_zip.exists():
            continue
        out = DATA / name
        out.mkdir(exist_ok=True)
        with zipfile.ZipFile(inner_zip) as zf:
            zf.extractall(out)
        _flatten(out)
        inner_zip.unlink()

    return DATA
