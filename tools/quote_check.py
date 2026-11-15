"""Verify every quote in a bass2_test_outcomes JSON list appears (whitespace-normalized) on its cited page."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORM = re.compile(r"\s+")


def norm(s: str) -> str:
    return NORM.sub(" ", s).strip()


def page_path(page: int) -> Path:
    return ROOT / "data" / "text" / "20210011385" / f"page_{page}.txt"


def main(argv: list[str]) -> int:
    registry = ROOT / "registry" / "bass2_test_outcomes_a.json"
    rows = json.loads(registry.read_text(encoding="utf-8"))
    cache: dict[int, str] = {}
    failures = 0
    for row in rows:
        page = row["page"]
        if page not in cache:
            cache[page] = norm(page_path(page).read_text(encoding="utf-8"))
        body = cache[page]
        for key in ("quote", "flow_quote"):
            text = row.get(key)
            if text is None:
                continue
            if norm(text) not in body:
                print(f"FAIL {row.get('test_id')} {key}: not found verbatim on page {page}")
                failures += 1
            else:
                print(f"ok   {row.get('test_id')} {key}")
    print(f"{len(rows)} rows checked, {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
