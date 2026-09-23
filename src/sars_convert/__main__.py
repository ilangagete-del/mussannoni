"""Command-line entry point for sars_convert.

Placeholder. The real CLI (convert -> render -> verify) is wired up by a later
feature. For now it just reports that the pipeline is not implemented yet.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Entry point stub. Returns a non-zero exit code until implemented."""
    print(
        "sars-convert: pipeline not implemented yet. "
        "See README.md for the planned convert -> render -> verify flow.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
