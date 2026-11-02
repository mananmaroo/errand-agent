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
| cancel_transient_503_retry | 503 then retry with SAME key -> cancelled, verified | cancel keys=['f16164e775e4b93b', 'f16164e775e4b93b'], status=['cancelled'] | PASS | invariants ok |
| cancel_requires_approval | no cancel call without explicit yes | cancel calls=0 | PASS | invariants ok |
| reschedule_same_provider | moved to Saturday, same provider, verified | bookings=[('A-301', '2026-11-07T08:00')] | PASS | invariants ok |
| reschedule_slot_conflict | conflict -> void, re-propose another slot, only moves after new yes | reschedule calls=['2026-11-07T08:00', '2026-11-07T14:00'], final=['2026-11-07T14:00'] | PASS | invariants ok |
| reschedule_conflict_no_alternative | conflict + no other slot -> clear msg, booking unchanged | final=['2026-11-02T11:00'], phase=FAILED | PASS | invariants ok |
| ambiguous_booking_asks_which | two plumber bookings -> asks; ID picks the right one | cancelled=['B-0002'] | PASS | invariants ok |
| memory_persists_across_sessions | area stated in session 1 reused in session 2 without asking | area fact={'value': 'koramangala', 'source': 'stated', 'updated_at': 0.0}, last reply='I can book AquaCare (P-103) on 2026-11-0' | PASS | invariants ok |
| memory_view_marks_source | view shows stated vs inferred | Here's what I remember: / - area: koramangala [stated] / - preferred technician (electrician): E-201 [inferred | PASS | invariants ok |
| memory_correction | 'actually I'm in HSR' overwrites stated area, keeps other facts | area=hsr, earliest=10 | PASS | invariants ok |
| memory_forget_never_reused | forgotten area not used next session -> asks again | area fact=None, last='Which area are you in (Koraman' | PASS | invariants ok |
| inferred_needs_confirmation | inferred technician asked about, not used silently | last='Last time you used E-201 for this. Want them ', holds after=1 | PASS | invariants ok |
| inferred_confirmed_becomes_stated | yes -> inferred promoted to stated, proposal uses it | fact={'value': 'E-201', 'source': 'stated', 'updated_at': 5.0}, proposal=E-201 | PASS | invariants ok |
| forgotten_inferred_not_reinferred | forget technician -> later booking doesn't re-infer it | fact=None, replies=5 | PASS | invariants ok |
| same_as_last_time | 'same electrician as last time, not before 10' -> E-202, hour>=10 | proposal=Proposal(action='book', provider_id='E-202', slot='2026-11-02T10:00', price=1100, booking_id=None) | PASS | invariants ok |
| restart_after_server_committed | crash after commit -> resume finds booked, 0 extra book calls | book calls=1, bookings=1, resume reply='Booked ✅ E-201 on 2026-11-02 a' | PASS | invariants ok |
| restart_before_commit_in_window | crash before commit, resume <30s -> same-key retry, 1 booking | book keys=['e297cefa91c12f74', 'e297cefa91c12f74'], bookings=1 | PASS | invariants ok |
| restart_before_commit_after_window | crash, down 120s -> no retry, voided, asks re-approval | book calls=1, phase=AWAITING_APPROVAL | PASS | invariants ok |
| memory_question_cannot_capture_approval | unanswered memory Q expires; booking 'yes' books and does NOT promote inferred fact (BUG-3 regression) | fact=inferred, bookings=2 | PASS | invariants ok |

**36/36 passed**
