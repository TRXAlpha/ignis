"""Print Appendix A pages of the BASS-II report (pymupdf text layer) for reading.

Usage: python -m tools.appendix_dump [first_page] [last_page]   (1-based physical pages)
"""
from __future__ import annotations

import sys

import pymupdf

PDF = "data/raw/ntrs/20210011385.pdf"


def main() -> int:
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 111
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 122
    doc = pymupdf.open(PDF)
    for p in range(first, min(last, len(doc)) + 1):
        print(f"\n===== PDF page {p} =====")
        print(doc[p - 1].get_text("text"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
