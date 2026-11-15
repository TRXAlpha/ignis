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


def test_numbers_from_tool_descriptions_are_not_flagged(monkeypatch):
    import analyst.tools as t
    monkeypatch.setitem(t.TOOLS, "p_burns", lambda **k: {"status": "insufficient_data"})
    call = {"tool_calls": [{"id": "1", "function": {"name": "p_burns", "arguments": '{"o2_percent": 34}'}}]}
    r = ask("q", chat=_fake_llm([call, {"content": "Give a flow for the 6.35-mm rod first."}]))
    assert r["ok"], r


def test_guard_holes_closed():
    ev = ['{"min_o2_percent_p50": 13.62, "page": 84, "p_burns": 0.136}']
    assert unsupported_numbers("PMMA keeps burning down to 9 percent oxygen.", ev) == [9.0]   # small number with a unit
    assert unsupported_numbers("The margin is -500.", ev) == [-500.0]                         # negatives are not "small"
    assert unsupported_numbers("The limit is 1362 percent.", ev) == [1362.0]                  # no x100 on non-fractions
    assert unsupported_numbers("It called 2 tools; P(burns) is 13.6 %.", ev) == []            # counts and fractions-as-percent


def test_every_tool_is_offered_to_the_model():
    from analyst.tools import SCHEMAS, TOOLS
    assert {s["function"]["name"] for s in SCHEMAS} == set(TOOLS)
