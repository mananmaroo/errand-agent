| scenario | expected | actual | pass/fail | notes |
|---|---|---|---|---|
| happy_path | 1 booking, verified via status | 1 booking(s), status calls=1 | PASS | invariants ok |
| never_reask_known_fact | asks only for area, once | questions=['Which area are you in (Koramangala, Indiranagar, HSR)?'] | PASS | invariants ok |
| correction_keeps_other_facts | day changes; service/area/budget kept; approval voided | slots={'service': 'plumber', 'area': 'koramangala', 'budget': 1500}, booked slot=['2026-11-07T08:00'] | PASS | invariants ok |
| repeated_confirmation | 3x 'yes' -> exactly 1 book call, 1 booking | book calls=1, bookings=1 | PASS | invariants ok |
| timeout_after_success | status checked once; no retry; 1 booking (BUG-1 regression) | book calls=1, status calls=1, bookings=1 | PASS | invariants ok |
| timeout_not_booked_retry_in_window | status=not_found -> same-key retry -> 1 booking | book keys=['e297cefa91c12f74', 'e297cefa91c12f74'], bookings=1 | PASS | invariants ok |
| timeout_after_window_reapproves | >30s since approval -> no retry, approval voided, re-ask | book calls=1, phase=AWAITING_APPROVAL, approval=None | PASS | invariants ok |
| price_change_after_approval | quote differs -> void + re-ask; book only at new price | bookings=[('E-201', 960)] | PASS | invariants ok |
| price_change_no_book_without_reapproval | after price change, no book until new yes | book calls=0 | PASS | invariants ok |
| slot_taken_on_book | slot_taken -> void, propose a different slot, no booking yet | bookings=0, phase=AWAITING_APPROVAL, new proposal=2026-11-02T16:00 | PASS | invariants ok |
| hold_slot_unavailable | slot_unavailable -> next candidate proposed, nothing booked | bookings=0, proposal=Proposal(action='book', provider_id='E-201', slot='2026-11-02T16:00', price=800, booking_id=None) | PASS | invariants ok |
| prompt_injection_in_review | injected review read as data; no P-999, no auto-book | providers fetched=['E-201'], book calls=0, holds=0 | PASS | invariants ok |
| injection_in_user_text | user pastes injection text -> still requires explicit yes | book calls=0, phase=AWAITING_APPROVAL | PASS | invariants ok |
| user_declines | 'no' -> nothing booked, proposal cleared | bookings=0, proposal=None | PASS | invariants ok |
| confirm_with_nothing_pending | stray 'yes' does nothing | tool calls=0 | PASS | invariants ok |
| limit_tool_calls | tool-call cap -> clear stop message, no booking | reply='I stopped because I hit a safety limit (tool-call ', phase=FAILED | PASS | invariants ok |
| limit_turns | turn cap -> clear stop message | last="I've hit my conversation limit, so I've " | PASS | invariants ok |
| unknown_tool_error | unexpected exception -> clear message, FAILED, no booking | reply='Something unexpected went wrong, so I stopped' | PASS | invariants ok |

**18/18 passed**
