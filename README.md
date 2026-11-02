# Errand Agent

A chat agent that books, reschedules and cancels home-service errands against a mocked provider API. It never double-books, never acts without approval, and never gets talked into anything by a provider review. Everything runs locally and offline. No API key is needed.

## Run it (3 commands)

```bash
pip install -e ".[dev]"          # Python ≥3.10, no runtime deps
pytest                           # 36 eval scenarios + trace tests; writes reports/eval_table.md
python -m errand_agent.cli       # chat (try --world timeout | price | timeout_lost | random)
```

To watch the trace live, run this in a second terminal pane:

```bash
python -m errand_agent.view traces/demo.jsonl --follow
```

In the chat, `/restart` simulates a process restart (state and memory survive it) and `/quit` exits. Things to try:

- *Find a plumber for my kitchen tap this week, mornings only, under ₹1,500*
- *Move my AC servicing to Saturday* (book an AC service first)
- *Book the same electrician as last time, but not before 10 a.m.*
- *what do you remember* · *forget my area* · *actually I'm in HSR*

## Layout

| Path | What |
|---|---|
| `src/errand_agent/mocks.py` | Mock provider world implementing the fixed tool contract. Uses seeded randomness, with scenario knobs to force outcomes. |
| `src/errand_agent/agent.py` | The agent loop: the state machine, approval gate, idempotent execution, recovery and limits. |
| `src/errand_agent/state.py` | Workflow state and the `Approval` / `Proposal` records, saved with atomic writes. |
| `src/errand_agent/memory.py` | Stated/inferred memory with view, correct and forget (plus the forget block list). |
| `src/errand_agent/model.py` | `ScriptedModel`: a deterministic parser that turns text into intent and slots. A live LLM can be swapped in here. |
| `src/errand_agent/trace.py` | JSONL tracer with sanitisation, review redaction and turn summaries. |
| `src/errand_agent/evals.py` | 36 scripted-user scenarios plus global invariants. Generates the eval table. |
| `docs/DESIGN.md` | Design note. |
| `docs/BUGS.md` | Three real bugs and their regression tests. |
| `docs/timeout_after_success_e2e.jsonl` | Raw end-to-end trace that includes a timeout-after-success. |
| `reports/eval_table.md` | Generated eval table. |

## Decisions on ambiguities

- **Price change voids approval:** any difference between the search price and the hold quote, up or down, voids the approval and the agent asks again at the quoted price.
- **Retry after a timeout:** the agent always checks `get_booking_status` first. A `not_found` result is retried with the same key only within 30 s of approval. After that, the agent asks for approval again.
- **Reschedule keeps the same technician.** On a conflict it proposes that provider's next free slot. If none is left, the booking stays unchanged.
- **What counts as a stated fact:** area and earliest time are saved as stated when the user says them. A preferred technician is stated only when named or confirmed; otherwise it's inferred and the agent asks before using it.
- **Forget blocks re-inference** of that key until the user states it again.
- **"This week"** maps to a fixed mock week, 2026-11-02 to 2026-11-07, so tests are stable.

## Nice-to-have

Not attempted. I spent the time on the must-haves and their tests, as the brief suggested. Next I would do **model routing**: the `parse()` seam already exists, and the eval suite would measure quality, latency and cost for each model.
