"""Print HTML to PDF through either WeasyPrint or Chromium.

Two engines, because they are wrong in different places and the reference decides
which one wins:

* **WeasyPrint** — the project's original engine. Pure Python, exact control of
  the page box, places text from the font's own advances.
* **Chromium** — headless Chrome's print-to-PDF. A different layout engine and a
  different text-placement path, so where WeasyPrint rounds or hints a fraction
  of a point differently from the reference, Chromium may not (and vice versa).

Nothing here decides which engine a report uses: ``tools/engine_bakeoff.py``
measures both against the reference with the fidelity gate and records the winner
per report in ``assets/engine_choice.json``, which :func:`engine_for` reads. That
keeps the choice evidence-based rather than a guess.

Both engines are driven from the same HTML, so a report's HTML+CSS remains the
single artefact and nothing engine-specific leaks into a template — except the
baseline calibration in :mod:`sars.fonts`, which is measured per engine because
the two compute a line box's half-leading differently.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHOICE_PATH = ROOT / "assets" / "engine_choice.json"

ENGINES = ("weasyprint", "chromium")

#: Chromium binaries to try, in order.
_CHROME_CANDIDATES = ("chrome", "chromium", "chromium-browser", "google-chrome")


@lru_cache(maxsize=1)
def chromium_binary() -> str | None:
    for name in _CHROME_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def available_engines() -> tuple[str, ...]:
    return tuple(e for e in ENGINES if e != "chromium" or chromium_binary())


@lru_cache(maxsize=1)
def _choices() -> dict:
    if CHOICE_PATH.exists():
        return json.loads(CHOICE_PATH.read_text(encoding="utf-8"))
    return {}


def engine_for(report: str, default: str = "weasyprint") -> str:
    """The engine measured to reproduce *report* best (see the bake-off tool)."""
    choice = _choices().get(report, {})
    engine = choice.get("engine", default) if isinstance(choice, dict) else str(choice)
    if engine == "chromium" and not chromium_binary():
        return "weasyprint"
    return engine


def record_choice(report: str, engine: str, evidence: dict | None = None) -> None:
    """Persist the measured engine choice for a report."""
    data = dict(_choices())
    data[report] = {"engine": engine, **(evidence or {})}
    CHOICE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHOICE_PATH.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    _choices.cache_clear()


def _weasyprint(html_text: str, base_url: str | None) -> bytes:
    from weasyprint import HTML

    return HTML(string=html_text, base_url=base_url or tempfile.gettempdir()).write_pdf()


def _chromium(html_text: str, base_url: str | None) -> bytes:
    binary = chromium_binary()
    if binary is None:  # pragma: no cover - environment dependent
        raise RuntimeError("chromium is not available in this environment")
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        source = directory / "page.html"
        source.write_text(html_text, encoding="utf-8")
        target = directory / "out.pdf"
        subprocess.run(
            [
                binary,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                "--no-pdf-header-footer",
                "--disable-lcd-text",
                "--font-render-hinting=none",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=20000",
                f"--print-to-pdf={target}",
                source.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
        )
        return target.read_bytes()


def print_pdf(
    html_text: str,
    out_path: str | Path | None = None,
    *,
    engine: str = "weasyprint",
    base_url: str | None = None,
) -> bytes | Path:
    """Print *html_text* to PDF with *engine*; return the bytes or the path written."""
    if engine not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; expected one of {ENGINES}")
    if engine == "weasyprint":
        data = _weasyprint(html_text, base_url)
    else:
        data = _chromium(html_text, base_url)
    if out_path is None:
        return data
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target
