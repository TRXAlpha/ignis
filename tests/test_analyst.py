import json

from analyst.__main__ import ask, unsupported_numbers


def test_guard_rejects_invented_numbers():
    ev = ['{"min_o2_percent_p50": 13.62, "band_percent": [13.1, 14.0]}']
    assert unsupported_numbers("Minimum is 13.62 % (13.1-14.0 %).", ev) == []
    assert unsupported_numbers("Minimum is 12.9 %.", ev) == [12.9]


def _fake_llm(script):
    it = iter(script)
    return lambda messages: next(it)


def test_answer_without_tools_refused():
    r = ask("min o2?", chat=_fake_llm([{"content": "It is 13.5 %."}]))
    assert not r["ok"] and "without calling" in r["reason"]


def test_tool_then_answer_and_fabrication_caught(monkeypatch):
    import analyst.tools as t
    monkeypatch.setitem(t.TOOLS, "min_o2", lambda: {"min_o2_percent_p50": 13.62})
    call = {"tool_calls": [{"id": "1", "function": {"name": "min_o2", "arguments": "{}"}}]}
    ok = ask("q", chat=_fake_llm([call, {"content": "About 13.62 % O2."}]))
    assert ok["ok"] and ok["calls"][0]["result"] == {"min_o2_percent_p50": 13.62}
    bad = ask("q", chat=_fake_llm([call, {"content": "About 11.8 % O2."}]))
    assert not bad["ok"] and "11.8" in bad["reason"]
