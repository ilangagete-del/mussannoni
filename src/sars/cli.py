"""Command line entry point: convert / render / verify / all."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import sources
from .classify import classify
from .extract import extract_document
from .html_out import write_document
from .render import render_html
from .unpack import unpack
from .verify import verify


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sars",
        description="Convert Mwanza SARS reports to pure HTML+CSS and print to A4.",
    )
    parser.add_argument(
        "command",
        choices=["unpack", "convert", "render", "verify", "all", "list"],
        help="action",
    )
    parser.add_argument("--only", help="substring of a document name")
    parser.add_argument("--force", action="store_true", help="re-extract even if data/sars exists")
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
    rc = cmd_convert(args.only)
    rc = cmd_render(args.only) or rc
    return cmd_verify(args.only) or rc


if __name__ == "__main__":
    raise SystemExit(main())
