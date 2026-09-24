"""Show which tokens the templated output loses for one document.

Read-only diagnostic. Renders a document through the data -> template -> PDF
path and prints the tokens present in the reference but absent from the output
(and vice versa), so a content gap can be traced to a specific column or block.

Usage::

    python tools/template_missing.py "Top 10 Schools"
    python tools/template_missing.py "District Performance" 60
"""

from __future__ import annotations

import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sars import sources, template_maker  # noqa: E402
from sars.extract import extract_document  # noqa: E402
from sars.extract_data import extract_report  # noqa: E402
from sars.verify import tokens  # noqa: E402


def main(needle: str, limit: int) -> int:
    pair = sources.select(needle)[0]
    doc = extract_document(pair.pdf, pair.html)
    report = extract_report(doc, pair.name)
    rtype = getattr(getattr(report, "meta", None), "report_type", "generic")

    out = Path(tempfile.mkdtemp(prefix="sars-miss-")) / f"{pair.name}.pdf"
    template_maker.render_pdf(rtype, report, out)

    ref_c = Counter(tokens(pair.pdf))
    out_c = Counter(tokens(out))
    missing = ref_c - out_c
    extra = out_c - ref_c

    print(f"document   {pair.name}  (report_type={rtype})")
    print(f"ref tokens {sum(ref_c.values())}   out tokens {sum(out_c.values())}")
    print(f"missing    {sum(missing.values())} tokens, {len(missing)} distinct")
    for tok, n in missing.most_common(limit):
        print(f"   -{n:5d}  {tok!r}")
    print(f"extra      {sum(extra.values())} tokens, {len(extra)} distinct")
    for tok, n in extra.most_common(limit):
        print(f"   +{n:5d}  {tok!r}")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if not args:
        raise SystemExit("usage: template_missing.py <name-substring> [limit]")
    raise SystemExit(main(args[0], int(args[1]) if len(args) > 1 else 40))
