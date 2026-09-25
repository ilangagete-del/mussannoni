"""Command line entry point: convert / render / verify / all."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import schema, sources, template_maker
from .classify import classify
from .extract import extract_document
from .extract_data import extract_report
from .html_out import write_document
from .render import render_html
from .unpack import unpack
from .verify import verify

OUT_DATA = sources.ROOT / "output" / "data"
OUT_TEMPLATE_HTML = sources.ROOT / "output" / "template_html"
OUT_TEMPLATE_PDF = sources.ROOT / "output" / "template_pdf"


def _convert_one(pair: sources.SourcePair) -> tuple[Path, str]:
    doc = extract_document(pair.pdf, pair.html)
    for page in doc.pages:
        for block in page.blocks:
            if block.table is not None:
                classify(block.table)
    path = write_document(doc, sources.OUT_HTML)
    return path, doc.orientation


def cmd_convert(only: str | None) -> int:
    for pair in sources.select(only):
        path, orientation = _convert_one(pair)
        size = path.stat().st_size
        src = pair.html.stat().st_size
        print(
            f"convert  {pair.name}\n"
            f"         {orientation:9s} {src / 1024:9.1f} KiB -> {size / 1024:8.1f} KiB"
            f"  ({size / src * 100:.1f}% of source)"
        )
    return 0


def cmd_render(only: str | None) -> int:
    for pair in sources.select(only):
        html_path = sources.OUT_HTML / f"{pair.name}.html"
        if not html_path.exists():
            print(f"render   {pair.name}: SKIP (no clean HTML; run convert)", file=sys.stderr)
            continue
        pdf = render_html(html_path, sources.OUT_PDF)
        print(f"render   {pair.name} -> {pdf.relative_to(sources.ROOT)}")
    return 0


def cmd_verify(only: str | None) -> int:
    results = []
    for pair in sources.select(only):
        generated = sources.OUT_PDF / f"{pair.name}.pdf"
        if not generated.exists():
            print(f"verify   {pair.name}: SKIP (no output PDF; run render)", file=sys.stderr)
            continue
        import pymupdf

        ref = pymupdf.open(pair.pdf)
        orientation = "landscape" if ref[0].rect.width > ref[0].rect.height else "portrait"
        ref.close()
        res = verify(pair.pdf, generated, orientation)
        results.append(res)
        print(res.line())

    if results:
        passed = sum(1 for r in results if r.ok)
        mean = sum(r.similarity for r in results) / len(results)
        print(
            f"\nsummary  {passed}/{len(results)} documents pass; "
            f"mean text similarity {mean * 100:.2f}%"
        )
        return 0 if passed == len(results) else 1
    return 0


def cmd_data(only: str | None) -> int:
    """Extract structured report data to JSON under output/data/."""
    OUT_DATA.mkdir(parents=True, exist_ok=True)
    for pair in sources.select(only):
        doc = extract_document(pair.pdf, pair.html)
        report = extract_report(doc, pair.name)
        text = schema.to_json(report)
        out = OUT_DATA / f"{pair.name}.json"
        out.write_text(text, encoding="utf-8")
        if only:
            print(text)
        else:
            print(f"data     {pair.name} -> {out.relative_to(sources.ROOT)}")
    return 0


def _template_one(name: str) -> tuple[str, str, str, str]:
    """Extract one document and write its templated HTML + PDF.

    Module level and named only by its document name, so it can be handed to a
    worker process. Returns what the caller needs to print, because a worker's
    stdout is not the user's terminal.
    """
    pair = next(p for p in sources.discover() if p.name == name)
    doc = extract_document(pair.pdf, pair.html)
    report = extract_report(doc, pair.name)
    report_type = getattr(report.meta, "report_type", "generic")

    html_text = template_maker.render_html(report_type, report)
    html_path = OUT_TEMPLATE_HTML / f"{pair.name}.html"
    html_path.write_text(html_text, encoding="utf-8")

    pdf_path = template_maker.render_pdf(
        report_type, report, OUT_TEMPLATE_PDF / f"{pair.name}.pdf"
    )
    return (
        pair.name,
        report_type,
        str(html_path.relative_to(sources.ROOT)),
        str(Path(pdf_path).relative_to(sources.ROOT)),
    )


def cmd_template(only: str | None, jobs: int | None = None) -> int:
    """Run the data -> template -> HTML/PDF path for each selected document.

    This exercises the template-maker API end to end: the document's data is
    extracted to a schema instance, handed to the template registered for its
    report type, and the resulting HTML is written to ``output/template_html/``
    and printed to a PDF in ``output/template_pdf/``. Unlike ``convert``, which
    redraws a specific PDF, this path rebuilds the report *from data alone*.

    Documents are independent, and printing one is dominated by the PDF engine —
    roughly 84% of the work — so they are rendered in parallel across processes.
    The result is byte-for-byte what a sequential run produces; only the wall
    clock changes. ``jobs=1`` forces the sequential path.
    """
    OUT_TEMPLATE_HTML.mkdir(parents=True, exist_ok=True)
    OUT_TEMPLATE_PDF.mkdir(parents=True, exist_ok=True)
    names = [pair.name for pair in sources.select(only)]
    if not names:
        return 0

    workers = _worker_count(jobs, len(names))

    def report(result: tuple[str, str, str, str]) -> None:
        name, report_type, html_path, pdf_path = result
        print(f"template {name}\n         {report_type:22s} -> {html_path} + {pdf_path}")

    if workers == 1:
        for name in names:
            report(_template_one(name))
        return 0

    import concurrent.futures as futures

    # The longest documents first, so the slowest one is never the last thing
    # left running while the other workers sit idle.
    ordered = sorted(names, key=lambda n: -_source_size(n))
    with futures.ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(_template_one, name): name for name in ordered}
        failures = 0
        for future in futures.as_completed(pending):
            name = pending[future]
            try:
                report(future.result())
            except Exception as error:  # noqa: BLE001 - report and keep going
                failures += 1
                print(f"template {name}\n         FAILED: {error!r}", file=sys.stderr)
    return 1 if failures else 0


def _worker_count(jobs: int | None, tasks: int) -> int:
    import os

    if jobs is not None and jobs > 0:
        return min(jobs, tasks)
    available = os.process_cpu_count() if hasattr(os, "process_cpu_count") else os.cpu_count()
    return max(1, min(available or 1, tasks))


def _source_size(name: str) -> int:
    """A cheap proxy for how long a document takes: how big its source PDF is."""
    pair = next((p for p in sources.discover() if p.name == name), None)
    try:
        return pair.pdf.stat().st_size if pair else 0
    except OSError:
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sars",
        description="Convert Mwanza SARS reports to pure HTML+CSS and print to A4.",
    )
    parser.add_argument(
        "command",
        choices=["unpack", "convert", "render", "verify", "all", "list", "data", "template"],
        help="action",
    )
    parser.add_argument("--only", help="substring of a document name")
    parser.add_argument("--force", action="store_true", help="re-extract even if data/sars exists")
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="parallel worker processes for `template` (default: one per CPU; 1 = sequential)",
    )
    args = parser.parse_args(argv)

    if args.command == "unpack":
        print(f"unpack   -> {unpack(force=args.force)}")
        return 0

    # every other command needs the source data present
    unpack()

    if args.command == "list":
        for pair in sources.select(args.only):
            print(f"{pair.group:8s} {pair.name}")
        return 0
    if args.command == "convert":
        return cmd_convert(args.only)
    if args.command == "render":
        return cmd_render(args.only)
    if args.command == "verify":
        return cmd_verify(args.only)
    if args.command == "data":
        return cmd_data(args.only)
    if args.command == "template":
        return cmd_template(args.only, jobs=args.jobs)
    rc = cmd_convert(args.only)
    rc = cmd_render(args.only) or rc
    return cmd_verify(args.only) or rc


if __name__ == "__main__":
    raise SystemExit(main())
