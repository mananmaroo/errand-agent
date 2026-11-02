# Three real bugs found while building

## BUG-1: Duplicate status checks after a timeout

- **What broke:** on a `book` timeout where the server *had* booked, the agent called `get_booking_status` twice.
- **Why:** the reconcile step saw `booked` and then handed off to `_verify()`, which runs its own status check. The behaviour was correct but the work was doubled. At 100× that doubles load on the endpoint that is already the hot path during provider incidents.
- **Fix:** I split out `_confirmed(status)`. Reconcile now finishes from the status it already has.
- **Regression test:** `timeout_after_success` asserts exactly one `get_booking_status` call and one `book` call.

## BUG-2: A forgotten fact came back after a restart

- **What broke:** "forget my area" removed the fact from memory, but in the next session the agent searched with `area=koramangala` anyway.
- **Why:** `_forget()` cleared the area from the workflow slots in memory but never saved the workflow state. The next session loaded the old `state.json`, which still had the slot. The forgotten fact came back through the workflow state rather than through memory, which breaks "forgotten facts are never reused".
- **Fix:** `_forget()` now saves the state, voids any proposal built from the fact, and returns to `COLLECTING`.
- **Regression test:** `memory_forget_never_reused` runs two sessions and asserts that the agent asks for the area again. It was mutation-checked: removing the save turns it red.

## BUG-3: A pending memory question captured the booking approval

- **What broke:**
  1. The agent asked "Last time you used E-201. Want them again? (yes/no)".
  2. The user replied with a constraint instead ("not before 10").
  3. On the next turn the user said "yes" **to the booking proposal**.
  4. That "yes" was routed to the still-pending memory question. E-201 was promoted from *inferred* to *stated* without the user ever confirming it, and the booking confirmation was swallowed.
- **Why:** `pending_memory` stayed set until a yes or no arrived, however many turns passed or other questions were asked in between.
- **Fix:** a pending question expires as soon as the user says anything else. The expiry is logged as `memory_confirm accepted=null why=unanswered`.
- **Regression test:** `memory_question_cannot_capture_approval` asserts that the fact stays `inferred` and that the booking goes through. It was mutation-checked.

*(Not a bug: I first suspected that repeated `get_provider` calls on re-proposals could exhaust the 12-call cap partway through a turn. I measured it: every slot-taken cycle uses exactly 4 calls and the agent stops to ask, so the cap can't be reached that way.)*
