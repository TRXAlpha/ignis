"""Tests for ingest.psi — no network; urllib is patched with unittest.mock."""

import hashlib
import io
import json
import os
import tempfile
import unittest.mock as mock

import pytest

from ingest import psi


def _urlopen_read(body: bytes):
    resp = mock.MagicMock()
    resp.__enter__.return_value.read.return_value = body
    return resp


METADATA = {
    "accession": "PSI-25",
    "title": "Burning and Suppression of Solids - II",
    "doi": "10.60555/4qc4-de67",
    "licenseIdentifier": "CC0-1.0",
    "experimentalTable": [
        {"file_name": "PSI-25_Experimental table_BASS-II.csv", "version": 1},
    ],
}
PRESIGNED = "https://psi-repo-prod.s3.amazonaws.com/psi-data/PSI-25/x.csv?Signature=abc"
CSV_BODY = b"Test,O2,flow\n1,21,5.0\n"


def _patch_network(monkeypatch, body=CSV_BODY):
    """Patch urlopen so metadata -> presign -> bytes all come from fixtures."""
    calls = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        calls.append(url)
        if "/repo/investigations/" in url:
            return _urlopen_read(json.dumps(METADATA).encode())
        if "/download?" in url:
            assert "redirect=false" in url
            assert urllib.parse.quote_plus("PSI-25_Experimental table_BASS-II.csv") in url
            return _urlopen_read(PRESIGNED.encode())
        if url.startswith("https://psi-repo-prod.s3.amazonaws.com/"):
            return _urlopen_read(body)
        raise AssertionError("unexpected url " + url)

    import urllib.parse  # noqa: F401  (imported for assertion clarity)
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(psi, "RATE_LIMIT_SECONDS", 0.0)
    return calls


# ---------------------------------------------------------------- metadata / naming

def test_get_metadata(monkeypatch):
    _patch_network(monkeypatch)
    meta = psi.get_metadata("PSI-25")
    assert meta["accession"] == "PSI-25"
    assert meta["doi"].startswith("10.60555/")


def test_table_name_and_version_from_metadata():
    name, version = psi.table_name_and_version("PSI-25", METADATA)
    assert name == "PSI-25_Experimental table_BASS-II.csv"
    assert version == 1


def test_table_name_and_version_fallback():
    meta = {"accession": "PSI-98", "experimentalTable": []}
    name, version = psi.table_name_and_version("PSI-98", meta)
    assert name == "PSI-98_Experimental table_SAFFIRE-1.csv"
    assert version == 1


def test_unknown_accession_without_metadata_raises():
    with pytest.raises(ValueError):
        psi.table_name_and_version("PSI-999", {"experimentalTable": []})


def test_presign_unquotes_json_string(monkeypatch):
    _patch_network(monkeypatch)
    url = psi.presign("PSI-25", "PSI-25_Experimental table_BASS-II.csv", 1)
    assert url == PRESIGNED


# ---------------------------------------------------------------- download

def test_download_experimental_table_sha256(monkeypatch):
    calls = _patch_network(monkeypatch)
    with tempfile.TemporaryDirectory() as out_dir:
        result = psi.download_experimental_table("PSI-25", out_dir=out_dir)
        assert result["sha256"] == hashlib.sha256(CSV_BODY).hexdigest()
        assert result["bytes"] == len(CSV_BODY)
        assert os.path.isfile(result["path"])
        assert result["retrieved_at"].endswith("+00:00")
        assert len([c for c in calls if c.startswith("https://psi-repo-prod")]) == 1

        # Second call: file exists -> skipped download, same hash, no network
        calls.clear()
        with mock.patch.object(psi.urllib.request, "urlopen", side_effect=AssertionError("no network")):
            again = psi.download_experimental_table("PSI-25", out_dir=out_dir)
        assert again["sha256"] == result["sha256"]
        assert calls == []  # metadata fetch still happens only inside download when uncached


# ---------------------------------------------------------------- source record

def _record():
    dl = {"sha256": "a" * 64, "retrieved_at": "2026-11-15T10:00:00+00:00"}
    return psi.to_source_record(METADATA, dl)


def test_to_source_record_fields():
    rec = _record()
    assert rec["id"] == "psi:PSI-25"
    assert rec["kind"] == "psi_dataset"
    assert rec["title"] == "Burning and Suppression of Solids - II"
    assert rec["url"] == "https://psi.nasa.gov/physci/repo/data/investigations/PSI-25"
    assert rec["doi"] == "10.60555/4qc4-de67"
    assert rec["license"] == "CC0-1.0"
    assert rec["sha256"] == "a" * 64
    assert "campaign_ids" not in rec


def test_source_record_matches_contract():
    from ignis_contract import schema_errors
    rec = _record()
    assert not schema_errors(rec, "Source"), [str(e) for e in schema_errors(rec, "Source")]


def test_missing_optional_fields_omitted_not_invented():
    meta = {"accession": "PSI-98", "title": "T"}  # no doi / license
    dl = {"sha256": "b" * 64, "retrieved_at": "2026-11-15T10:00:00+00:00"}
    rec = psi.to_source_record(meta, dl)
    for key in ("doi", "license"):
        assert key not in rec


# ---------------------------------------------------------------- retry behaviour

def test_request_retries_on_5xx(monkeypatch):
    monkeypatch.setattr(psi.time, "sleep", lambda s: None)
    monkeypatch.setattr(psi, "RATE_LIMIT_SECONDS", 0.0)
    responses = [
        psi.urllib.error.HTTPError("u", 503, "oops", {}, io.BytesIO(b"")),
        _urlopen_read(b"ok"),
    ]
    with mock.patch.object(psi.urllib.request, "urlopen", side_effect=responses) as urlopen:
        assert psi._request("https://x") == b"ok"
        assert urlopen.call_count == 2


def test_request_no_retry_on_404(monkeypatch):
    monkeypatch.setattr(psi.time, "sleep", lambda s: None)
    monkeypatch.setattr(psi, "RATE_LIMIT_SECONDS", 0.0)
    err = psi.urllib.error.HTTPError("u", 404, "nope", {}, io.BytesIO(b""))
    with mock.patch.object(psi.urllib.request, "urlopen", side_effect=err):
        with pytest.raises(psi.urllib.error.HTTPError):
            psi._request("https://x")
