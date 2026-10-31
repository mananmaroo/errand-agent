import pytest

from errand_agent.evals import EVALS, invariants, play, run_all, write_table


@pytest.mark.parametrize("ev", EVALS, ids=lambda e: e.name)
def test_scenario(ev, tmp_path):
    r = play(ev, tmp_path)
    actual, ok = ev.check(r)
    assert ok, f"{ev.name}: expected {ev.expected!r}, got {actual!r}"
    assert not invariants(r), invariants(r)


def test_eval_table_generated(tmp_path):
    rows = run_all(tmp_path)
    assert len(rows) >= 15
    assert write_table(rows).exists()
