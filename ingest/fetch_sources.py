"""Download every NTRS PDF in registry/sources.json and verify its sha256 against the registry.

python -m ingest.fetch_sources          # idempotent; exits 1 on any hash mismatch
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .ntrs import download_pdf
from .psi import download_experimental_table


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bad = 0
    for s in json.loads(Path("registry/sources.json").read_text(encoding="utf-8")):
        if s["kind"] == "ntrs":
            nid = s["id"].split(":", 1)[1]
            got = download_pdf(nid)
        elif s["kind"] == "psi_dataset":
            acc = s["id"].split(":", 1)[1]
            got = download_experimental_table(acc)
        else:
            continue
        ok = got["sha256"] == s.get("sha256")
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} {s['id']}  {got['sha256'][:12]}  {s['title'][:60]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
