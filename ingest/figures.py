"""Render a PDF figure to PNG for WebPlotDigitizer and record its sha256.

python -m ingest.figures render ntrs:20210011385 83 --name bass2_fig6_9 [--clip x0,y0,x1,y1] [--dpi 300]

Writes data/figures/<name>.png and prints the hash. The PNG is what gets digitized, so its hash goes into
the figure spec (digitized/<name>.spec.json) and every resulting observation. --clip is in PDF points
(72/inch, origin top-left); omit it to render the whole page (WPD zooms fine).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pymupdf as fitz

RAW = Path("data/raw/ntrs")
OUT = Path("data/figures")


def pdf_path(source_id: str) -> Path:
    kind, _, ident = source_id.partition(":")
    if kind != "ntrs":
        raise SystemExit(f"only ntrs: sources are stored locally, got {source_id}")
    p = RAW / f"{ident}.pdf"
    if not p.exists():
        raise SystemExit(f"{p} missing; run: python -m ingest.ntrs fetch {ident} --download")
    return p


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(source_id: str, page: int, name: str, clip: tuple[float, float, float, float] | None = None,
           dpi: int = 300) -> tuple[Path, str]:
    doc = fitz.open(pdf_path(source_id))
    pg = doc[page - 1]  # 1-based physical page, same as Locator.page
    pix = pg.get_pixmap(dpi=dpi, clip=fitz.Rect(*clip) if clip else None)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{name}.png"
    pix.save(out)
    return out, sha256_file(out)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("source_id")
    r.add_argument("page", type=int)
    r.add_argument("--name", required=True)
    r.add_argument("--clip")
    r.add_argument("--dpi", type=int, default=300)
    a = ap.parse_args(argv)
    clip = tuple(float(v) for v in a.clip.split(",")) if a.clip else None
    out, h = render(a.source_id, a.page, a.name, clip, a.dpi)
    print(f"{out}  sha256={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
