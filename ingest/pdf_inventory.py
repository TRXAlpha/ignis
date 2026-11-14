"""Find the figures and tables in a PDF that carry in-scope data, before anyone extracts anything.

python -m ingest.pdf_inventory data/raw/ntrs/20210011385.pdf --source ntrs:20210011385 [--out research/inventory/x.json]

Writes per-page text to data/text/<stem>/page_NNN.txt (for grep / LLM passes) and an inventory of
captions scored against the narrowed scope. Captions are quoted verbatim from the PDF text layer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

CAPTION_RE = re.compile(r"^\s*(Fig(?:ure)?\.?|Table)\s+([0-9]+[A-Za-z]?(?:[.\-][0-9]+)?)[.:\s]\s*(.*)$", re.I)

# keyword -> weight. Scope: thin solid fuels, spread rate, flammability/extinction boundary.
KEYWORDS = {
    r"spread rate|flame spread|spread velocit": 3,
    r"extinction|blow-?off|quench": 3,
    r"flammab": 3,
    r"limiting oxygen|oxygen concentration|o2 concentration|oxygen mole|% ?o2|oxygen level": 2,
    r"flow (?:velocity|speed)|air ?flow|forced flow|cm/s|opposed|concurrent": 2,
    r"pmma|cotton|sibal|nomex|kimwipe|cellulose|fabric|acrylic|ultem|plexiglas": 1,
    r"thin|thickness": 1,
    r"microgravity|normal gravity|1-?g|drop tower|partial gravity": 1,
    r"flame length|standoff|preheat": 1,
    r"\btable\b": 0,
}
_KW = [(re.compile(k, re.I), w) for k, w in KEYWORDS.items()]


def page_texts(pdf: Path, text_dir: Path | None) -> list[str]:
    doc = pymupdf.open(pdf)
    out = []
    for i, page in enumerate(doc, start=1):
        t = page.get_text("text")
        out.append(t)
        if text_dir is not None:
            text_dir.mkdir(parents=True, exist_ok=True)
            (text_dir / f"page_{i:03d}.txt").write_text(t, encoding="utf-8")
    return out


def find_captions(pages: list[str]) -> list[dict]:
    hits = []
    for pno, text in enumerate(pages, start=1):
        lines = text.splitlines()
        for li, line in enumerate(lines):
            m = CAPTION_RE.match(line)
            if not m:
                continue
            kind = "table" if m.group(1).lower().startswith("tab") else "figure"
            # caption may wrap: join following short lines until a blank or the next caption
            cap = [m.group(3).strip()]
            for nxt in lines[li + 1: li + 4]:
                if not nxt.strip() or CAPTION_RE.match(nxt):
                    break
                cap.append(nxt.strip())
            caption = " ".join(c for c in cap if c).lstrip("—–-:. ")
            if len(caption) < 8:  # in-text reference like "Figure 3 shows", or an axis label
                continue
            score, matched = 0, []
            for rx, w in _KW:
                if rx.search(caption):
                    score += w
                    matched.append(rx.pattern.split("|")[0])
            hits.append({"kind": kind, "label": m.group(2), "page": pno, "caption": caption[:400],
                         "score": score, "keywords": matched})
    # captions are often repeated in a list of figures; keep the latest page per (kind,label) = the real one
    best = {}
    for h in hits:
        best[(h["kind"], h["label"])] = h
    return sorted(best.values(), key=lambda h: (-h["score"], h["page"]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ingest.pdf_inventory")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--source", required=True, help="contract source id, e.g. ntrs:20210011385")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--min-score", type=int, default=4)
    ap.add_argument("--no-text", action="store_true", help="do not write per-page text files")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    text_dir = None if a.no_text else Path("data/text") / a.pdf.stem
    pages = page_texts(a.pdf, text_dir)
    caps = find_captions(pages)
    keep = [c for c in caps if c["score"] >= a.min_score]
    inv = {"source_id": a.source, "pdf": str(a.pdf).replace("\\", "/"), "pages": len(pages),
           "text_chars": sum(map(len, pages)), "captions_total": len(caps), "in_scope": keep}
    out = a.out or Path("research/inventory") / f"{a.pdf.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{a.source}: {len(pages)} pages, {len(caps)} captions, {len(keep)} in scope -> {out}", file=sys.stderr)
    for c in keep[:40]:
        print(f"  p{c['page']:>3} {c['kind'][:3]} {c['label']:>6} s{c['score']}  {c['caption'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
