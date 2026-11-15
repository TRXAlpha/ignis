"""Record real analyst runs (local LLM via Ollama) for the website: question, model, tool calls, answer or refusal.

python -m analyst.record            # writes web/public/data/analyst_runs.json

Nothing is edited after the fact: answers, refusals and tool results are stored exactly as the run produced them.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .__main__ import ask

OUT = Path("web/public/data/analyst_runs.json")
RUNS = [
    ("gemmaclaude:latest", "What is the lowest oxygen level at which PMMA keeps burning in microgravity, "
                           "and how does it compare to the normal-gravity limit?"),
    ("gemmaclaude:latest", "Is the 8.2 psia, 34 percent oxygen exploration atmosphere safe for PMMA?"),
    ("gemmaclaude:latest", "Which experiment should be run next, and why?"),
    ("gemmaclaude:latest", "Does silicone burn differently on Earth than in orbit? Give numbers."),
    ("hf.co/empero-ai/Qwen3.8-4B-Distill-GGUF:Q4_K_M",
     "Is the 8.2 psia, 34 percent oxygen exploration atmosphere safe for PMMA?"),
]
# Team review notes, added only after reading a recorded run (the guard checks numbers, not meaning).
REVIEW = Path("analyst/review_notes.json")


def _short(obj, n=400):
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= n else s[:n] + "…"


def apply_reviews() -> int:
    """Attach team review notes to an existing recording without re-running the models."""
    data = json.loads(OUT.read_text(encoding="utf-8"))
    notes = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}
    n = 0
    for row in data["runs"]:
        note = notes.get(f"{row['model']}|{row['question']}")
        if note and (row["answer"] or "").startswith(note["answer_starts"]):
            row["review"] = note["note"]
            n += 1
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} review notes attached")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["--apply-reviews"]:
        return apply_reviews()
    out = []
    for model, q in RUNS:
        os.environ["IGNIS_LLM_MODEL"] = model
        try:
            r = ask(q)
        except Exception as e:  # noqa: BLE001 - a failed run is recorded as failed, not hidden
            r = {"ok": False, "answer": None, "reason": f"run failed: {e}", "calls": []}
        out.append({"model": model, "question": q, "ok": r["ok"], "answer": r.get("answer"), "reason": r.get("reason"),
                    "review": None,
                    "calls": [{"tool": c["tool"], "args": c["args"], "result": _short(c["result"])} for c in r["calls"]]})
        print(("OK " if r["ok"] else "REFUSED ") + model + " | " + q[:60] + " | " + str(r.get("reason") or "")[:80])
    notes = json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else {}
    for row in out:
        key = f"{row['model']}|{row['question']}"
        if key in notes and notes[key].get("answer_starts") and (row["answer"] or "").startswith(notes[key]["answer_starts"]):
            row["review"] = notes[key]["note"]   # only attach if the reviewed answer is the one recorded
    OUT.write_text(json.dumps({"recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                               "runtime": "Ollama on a local machine (no cloud API, no keys)",
                               "guard": "Any number in an answer that is not in a tool result gets the answer refused.",
                               "runs": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
