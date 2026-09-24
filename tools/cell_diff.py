"""Cell-by-cell comparison of a generated PDF against its reference.

Token-multiset verification (``sars verify``) proves no text was lost, but it is
blind to *where* a value landed and to what colour its cell was painted. This
tool compares the two documents **cell by cell** on the logical row/column
lattice, reporting three classes of defect per table:

``text``        a cell whose text differs from the reference's cell at the same
                (row, col);
``background``  a cell whose fill colour differs - the shading washes and the
                competency bands;
``shape``       a table whose row/column count or a cell's rowspan/colspan
                differs, which is what makes text spill out of its box.

Both PDFs are read with the same recovery the pipeline uses
(:func:`sars.extract.extract_document`), so the comparison is of like with like
and is independent of the page size difference (Letter reference vs A4 output).

Usage::

    python tools/cell_diff.py "MWANZA CC SCHOOLS RANK"     # one document
    python tools/cell_diff.py "MWANZA CC SCHOOLS RANK" -v  # list every mismatch
    python tools/cell_diff.py                              # every document
    python tools/cell_diff.py --template                   # vs templated output
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from sars import sources  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.model import Document, Table  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

#: Render scale for the per-cell colour sampling.
ZOOM = 2.0


def _norm(text: str) -> str:
    """Collapse whitespace so only real text differences register."""
    return " ".join((text or "").split())


class Sampler:
    """Samples the colour actually painted inside a cell, from the rendered page.

    The recovered ``Cell.style.background`` cannot be compared directly between
    two documents: the extractor's panel heuristic treats a wide band drawn
    behind a header row as a page *panel* and reports those cells as unpainted,
    while the same band re-emitted as per-cell fills is reported truthfully. The
    comparison would then flag a difference where the two pages look identical.

    Sampling the rasterised page removes that asymmetry, and because each cell is
    sampled using *its own* geometry the result is also independent of the page
    size difference (a US-Letter reference against A4 output).
    """

    def __init__(self, pdf: Path) -> None:
        self._doc = pymupdf.open(pdf)
        self._cache: dict[int, Image.Image] = {}

    def _page(self, index: int) -> Image.Image:
        if index not in self._cache:
            page = self._doc[index]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(ZOOM, ZOOM))
            self._cache[index] = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return self._cache[index]

    def background(self, page_index: int, bbox: tuple[float, float, float, float]) -> str:
        """The dominant colour inside *bbox*, as ``#rrggbb``.

        A grid of interior points is sampled and the most common colour wins, so
        the glyphs and the ruled border do not outvote the fill behind them.
        """
        img = self._page(page_index)
        x0, y0, x1, y1 = (v * ZOOM for v in bbox)
        # Inset past the border so the rule is never sampled.
        x0, y0, x1, y1 = x0 + 2, y0 + 2, x1 - 2, y1 - 2
        if x1 <= x0 or y1 <= y0:
            return "#ffffff"
        counts: dict[tuple[int, int, int], int] = {}
        steps = 5
        for i in range(steps):
            for j in range(steps):
                px = int(x0 + (x1 - x0) * (i + 0.5) / steps)
                py = int(y0 + (y1 - y0) * (j + 0.5) / steps)
                if not (0 <= px < img.width and 0 <= py < img.height):
                    continue
                rgb = img.getpixel((px, py))
                counts[rgb] = counts.get(rgb, 0) + 1
        if not counts:
            return "#ffffff"
        r, g, b = max(counts.items(), key=lambda kv: kv[1])[0]
        return f"#{r:02x}{g:02x}{b:02x}"

    def close(self) -> None:
        self._doc.close()


def _close(a: str, b: str, tol: int = 24) -> bool:
    """True when two ``#rrggbb`` colours are visually the same.

    A tolerance absorbs JPEG-free but still lossy rasterisation differences and
    the sub-percent colour drift between a PDF fill and its re-emission.
    """
    try:
        ra, ga, ba = (int(a[i : i + 2], 16) for i in (1, 3, 5))
        rb, gb, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return a == b
    return max(abs(ra - rb), abs(ga - gb), abs(ba - bb)) <= tol


@dataclass
class TableDiff:
    index: int
    ref_shape: tuple[int, int]
    out_shape: tuple[int, int]
    text: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    span: list[str] = field(default_factory=list)

    @property
    def shape_ok(self) -> bool:
        return self.ref_shape == self.out_shape

    @property
    def total(self) -> int:
        return len(self.text) + len(self.background) + len(self.span)


def _tables(doc: Document) -> list[tuple[int, Table]]:
    """Every table with the zero-based index of the page it sits on."""
    return [
        (pi, b.table) for pi, p in enumerate(doc.pages) for b in p.blocks if b.table is not None
    ]


def _bbox(table: Table, cell) -> tuple[float, float, float, float] | None:
    """The cell's rectangle on the page, from the table's own lattice."""
    cols, rows = table.col_edges, table.row_edges
    c1 = cell.col + cell.colspan
    r1 = cell.row + cell.rowspan
    if cell.col >= len(cols) or c1 >= len(cols) or cell.row >= len(rows) or r1 >= len(rows):
        return None
    return (cols[cell.col], rows[cell.row], cols[c1], rows[r1])


def compare_tables(
    ref: Table,
    out: Table,
    index: int,
    ref_page: int = 0,
    out_page: int = 0,
    ref_s: Sampler | None = None,
    out_s: Sampler | None = None,
) -> TableDiff:
    """Compare two tables cell by cell on their logical lattice."""
    diff = TableDiff(
        index=index,
        ref_shape=(ref.n_rows, ref.n_cols),
        out_shape=(out.n_rows, out.n_cols),
    )
    ref_cells = {(c.row, c.col): c for c in ref.cells}
    out_cells = {(c.row, c.col): c for c in out.cells}

    for key in sorted(set(ref_cells) | set(out_cells)):
        rc = ref_cells.get(key)
        oc = out_cells.get(key)
        where = f"r{key[0]}c{key[1]}"

        if rc is None:
            if oc is not None and _norm(oc.text):
                diff.text.append(f"{where}: reference has no cell; output {_norm(oc.text)!r}")
            continue
        if oc is None:
            if _norm(rc.text):
                diff.text.append(f"{where}: missing from output; reference {_norm(rc.text)!r}")
            continue

        if _norm(rc.text) != _norm(oc.text):
            diff.text.append(f"{where}: ref {_norm(rc.text)!r} != out {_norm(oc.text)!r}")

        # Colour is compared from the rendered page, not from the recovered style
        # (see :class:`Sampler`).
        if ref_s is not None and out_s is not None:
            rbb, obb = _bbox(ref, rc), _bbox(out, oc)
            if rbb and obb:
                rb = ref_s.background(ref_page, rbb)
                ob = out_s.background(out_page, obb)
                if not _close(rb, ob):
                    diff.background.append(f"{where}: ref {rb} != out {ob} ({_norm(rc.text)!r})")

        if (rc.rowspan, rc.colspan) != (oc.rowspan, oc.colspan):
            diff.span.append(
                f"{where}: ref span {rc.rowspan}x{rc.colspan} != "
                f"out span {oc.rowspan}x{oc.colspan} ({_norm(rc.text)!r})"
            )

    return diff


def compare_document(name: str, reference: Path, generated: Path, verbose: bool) -> int:
    ref_doc = extract_document(reference, reference)
    out_doc = extract_document(generated, generated)
    ref_tables = _tables(ref_doc)
    out_tables = _tables(out_doc)

    print(f"\n=== {name}")
    print(
        f"    pages ref={len(ref_doc.pages)} out={len(out_doc.pages)}   "
        f"tables ref={len(ref_tables)} out={len(out_tables)}"
    )

    if len(ref_tables) != len(out_tables):
        print(f"    [SHAPE] table count differs: {len(ref_tables)} vs {len(out_tables)}")

    ref_s, out_s = Sampler(reference), Sampler(generated)
    total = 0
    for i, ((rp, rt), (op, ot)) in enumerate(zip(ref_tables, out_tables, strict=False)):
        d = compare_tables(rt, ot, i, ref_page=rp, out_page=op, ref_s=ref_s, out_s=out_s)
        total += d.total
        if not d.shape_ok:
            print(f"    [SHAPE] table {i}: ref {d.ref_shape} != out {d.out_shape}")
        if d.total:
            print(
                f"    table {i}: text={len(d.text)} background={len(d.background)} "
                f"span={len(d.span)}"
            )
            if verbose:
                for line in d.text[:15]:
                    print(f"        TEXT {line}")
                for line in d.background[:15]:
                    print(f"        BG   {line}")
                for line in d.span[:15]:
                    print(f"        SPAN {line}")
    print(f"    TOTAL cell mismatches: {total}")
    return total


def main() -> int:
    argv = sys.argv[1:]
    verbose = "-v" in argv
    templated = "--template" in argv
    args = [a for a in argv if not a.startswith("-")]
    needle = args[0] if args else None

    out_dir = ROOT / "output" / ("template_pdf" if templated else "pdf")
    pairs = sources.discover()
    if needle:
        # An exact name wins, so "MWANZA CC SCHOOLS RANK" targets that document
        # and not also "MWANZA CC SCHOOLS RANK SUBJECTWISE".
        exact = [p for p in pairs if p.name.lower() == needle.lower()]
        pairs = exact or [p for p in pairs if needle.lower() in p.name.lower()]
        if not pairs:
            print(f"no document matches {needle!r}", file=sys.stderr)
            return 1

    grand = 0
    for pair in pairs:
        generated = out_dir / f"{pair.name}.pdf"
        if not generated.exists():
            print(f"skip {pair.name}: no generated PDF in {out_dir.name}/", file=sys.stderr)
            continue
        grand += compare_document(pair.name, pair.pdf, generated, verbose)

    print(f"\nGRAND TOTAL cell mismatches: {grand}")
    return 0 if grand == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
