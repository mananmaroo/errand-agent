# Errand Agent — Design Note

**Core idea:** the language model is only a *parser*. It turns a user message into `{intent, slots}`. Code owns state, approval and every side effect. The offline evals use a deterministic `ScriptedModel`. A live LLM would sit behind the same `parse()` interface, and its output would be treated as suggestions, never as permission.

## 1. State model

`WorkflowState` (`state.py`) is an explicit, persisted record:

```
COLLECTING → AWAITING_APPROVAL → EXECUTING → DONE
      ↑            │  any change to provider/slot/price voids approval
      └────────────┘                         └→ FAILED (always with a user message)
```

- **Slots:** `service, area, date_range` are required. `budget, earliest/latest hour, preferred provider, booking_id` are optional. The agent asks only for the first missing *required* slot, so a known fact is never asked for twice. A correction changes only the slots it names (`{k: v for k, v in parse.slots if changed}`). If a proposal was pending, the correction voids it and its approval.
- **Persistence:** the state is written to disk after every transition with an atomic write (`tmp` file then `replace`). A new request after `DONE`/`FAILED` starts a fresh workflow, so old slots can't leak into it.

## 2. Approval enforcement

An `Approval` is a frozen record `(action, provider_id, slot, price, booking_id, approved_at)`. It can only be created in `_on_confirm()`: the user's message must parse as an explicit yes, and there must be a pending `Proposal`. Neither the model nor tool output can create one.

Before **every** side-effecting call, code compares the approval to what is about to happen:

- **`book`:** the approval must equal the live hold `(provider, slot, quoted_price)`. If the price quoted at hold time differs from the approved price, up *or* down, the approval is voided and the agent asks again at the new price. The hold is kept (10-minute TTL).
- **`cancel` / `reschedule`:** `_gate()` checks `approval.matches(proposal)`, including the `booking_id` and the new slot.
- A test-side invariant (INV-1), checked on every scenario, replays the trace and fails the run if any `book`/`cancel`/`reschedule` call lacks a matching live approval.

**Untrusted output.** Provider reviews are fetched, but no code path reads review text. Ranking uses only typed fields (`rating`, `price`, `free_slots`). Traces replace reviews with `<n reviews redacted>`. Since the model only parses *user* text, an injection in a review can't reach it. If a user pastes injection text into their own message, the agent still requires an explicit "yes" (eval `injection_in_user_text`).

## 3. Idempotency and recovery

- **Write-ahead key.** The idempotency key is `sha256(user|action|provider|slot|price|approved_at)`. It's saved together with `phase=EXECUTING` *before* `book` is called. So the same approval always gives the same key, even across a restart, and the mock server deduplicates on it.
- **Timeouts.** After a timeout the agent always calls `get_booking_status(key)` first. That status is the authoritative answer:
  - `booked`: report success.
  - `failed`: treat the slot as lost, void the approval and re-propose.
  - `not_found`: retry with the **same key**, but only if less than **30 s** have passed since approval and the attempt cap allows it. Otherwise void the approval and ask again. *(Ambiguity resolved: an approval older than 30 s is considered stale for a blind retry.)*
- **No success until verified.** Success is reported only after a status check (for `book`) or a `list_bookings` read-back (for `cancel`/`reschedule`).
- **Restarts.** On startup, `Agent.resume()` checks for `phase=EXECUTING` with a saved key and reconciles through the status check. The evals simulate a crash with a `BaseException` (`ProcessCrash`), so the agent's catch-all handler can't swallow it, both before and after the server commits.
- **Cancel 503.** Retried up to 3 times with the same key.
- **Reschedule conflict.** The rejected slot is recorded, the approval voided, and the *same provider's* next free slot is proposed. If there isn't one, the booking stays unchanged and the agent says so.

**Bounds.** Each turn has a cap of 12 tool calls and 60 s of simulated wall-clock time. There's a cap on turns per session and a cap of 2 booking attempts. Hitting any limit, or any unexpected exception, ends in `FAILED` with a message that also states what *was* or *wasn't* booked.

## 4. Memory

`memory.json` is stored per user, separate from workflow state. Each fact is `{value, source: stated|inferred, updated_at}`.

- **Stated** facts are things the user said: area, earliest time, a technician they named, or one they confirmed. Stated facts fill missing slots, and each use is logged as `memory_used`.
- **Inferred** facts come from successful bookings (preferred provider per service). They are **never used silently**. The agent asks "Want them again?", and only a yes promotes the fact to stated. An unanswered question expires (see BUG-3).
- **Forget** deletes the fact *and* adds its key to a block list, so it can't be re-inferred from history. If the user explicitly states it again later, the block is lifted.

## 5. Observability

There is one JSONL trace per run (`traces/<run>.jsonl`). Event kinds:

- `model`: intent, slots, tokens
- `state`: phase transitions, with the reason
- `tool`: name, args, sanitised result or error, latency
- `approval`, `approval_void`, `retry`, `resume`, `memory_*`
- `turn_summary`: per-tool counts, errors, latency, tokens, cost

Keys that look like secrets are masked and long strings are truncated. `python -m errand_agent.view <trace> --follow` renders the trace live.

**Annotated excerpt: timeout-after-success** (`docs/timeout_after_success_e2e.jsonl`):

```
APPROVE book E-202 2026-11-02T10:00 ₹1100        ← user's explicit "yes"; record created
hold_slot(E-202, 10:00) → quoted ₹1100           ← quote == approved price → gate passes
STATE AWAITING_APPROVAL → EXECUTING               ← key 046c99… persisted BEFORE book
book(H-0001, key=046c99…) ✗ ToolTimeout          ← ambiguous: did it book?
get_booking_status(046c99…) → booked, B-0002      ← ask the source of truth; do NOT retry
STATE EXECUTING → DONE                            ← success claimed only now
(user: "yes" again) → "Already done — B-0002"     ← no second book call
```

The turn summary shows `get_booking_status: 1`. Before BUG-1 was fixed, this path called it twice.

## 6. Evals

There are 36 scripted-user scenarios (`evals.py`). They run offline against `ScriptedModel`, with a seeded `World` and a simulated `Clock`. They assert *outcomes*, not wording: booking counts, `call_log` arguments, idempotency keys, memory sources and the final phase. They also check four invariants on every run:

- no side effect without a valid approval
- no duplicate bookings
- no "Booked" claim without a real booking
- no empty reply

The suite was *mutation-checked*: removing the approval gate, the status check before retry, the write-ahead save, `resume()`, or each bug fix turns specific scenarios red. `reports/eval_table.md` is generated by the run.

## 7. What breaks first at 100×, and what I'd change

1. **The single JSON state file.** Two devices, or two tabs, can race on one workflow. Both could read `AWAITING_APPROVAL`, both see "yes", and both call `book`. The server-side key saves us *only* if both derive the same `approved_at`, and they won't. **Change:** move workflow state into Postgres with a row lock or a version column (compare-and-swap) on each transition, and make "approve" a single conditional update. Use an outbox table instead of in-process side effects.
2. **The status endpoint becomes the hot path.** Every timeout produces at least one status read, and at 100× providers time out *more*, not less. **Change:** stagger reconciliation with backoff and jitter, and prefer webhook or event confirmation from providers where available.
3. **The fixed 30 s retry window** was a sensible guess. At scale, retry safety depends on measured `book` latency per provider. **Change:** derive the window from p99 latency plus the hold TTL, configured per provider, and alert when the share of `not_found`-after-timeout rises.
4. **A scripted parser doesn't cover real phrasing.** **Change:** put a live LLM extractor behind `parse()` with a strict JSON schema. Make this eval suite, plus recorded real conversations, its regression gate. Route easy turns ("yes", "no", IDs) to rules or a cheap model and hard ones to a stronger model. The approval and execution layers stay unchanged, because they never trust the parser.
5. **Memory needs governance.** Add per-fact TTLs, an audit log of every promote and forget, and PII handling for addresses.
