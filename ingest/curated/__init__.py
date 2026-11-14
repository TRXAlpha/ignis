"""Curated transcriptions: small, reviewable modules that turn one table/passage into observations.

Every module must call `require_text()` for each number it emits, so the build fails if the number is
not literally present on the cited PDF page. That is the guard against transcription typos and
against an LLM 'remembering' a value instead of reading it.
"""
from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from pathlib import Path

import pymupdf

RAW = Path("data/raw/ntrs")


class TranscriptionError(AssertionError):
    pass


def _norm(s: str) -> str:
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=None)
def pdf_pages(source_id: str, expected_sha256: str) -> tuple[str, ...]:
    kind, _, nid = source_id.partition(":")
    if kind != "ntrs":
        raise TranscriptionError(f"only ntrs sources supported so far, got {source_id}")
    path = RAW / f"{nid}.pdf"
    if not path.exists():
        raise TranscriptionError(f"{path} missing: run python -m ingest.ntrs fetch {nid} --download")
    data = path.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != expected_sha256:
        raise TranscriptionError(f"{path} sha256 {got[:12]} != registry {expected_sha256[:12]} (different file)")
    doc = pymupdf.open(stream=data, filetype="pdf")
    return tuple(_norm(p.get_text("text")) for p in doc)


def require_text(sources: dict, source_id: str, page: int, *snippets: str) -> None:
    """Assert every snippet appears (whitespace/dash-normalized) on 1-based PDF page `page`."""
    pages = pdf_pages(source_id, sources[source_id]["sha256"])
    text = pages[page - 1]
    for s in snippets:
        if _norm(s) not in text:
            raise TranscriptionError(f"{source_id} p{page}: {s!r} not found on page")
