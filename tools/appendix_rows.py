"""T2c STEP A: dump BASS-II Appendix A test-matrix rows (PDF pages 111-122) to JSON.

Run: .venv\\Scripts\\python.exe tools/appendix_rows.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

PDF = Path("data/raw/ntrs/20210011385.pdf")
OUT = Path("data/text/bass2_appendix_rows.json")
PAGES = range(111, 123)
TEST_ID = re.compile(r"^[A-Z]{1,2}\d+[a-z]?$")


def norm_cell(c: str) -> str:
    s = re.sub(r"\s+", " ", c).strip()
    s = re.sub(r"(\d) \.(\d)", r"\1.\2", s)
    s = s.replace(" ,", ",")
    return s


def main() -> None:
    doc = pymupdf.open(PDF)
    rows: list[dict] = []
    per_page: dict[int, int] = {}
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur is not None:
            cur["cells"] = [norm_cell(c) for c in cur["cells"]]
            cur["observation_raw"] = cur["observation"]
            cur["observation"] = norm_cell(cur["observation"])
            rows.append(cur)
            per_page[cur["page"]] = per_page.get(cur["page"], 0) + 1
            cur = None

    for pno in PAGES:
        page = doc[pno - 1]
        for tab in page.find_tables():
            for row in tab.extract():
                cells = [c.replace("\n", " ").strip() for c in row if c is not None and c.strip()]
                if not cells:
                    continue
                tid = next((c for c in cells if TEST_ID.match(c)), None)
                if tid is not None:
                    flush()
                    cur = {"page": pno, "test_id": tid, "cells": cells,
                           "observation": cells[-1]}
                elif cur is not None:
                    cur["cells"].extend(cells)
                    cur["observation"] += " " + cells[-1]
                else:
                    # leading continuation with no previous test yet: skip
                    continue
    flush()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} tests -> {OUT}")
    for p in sorted(per_page):
        print(f"  page {p}: {per_page[p]}")


if __name__ == "__main__":
    main()
