"""Stdlib-only NTRS (NASA Technical Reports Server) client.

Verified against the live API (2026-11):
- search:  GET https://ntrs.nasa.gov/api/citations/search?q=...&page.size=N
           returns {"results": [citation, ...], "stats": {...}}
- citation: GET https://ntrs.nasa.gov/api/citations/<id>
- pdf:     https://ntrs.nasa.gov/api/citations/<id>/downloads/<name>.pdf

Observed citation fields: id (int), title, authorAffiliations[].meta.author.name,
publications[].publicationDate, downloads[].links.pdf (relative path), doi
(present only on some records, may be None).
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://ntrs.nasa.gov"
SEARCH_URL = BASE_URL + "/api/citations/search"
CITATION_URL = BASE_URL + "/api/citations/{id}"
DOWNLOAD_BASE = BASE_URL + "/api/citations/{id}/downloads/{filename}"
USER_AGENT = "ignis-research/0.1"
RATE_LIMIT_SECONDS = 1.0
TIMEOUT = 30
MAX_RETRIES = 4
DEFAULT_OUT_DIR = os.path.join("data", "raw", "ntrs")

_last_request_time = 0.0


def _rate_limit():
    """Enforce at most 1 request per second."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.monotonic()


def _request(url, accept="application/json"):
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


def search(query, size=25, page=1):
    """Search NTRS; returns the raw list of citation hits."""
    params = urllib.parse.urlencode({"q": query, "page.size": size, "page": page})
    data = json.loads(_request(SEARCH_URL + "?" + params).decode("utf-8"))
    return data.get("results", [])


def get_citation(ntrs_id):
    """Fetch a single citation record by NTRS id."""
    data = json.loads(_request(CITATION_URL.format(id=ntrs_id)).decode("utf-8"))
    return data


def _first_pdf_link(citation):
    for dl in citation.get("downloads") or []:
        links = dl.get("links") or {}
        link = links.get("pdf") or links.get("original")
        if link:
            if link.startswith("http"):
                return link
            return BASE_URL + link
        name = dl.get("name")
        if name:
            return DOWNLOAD_BASE.format(id=citation.get("id"), filename=name)
    return None


def _publication_year(citation):
    """Publication year only. distributionDate/created/submittedDate are NTRS ingest dates,
    not publication dates, so they are deliberately NOT used as a fallback (no guessing)."""
    for pub in citation.get("publications") or []:
        date_str = (pub.get("publicationDate") or "")[:10]
        if len(date_str) >= 4 and date_str[:4].isdigit():
            return int(date_str[:4])
    return None


def to_source_record(citation):
    """Map a raw NTRS citation to the IGNIS source-record shape.

    Keys are omitted when the underlying value is unknown; nothing is guessed.
    """
    record = {"id": "ntrs:%s" % citation["id"], "kind": "ntrs"}

    title = citation.get("title")
    if title:
        record["title"] = title

    authors = []
    for aff in citation.get("authorAffiliations") or []:
        name = ((aff.get("meta") or {}).get("author") or {}).get("name")
        if name:
            authors.append(name)
    if authors:
        record["authors"] = authors

    year = _publication_year(citation)
    if year is not None:
        record["year"] = year

    ntrs_id = str(citation.get("id"))
    record["url"] = "https://ntrs.nasa.gov/citations/%s" % ntrs_id
    record["ntrs_id"] = ntrs_id

    doi = citation.get("doi")
    if doi:
        record["doi"] = doi

    pdf_url = _first_pdf_link(citation)
    if pdf_url:
        record["pdf_url"] = pdf_url

    return record


def download_pdf(ntrs_id, out_dir=DEFAULT_OUT_DIR):
    """Download the citation's first PDF; returns path, sha256, size, timestamp.

    Skips the download if the file already exists (returns existing file's hash).
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.pdf" % ntrs_id)

    if os.path.exists(path):
        with open(path, "rb") as fh:
            data = fh.read()
        retrieved = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)  # when we actually fetched it
    else:
        retrieved = None
        citation = get_citation(ntrs_id)
        pdf_url = _first_pdf_link(citation)
        if not pdf_url:
            raise ValueError("no PDF available for NTRS id %s" % ntrs_id)
        data = _request(pdf_url, accept="application/pdf")
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


def _main(argv):
    import argparse

    parser = argparse.ArgumentParser(prog="ingest.ntrs", description="NTRS client")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="search NTRS")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--size", type=int, default=25)

    p_fetch = sub.add_parser("fetch", help="fetch one citation as a source record")
    p_fetch.add_argument("ntrs_id")
    p_fetch.add_argument("--download", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "search":
        for hit in search(" ".join(args.query), size=args.size):
            year = _publication_year(hit)
            print("%s | %s | %s" % (hit.get("id"), year if year else "----", hit.get("title", "")))
    elif args.command == "fetch":
        citation = get_citation(args.ntrs_id)
        record = to_source_record(citation)
        if args.download:
            dl = download_pdf(args.ntrs_id)
            record["sha256"] = dl["sha256"]          # contract Source fields
            record["retrieved_at"] = dl["retrieved_at"]
            print("saved %s (%d bytes)" % (dl["path"], dl["bytes"]), file=sys.stderr)
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    _main(sys.argv[1:])
