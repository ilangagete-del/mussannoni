"""Make the bundled reference faces available to the renderer, or fail loudly.

This project permits **no fallback font**. That is not a stylistic preference: the
reference documents embed real Arial / Times New Roman / Arial Narrow / Calibri
(and name URW Nimbus), and every x position in a rendered report is computed from
*those* faces' advance widths. With the faces missing, WeasyPrint does not fail —
it quietly substitutes whatever it can find and still produces a plausible PDF.
Measured, that substitution costs about twelve points of fidelity: every report
drops from ~99% to ~87% visible match with ``max_delta 255``. A silent near-miss
is the worst failure mode this project has, so absence is made loud here.

WeasyPrint finds fonts through fontconfig, which searches directories rather than
accepting a file path per face. So the bundled faces are registered by copying
them into the user font directory and refreshing the fontconfig cache — once,
idempotently:

    >>> from sars import fontsetup
    >>> fontsetup.ensure()          # no-op when already registered

:func:`verify` is the check on its own: it asks fontconfig whether every family
the manifest names is actually resolvable, and reports the ones that are not.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from . import fonts

#: Where the faces are registered for fontconfig to find them. A user directory,
#: so no privileged install step is ever required.
INSTALL_DIR = Path.home() / ".local" / "share" / "fonts" / "sars"


class FontsUnavailable(RuntimeError):
    """Raised when a face the reference needs cannot be resolved.

    Never caught internally to substitute something else — that would be a
    fallback font, which this project does not allow.
    """


def bundled() -> dict[str, Path]:
    """Every bundled face, ``css family name -> file``, from the manifest."""
    manifest = fonts.manifest()
    out: dict[str, Path] = {}
    for record in manifest["assets"].values():
        path = fonts.ASSETS / record["file"]
        if path.exists():
            out[record["family"]] = path
    return out


def _fc_families() -> set[str]:
    """Families fontconfig can currently resolve."""
    try:
        done = subprocess.run(
            ["fc-list", ":", "family"], capture_output=True, text=True, check=False, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    found: set[str] = set()
    for line in done.stdout.splitlines():
        for name in line.split(","):
            # fc-list escapes '-' in family names.
            found.add(name.strip().replace("\\-", "-"))
    return found


def missing() -> list[str]:
    """Bundled families that fontconfig cannot resolve right now."""
    available = _fc_families()
    if not available:
        # No fontconfig at all: everything is effectively missing, and saying so
        # is more useful than reporting success.
        return sorted(bundled())
    return sorted(family for family in bundled() if family not in available)


def install(force: bool = False) -> int:
    """Copy the bundled faces into the user font directory and refresh the cache.

    Returns how many files were installed. Safe to call repeatedly: a face already
    present with the same size is left alone unless *force* is set.
    """
    faces = bundled()
    if not faces:
        raise FontsUnavailable(
            f"no font files found in {fonts.ASSETS} — the package is incomplete; "
            "rebuild them with `python tools/build_fonts.py`"
        )
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    installed = 0
    for source in faces.values():
        target = INSTALL_DIR / source.name
        if (
            force
            or not target.exists()
            or target.stat().st_size != source.stat().st_size
        ):
            shutil.copy2(source, target)
            installed += 1
    if installed:
        try:
            subprocess.run(
                ["fc-cache", "-f", str(INSTALL_DIR)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError):  # pragma: no cover
            pass
        _ensured.cache_clear()
    return installed


def verify() -> None:
    """Raise :class:`FontsUnavailable` unless every bundled face is resolvable."""
    absent = missing()
    if absent:
        raise FontsUnavailable(
            f"{len(absent)} reference font family(ies) are not available to the "
            f"renderer, so a report would be drawn in a substitute face and would "
            f"NOT match the original. This project uses no fallback font.\n"
            f"Fix: python -c 'from sars import fontsetup; fontsetup.install()'  "
            f"(or `sars fonts install`).\n"
            f"First missing: {', '.join(absent[:3])}"
            + (f" (+{len(absent) - 3} more)" if len(absent) > 3 else "")
        )


@lru_cache(maxsize=1)
def _ensured() -> bool:
    if missing():
        install()
    verify()
    return True


def ensure() -> None:
    """Register the bundled faces if they are not already, then verify.

    Cached, so the public API can call it before every render without cost.
    """
    _ensured()
