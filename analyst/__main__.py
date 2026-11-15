"""IGNIS analyst: a local LLM that may only answer through tool calls.

python -m analyst "What is the minimum O2 for PMMA to burn in microgravity?"
python -m analyst --tool p_burns o2_percent=16 flow_cm_s=5        # call a tool directly, no LLM

LLM: any OpenAI-compatible endpoint with tool calling. Default is local Ollama.
  IGNIS_LLM_URL   (default http://localhost:11434/v1)
  IGNIS_LLM_MODEL (default gemmaclaude:latest)
  IGNIS_LLM_KEY   (optional bearer token; never commit it)

Guard: every number in the final answer must appear in a tool result or in the question.
Otherwise the answer is refused and the tool results are printed instead.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

from .tools import SCHEMAS, TOOLS

SYSTEM = ("You are the IGNIS analyst for microgravity fire safety. You know NOTHING except what tools return. "
          "Always call tools before answering. Never state a number that is not in a tool result. "
          "If a tool says insufficient_data or extrapolation, say so plainly. Cite sources (title + page) from tool "
          "results when you give a number. Be brief.")
NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
# a number followed by one of these is a measurement, never a list rank or a count
UNIT = re.compile(r"\s*(?:%|percent\b|°|1/s|(?:mm|cm|m|kpa|pa|psia?|atm|s|k|g|nats?)\b)", re.I)


def _numbers(text: str) -> set[float]:
    return {float(m) for m in NUM.findall(text)}


def unsupported_numbers(answer: str, evidence: list[str]) -> list[float]:
    """Numbers in the answer not found (to 2 significant rounding) in any tool output or the question.

    Known limit: it matches values, not meaning, so a number that appears in the evidence for another reason
    (a page number, a count) still passes. That is why recorded answers also carry a human review note."""
    pool = set()
    for e in evidence:
        for v in _numbers(e):
            pool |= {v, round(v, 1), round(v, 2), round(v)}
            if abs(v) <= 1:  # fractions are shown as percent (0.136 -> 13.6); never scale anything else
                pool |= {round(v * 100, 1), round(v * 100), round(v * 100, 2)}
    bad = []
    for m in NUM.finditer(answer):
        v = float(m.group())
        if v in pool or round(v, 1) in pool:
            continue
        # small counts and list ranks ("2 tools", "1." ) are fine; a small number with a unit is a claim
        if v.is_integer() and 0 <= v <= 10 and not UNIT.match(answer, m.end()):
            continue
        bad.append(v)
    return bad


def _chat(messages: list[dict]) -> dict:
    url = os.environ.get("IGNIS_LLM_URL", "http://localhost:11434/v1").rstrip("/") + "/chat/completions"
    body = {"model": os.environ.get("IGNIS_LLM_MODEL", "gemmaclaude:latest"), "messages": messages, "tools": SCHEMAS,
            "temperature": 0}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    if os.environ.get("IGNIS_LLM_KEY"):
        req.add_header("Authorization", f"Bearer {os.environ['IGNIS_LLM_KEY']}")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["choices"][0]["message"]


def ask(question: str, chat=_chat, max_steps: int = 6) -> dict:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    # the model also sees the tool descriptions (e.g. '6.35-mm rod'), so numbers from them are not invented
    evidence, calls = [question] + [t["function"]["description"] or "" for t in SCHEMAS], []
    for _ in range(max_steps):
        msg = chat(messages)
        tcs = msg.get("tool_calls") or []
        if not tcs:
            answer = (msg.get("content") or "").strip()
            if not calls:
                return {"ok": False, "answer": None, "reason": "model answered without calling any tool", "calls": calls}
            bad = unsupported_numbers(answer, evidence)
            if bad:
                return {"ok": False, "answer": answer, "reason": f"numbers not in any tool result: {bad}", "calls": calls}
            return {"ok": True, "answer": answer, "calls": calls}
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tcs})
        for tc in tcs:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
                out = TOOLS[name](**args) if name in TOOLS else {"error": f"unknown tool {name}"}
            except Exception as e:  # noqa: BLE001 - report tool errors to the model, don't crash
                out = {"error": str(e)}
            s = json.dumps(out, ensure_ascii=False)
            evidence.append(s)
            calls.append({"tool": name, "args": tc["function"].get("arguments"), "result": out})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", name), "content": s})
    return {"ok": False, "answer": None, "reason": "too many tool steps", "calls": calls}


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--tool"]:
        kw = {}
        for a in argv[2:]:
            k, _, v = a.partition("=")
            try:
                kw[k] = float(v)
            except ValueError:
                kw[k] = v
        print(json.dumps(TOOLS[argv[1]](**kw), indent=1, ensure_ascii=False))
        return 0
    res = ask(" ".join(argv))
    if res["ok"]:
        print(res["answer"])
    else:
        print(f"[refused] {res['reason']}")
        if res.get("answer"):
            print(f"[unsupported draft] {res['answer']}")
    for c in res["calls"]:
        print(f"  tool {c['tool']}({c['args']}) -> {json.dumps(c['result'], ensure_ascii=False)[:300]}")
    return 0 if res["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
