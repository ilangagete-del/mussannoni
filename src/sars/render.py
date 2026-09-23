"""Print the generated pure HTML + CSS to A4 PDFs with WeasyPrint."""

from __future__ import annotations

from pathlib import Path

from weasyprint import HTML


def render_html(html_path: Path, out_dir: Path) -> Path:
    """Render one clean HTML document to an A4 PDF."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{html_path.stem}.pdf"
    HTML(filename=str(html_path), base_url=str(html_path.parent)).write_pdf(str(target))
    return target
