"""Assemble data/bundle.json from registry/*.json + every curated module, then validate (production mode).

python -m ingest.build_bundle            # writes data/bundle.json, exits 1 if invalid
"""
from __future__ import annotations

import importlib
import json
import pkgutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from ignis_contract import check_bundle, is_valid

from . import curated

REG = Path("registry")
OUT = Path("data/bundle.json")


def load(name: str) -> list[dict]:
    return json.loads((REG / f"{name}.json").read_text(encoding="utf-8"))


def build() -> dict:
    sources = load("sources")
    by_id = {s["id"]: s for s in sources}
    obs = []
    for m in pkgutil.iter_modules(curated.__path__):
        mod = importlib.import_module(f"{curated.__name__}.{m.name}")
        got = mod.observations(by_id)
        print(f"  {m.name}: {len(got)} observations", file=sys.stderr)
        obs.extend(got)
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sources": sources,
        "campaigns": load("campaigns"),
        "materials": load("materials"),
        "observations": obs,
    }


def main() -> int:
    b = build()
    issues = check_bundle(b, production=True)
    for i in issues:
        print(i, file=sys.stderr)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(b, indent=1, ensure_ascii=False), encoding="utf-8")
    ok = is_valid(issues)
    print(f"{'OK' if ok else 'INVALID'}: {len(b['observations'])} observations, {len(b['sources'])} sources -> {OUT}",
          file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
