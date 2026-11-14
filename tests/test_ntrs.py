"""Tests for ingest.ntrs — no network; urllib is patched with unittest.mock."""

import hashlib
import io
import json
import os
import tempfile
import unittest.mock as mock

import pytest

from ingest import ntrs

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "ntrs_citation_sample.json")


@pytest.fixture
def sample_citation():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _urlopen_read(body: bytes):
    """Mock urlopen context manager returning `body`."""
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = body
    return resp


# ---------------------------------------------------------------- to_source_record

def test_to_source_record_full(sample_citation):
    rec = ntrs.to_source_record(sample_citation)
    assert rec["id"] == "ntrs:20150008962"
    assert rec["kind"] == "ntrs"
    assert rec["title"].startswith("Concurrent Flame Growth")
    assert "Zhao, Xiaoyang" in rec["authors"]
    assert rec["year"] == 2015
    assert rec["url"] == "https://ntrs.nasa.gov/citations/20150008962"
    assert rec["ntrs_id"] == "20150008962"
    assert rec["pdf_url"] == "https://ntrs.nasa.gov/api/citations/20150008962/downloads/20150008962.pdf"
    assert set(rec) <= {
        "id", "kind", "title", "authors", "year", "url",
        "ntrs_id", "doi", "pdf_url",
    }


def test_missing_fields_omitted_not_invented():
    citation = {"id": 42, "title": "Only a title"}
    rec = ntrs.to_source_record(citation)
    assert rec["id"] == "ntrs:42"
    assert rec["kind"] == "ntrs"
    assert rec["title"] == "Only a title"
    assert rec["url"] == "https://ntrs.nasa.gov/citations/42"
    assert rec["ntrs_id"] == "42"
    for key in ("authors", "year", "doi", "pdf_url"):
        assert key not in rec


def test_null_doi_omitted(sample_citation):
    # Fixture record has doi: None (not present) — must not invent one.
    citation = dict(sample_citation, doi=None)
    rec = ntrs.to_source_record(citation)
    assert "doi" not in rec


# ---------------------------------------------------------------- rate limiter

def test_rate_limiter_enforces_one_per_second(monkeypatch):
    monkeypatch.setattr(ntrs, "RATE_LIMIT_SECONDS", 0.2)
    monkeypatch.setattr(ntrs, "_last_request_time", 0.0)
    calls = []
    clock = {"t": 1.0}  # start well past the last request so the first call is free

    def fake_mono():
        return clock["t"]

    def fake_sleep(s):
        calls.append(s)
        clock["t"] += s

    monkeypatch.setattr(ntrs.time, "monotonic", fake_mono)
    monkeypatch.setattr(ntrs.time, "sleep", fake_sleep)

    ntrs._rate_limit()
    assert calls == []  # first call: no wait
    ntrs._rate_limit()
    assert calls == [pytest.approx(0.2)]  # second call within window: waits
    clock["t"] += 10.0
    ntrs._rate_limit()
    assert calls == [pytest.approx(0.2)]  # enough time elapsed: no wait


# ---------------------------------------------------------------- search / get_citation

def test_search_parses_results(monkeypatch):
    payload = {"results": [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}], "stats": {}}
    with mock.patch.object(ntrs.urllib.request, "urlopen", return_value=_urlopen_read(json.dumps(payload).encode())):
        hits = ntrs.search("test", size=2)
    assert [h["id"] for h in hits] == [1, 2]


def test_get_citation(monkeypatch):
    payload = {"id": 20150008962, "title": "T"}
    with mock.patch.object(ntrs.urllib.request, "urlopen", return_value=_urlopen_read(json.dumps(payload).encode())):
        assert ntrs.get_citation(20150008962)["id"] == 20150008962


def test_request_retries_on_5xx(monkeypatch):
    monkeypatch.setattr(ntrs.time, "sleep", lambda s: None)
    monkeypatch.setattr(ntrs, "RATE_LIMIT_SECONDS", 0.0)
    responses = [
        ntrs.urllib.error.HTTPError("u", 503, "oops", {}, io.BytesIO(b"")),
        ntrs.urllib.error.HTTPError("u", 429, "slow down", {}, io.BytesIO(b"")),
        _urlopen_read(b'{"ok": true}'),
    ]
    with mock.patch.object(ntrs.urllib.request, "urlopen", side_effect=responses) as urlopen:
        assert ntrs._request("https://x") == b'{"ok": true}'
        assert urlopen.call_count == 3


def test_request_no_retry_on_404(monkeypatch):
    monkeypatch.setattr(ntrs.time, "sleep", lambda s: None)
    monkeypatch.setattr(ntrs, "RATE_LIMIT_SECONDS", 0.0)
    err = ntrs.urllib.error.HTTPError("u", 404, "nope", {}, io.BytesIO(b""))
    with mock.patch.object(ntrs.urllib.request, "urlopen", side_effect=err):
        with pytest.raises(ntrs.urllib.error.HTTPError):
            ntrs._request("https://x")


# ---------------------------------------------------------------- download_pdf

def test_download_pdf_sha256(monkeypatch):
    body = b"%PDF-1.4 fake pdf content"
    expected_hash = hashlib.sha256(body).hexdigest()
    citation = {
        "id": 20150008962,
        "downloads": [{"links": {"pdf": "/api/citations/20150008962/downloads/20150008962.pdf"}}],
    }
    monkeypatch.setattr(ntrs, "RATE_LIMIT_SECONDS", 0.0)

    with tempfile.TemporaryDirectory() as out_dir:
        with mock.patch.object(ntrs, "get_citation", return_value=citation):
            with mock.patch.object(ntrs.urllib.request, "urlopen", return_value=_urlopen_read(body)):
                result = ntrs.download_pdf(20150008962, out_dir=out_dir)
        assert result["sha256"] == expected_hash
        assert result["bytes"] == len(body)
        assert os.path.isfile(result["path"])
        assert result["retrieved_at"].endswith("+00:00")

        # Second call: file exists -> skipped download, same hash, no network
        with mock.patch.object(ntrs.urllib.request, "urlopen", side_effect=AssertionError("no network")):
            again = ntrs.download_pdf(20150008962, out_dir=out_dir)
        assert again["sha256"] == expected_hash


# ---------------------------------------------------------------- contract conformance (added in review)

def test_ingest_dates_are_not_used_as_publication_year():
    c = {"id": 1, "title": "t", "distributionDate": "2019-01-01T00:00:00.0000000+00:00",
         "created": "2018-01-01T00:00:00.0000000+00:00"}
    assert "year" not in ntrs.to_source_record(c)


def test_source_record_matches_contract():
    import json as _json
    from pathlib import Path as _P
    from ignis_contract import schema_errors
    c = _json.loads((_P(__file__).parent / "fixtures" / "ntrs_citation_sample.json").read_text(encoding="utf-8"))
    rec = ntrs.to_source_record(c)
    assert not schema_errors(rec, "Source"), [str(e) for e in schema_errors(rec, "Source")]
