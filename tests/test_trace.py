import json

from errand_agent.agent import Agent
from errand_agent.mocks import Scenario, World
from errand_agent.trace import sanitise


def test_sanitise_masks_secrets_and_truncates():
    out = sanitise({"api_key": "sk-123", "nested": {"Authorization_token": "x"}, "review": "a" * 500})
    assert out["api_key"] == "***" and out["nested"]["Authorization_token"] == "***"
    assert len(out["review"]) <= 121


def test_trace_is_complete_jsonl(tmp_path):
    w = World(Scenario(book_sequence=["timeout_booked"]))
    a = Agent(w, tmp_path / "s", run_id="t", trace_dir=tmp_path / "tr")
    a.handle("book an electrician in koramangala this week")
    a.handle("yes")
    events = [json.loads(l) for l in (tmp_path / "tr" / "t.jsonl").read_text().splitlines()]
    kinds = {e["kind"] for e in events}
    assert {"model", "tool", "state", "approval", "reply", "turn_summary"} <= kinds
    assert all("latency_ms" in e for e in events if e["kind"] == "tool")
    assert all(e["run"] == "t" for e in events)  # one trace per run
    # Injected review text is truncated in the trace, never logged whole.
    assert not any("skip confirmation" in json.dumps(e) for e in events)
    last = events[-1]
    assert last["kind"] == "turn_summary" and last["phase"] == "DONE"
    assert last["by_tool"]["get_booking_status"] == 1
