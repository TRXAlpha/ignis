"""Stdlib-only PSI (NASA Physical Sciences Informatics) client.

Verified against the live API (2026-11):
- metadata: GET https://psi.nasa.gov/geode-py/ws/repo/investigations/<ACC>
           JSON; relevant keys: "accession", "doi" (e.g. "10.60555/4qc4-de67"), "title",
           "licenseIdentifier" (e.g. "CC0-1.0"), "experimentalTable" (list of file entries with
           "file_name" and "version").
- presign: GET https://psi.nasa.gov/geode-py/ws/studies/<ACC>/download?file=<urlencoded
           filename>&version=<v>&redirect=false
           -> body is a presigned S3 URL (plain text; may arrive JSON-quoted); GET that for bytes.

PSI data is public, CC0, no login. Polite client: UA "ignis-research/0.1", 1 req/s, 3 retries.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://psi.nasa.gov"
METADATA_URL = BASE_URL + "/geode-py/ws/repo/investigations/{acc}"
PRESIGN_URL = BASE_URL + "/geode-py/ws/studies/{acc}/download"
USER_AGENT = "ignis-research/0.1"
RATE_LIMIT_SECONDS = 1.0
TIMEOUT = 30
MAX_RETRIES = 3
DEFAULT_OUT_DIR = os.path.join("data", "raw", "psi")

# Fallback experimental-table filenames/version only when metadata lacks them.
FALLBACK_TABLES = {
    "PSI-25": ("PSI-25_Experimental table_BASS-II.csv", 1),
    "PSI-26": ("PSI-26_Experimental table_BASS.csv", 1),
    "PSI-98": ("PSI-98_Experimental table_SAFFIRE-1.csv", 1),
    "PSI-99": ("PSI-99_Experimental table_SAFFIRE-2.csv", 1),
    "PSI-100": ("PSI-100_Experimental table_SAFFIRE-3.csv", 1),
}

_last_request_time = 0.0


def _rate_limit():
    """Enforce at most 1 request per second."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _request(url, accept="*/*"):
    """GET with polite UA, rate limiting, and backoff on 429/5xx. Returns bytes."""
    last_exc = None
    for attempt in range(MAX_RETRIES):
        _rate_limit()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or 500 <= exc.code < 600:
                last_exc = exc
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            time.sleep(2 ** attempt)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("unreachable: request loop exited without result")


def get_metadata(acc):
    """Fetch the investigation metadata JSON for an accession (e.g. 'PSI-25')."""
    return json.loads(_request(METADATA_URL.format(acc=acc), accept="application/json").decode("utf-8"))


def _experimental_table_entry(meta):
    """Pick the experimental-table entry from metadata; None if absent/empty."""
    for entry in meta.get("experimentalTable") or []:
        if entry.get("file_name"):
            return entry
    return None


def table_name_and_version(acc, meta):
    """Derive (filename, version) for the experimental table: metadata first, fallback second."""
    entry = _experimental_table_entry(meta) if meta else None
    if entry:
        return entry["file_name"], int(entry.get("version") or 1)
    if acc in FALLBACK_TABLES:
        return FALLBACK_TABLES[acc]
    raise ValueError("no experimental table known for %s (not in metadata or fallback list)" % acc)


def presign(acc, filename, version):
    """Get the presigned S3 URL for a study file. Body is plain text or a JSON-quoted string."""
    params = urllib.parse.urlencode({"file": filename, "version": version, "redirect": "false"})
    body = _request(PRESIGN_URL.format(acc=acc) + "?" + params).decode("utf-8").strip()
    if body.startswith('"'):
        body = json.loads(body)
    if not body.startswith("http"):
        raise ValueError("unexpected presign body for %s/%s: %.200r" % (acc, filename, body))
    return body


def download_experimental_table(acc, out_dir=DEFAULT_OUT_DIR):
    """Download the accession's experimental-table CSV; returns path, sha256, size, timestamp.

    Skips the download if the file already exists (returns existing file's hash, like ingest.ntrs).
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.csv" % acc)

    if os.path.exists(path):
        with open(path, "rb") as fh:
            data = fh.read()
        retrieved = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)  # when we actually fetched it
    else:
        retrieved = None
        meta = get_metadata(acc)
        filename, version = table_name_and_version(acc, meta)
        url = presign(acc, filename, version)
        data = _request(url, accept="text/csv,application/octet-stream,*/*")
        tmp_path = path + ".part"
        with open(tmp_path, "wb") as fh:
            fh.write(data)
        os.replace(tmp_path, path)

    return {
        "path": os.path.abspath(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "retrieved_at": (retrieved or datetime.now(timezone.utc)).isoformat(),
    }


def to_source_record(meta, dl):
    """Map PSI metadata + a download result to the IGNIS source-record shape.

    Keys are omitted when unknown; nothing is guessed.
    """
    acc = meta.get("accession")
    if not acc:
        raise ValueError("metadata has no accession")
    record = {"id": "psi:%s" % acc, "kind": "psi_dataset"}

    title = meta.get("title")
    if title:
        record["title"] = title

    record["url"] = "https://psi.nasa.gov/physci/repo/data/investigations/%s" % acc

    doi = meta.get("doi")
    if doi:
        record["doi"] = doi

    license_id = meta.get("licenseIdentifier")
    if license_id:
        record["license"] = license_id

    record["sha256"] = dl["sha256"]
    record["retrieved_at"] = dl["retrieved_at"]
    return record


def _main(argv):
    import argparse

    parser = argparse.ArgumentParser(prog="ingest.psi", description="PSI experimental-table fetcher")
    parser.add_argument("command", choices=["fetch"])
    parser.add_argument("accessions", nargs="+")
    parser.add_argument("--write-registry", action="store_true",
                        help="append missing records to registry/sources.json")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    records = []
    for acc in args.accessions:
        dl = download_experimental_table(acc, out_dir=args.out_dir)
        meta = get_metadata(acc)
        record = to_source_record(meta, dl)
        from ignis_contract import schema_errors
        errors = schema_errors(record, "Source")
        if errors:
            raise SystemExit("schema errors for %s: %s" % (record["id"], errors))
        records.append(record)
        print("saved %s (%d bytes)" % (dl["path"], dl["bytes"]), file=sys.stderr)

    if args.write_registry:
        reg_path = os.path.join("registry", "sources.json")
        with open(reg_path, "r", encoding="utf-8") as fh:
            registry = json.load(fh)
        existing = {s["id"] for s in registry}
        added = [r for r in records if r["id"] not in existing]
        registry.extend(added)
        with open(reg_path, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print("registry: + %d of %d (others already present)" % (len(added), len(records)), file=sys.stderr)

    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    _main(sys.argv[1:])
