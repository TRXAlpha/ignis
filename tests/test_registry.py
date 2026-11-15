"""Every registry quote on an NTRS source must be verbatim on its cited page (campaigns, habitats)."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _refs():
    for name in ("campaigns", "habitats"):
        for item in json.loads((ROOT / f"registry/{name}.json").read_text(encoding="utf-8")):
            for r in item["refs"]:
                if r["source_id"].startswith("ntrs:") and "quote" in r:
                    yield item["id"], r


@pytest.mark.parametrize("item,ref", list(_refs()))
def test_registry_quote_on_page(item, ref):
    from ingest.curated import require_text
    if not (ROOT / f"data/raw/ntrs/{ref['source_id'].split(':')[1]}.pdf").exists():
        pytest.skip("pdf not downloaded")
    sources = {s["id"]: s for s in json.loads((ROOT / "registry/sources.json").read_text(encoding="utf-8"))}
    require_text(sources, ref["source_id"], ref["page"], ref["quote"])
