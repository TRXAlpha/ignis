import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data/raw/ntrs/20210011385.pdf"
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="source PDFs not downloaded (python -m ingest.ntrs fetch ... --download)")


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _sources():
    return {s["id"]: s for s in json.loads((ROOT / "registry/sources.json").read_text(encoding="utf-8"))}


def test_build_is_production_valid():
    from ignis_contract import check_bundle, is_valid
    from ingest.build_bundle import build
    b = build()
    issues = check_bundle(b, production=True)
    assert is_valid(issues), [str(i) for i in issues]
    assert len(b["observations"]) >= 2


def test_require_text_rejects_number_not_on_page():
    from ingest.curated import TranscriptionError, require_text
    require_text(_sources(), "ntrs:20210011385", 36, "21 10±5")
    with pytest.raises(TranscriptionError):
        require_text(_sources(), "ntrs:20210011385", 36, "21 12±5")   # typo'd value
    with pytest.raises(TranscriptionError):
        require_text(_sources(), "ntrs:20210011385", 35, "21 10±5")   # right value, wrong page


def test_hash_mismatch_rejected():
    from ingest.curated import TranscriptionError, pdf_pages
    with pytest.raises(TranscriptionError):
        pdf_pages("ntrs:20210011385", "0" * 64)
