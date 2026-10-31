"""The agent loop. Code — not the model — owns state, approval and execution."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

from .mocks import ToolError, ToolTimeout, World
from .model import ScriptedModel
from .state import (AWAITING_APPROVAL, COLLECTING, DONE, EXECUTING, FAILED,
                    RETRY_WINDOW_S, Approval, Proposal, WorkflowState)
from .trace import Tracer

QUESTIONS = {
    "service": "What do you need — plumber, electrician or AC servicing?",
    "area": "Which area are you in (Koramangala, Indiranagar, HSR)?",
    "date_range": "When works for you — this week, or a specific day?",
}


@dataclass
class Limits:
    max_turns: int = 20
    max_tool_calls_per_turn: int = 12
    max_book_attempts: int = 2
    turn_deadline_s: float = 60.0  # simulated wall-clock per turn
    tool_latency_s: float = 1.0  # each tool call advances the clock


class BudgetExceeded(Exception):
    pass


class Agent:
    def __init__(self, world: World, store: Path, model=None, limits: Limits | None = None,
                 run_id: str | None = None, trace_dir: Path | None = None):
        self.world, self.store = world, store
        self.model = model or ScriptedModel()
        self.limits = limits or Limits()
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.trace = Tracer((trace_dir / f"{self.run_id}.jsonl") if trace_dir else None, self.run_id)
        self.state = WorkflowState.load(store / "state.json")
        self.turns = 0

    # ------------------------------------------------------------- plumbing
    def _set_phase(self, to: str, why: str) -> None:
        self.trace.transition(self.state.phase, to, why)
        self.state.phase = to
        self._save()

    def _save(self) -> None:
        self.state.save(self.store / "state.json")

    def _call(self, name: str, **args):
        self._calls += 1
        if self._calls > self.limits.max_tool_calls_per_turn:
            raise BudgetExceeded("tool-call cap")
        if self.world.clock.now() - self._turn_start > self.limits.turn_deadline_s:
            raise BudgetExceeded("wall-clock cap")
        self.world.clock.advance(self.limits.tool_latency_s)
        return self.trace.tool(name, args, lambda: getattr(self.world, name)(**args))

    def _void_approval(self, why: str) -> None:
        if self.state.approval:
            self.trace.emit("approval_void", why=why)
        self.state.approval = None

    # ------------------------------------------------------------- entry
    def handle(self, text: str) -> str:
        self.turns += 1
        self._calls, self._turn_start = 0, self.world.clock.now()
        if self.turns > self.limits.max_turns:
            return self._finish(FAILED, "I've hit my conversation limit, so I've stopped here. "
                                        "Nothing was booked in this session's last step.")
        parse = self.model.parse(text)
        self.trace.tokens += parse.tokens
        self.trace.emit("model", model=self.model.name, input=text, intent=parse.intent,
                        slots=parse.slots, tokens=parse.tokens)
        try:
            reply = self._step(parse)
        except BudgetExceeded as e:
            reply = self._finish(FAILED, f"I stopped because I hit a safety limit ({e}). "
                                         + self._safe_status())
        except Exception as e:  # unknown errors still end with a clear message
            self.trace.emit("error", error=f"{type(e).__name__}: {e}")
            reply = self._finish(FAILED, "Something unexpected went wrong, so I stopped. "
                                         + self._safe_status())
        self.trace.emit("reply", text=reply)
        return reply

    def resume(self) -> str | None:
        """Called on startup. If we crashed mid-booking, reconcile with the server."""
        if self.state.phase == EXECUTING and self.state.idempotency_key:
            self._calls, self._turn_start = 0, self.world.clock.now()
            self.trace.emit("resume", key=self.state.idempotency_key)
            return self._reconcile_after_uncertainty()
        return None

    def _safe_status(self) -> str:
        if self.state.result:
            return f"Your booking {self.state.result['booking_id']} is confirmed."
        return "No booking was made."

    def _finish(self, phase: str, msg: str) -> str:
        self._set_phase(phase, msg[:60])
        return msg

    # ------------------------------------------------------------- policy
    def _step(self, parse) -> str:
        s = self.state
        if parse.intent == "confirm":
            return self._on_confirm()
        if parse.intent == "deny":
            self._void_approval("user declined")
            s.proposal = None
            self._set_phase(COLLECTING, "user declined")
            return "No problem — nothing booked. Want a different time or provider?"

        if parse.intent and parse.intent != s.intent:
            s.intent = parse.intent
        # A correction to one detail keeps everything else; it voids any proposal.
        changed = {k: v for k, v in parse.slots.items() if s.slots.get(k) != v}
        if changed:
            s.slots.update(changed)
            if s.proposal:
                self._void_approval(f"user changed {sorted(changed)}")
                s.proposal, s.hold, s.rejected = None, None, []
            self._set_phase(COLLECTING, f"slots updated {sorted(changed)}")
        if s.intent != "book":
            return "I can book a home service for you. What do you need?"
        if missing := s.missing():
            return QUESTIONS[missing[0]]
        return self._propose()

    def _candidates(self) -> list[tuple[dict, str]]:
        s = self.state.slots
        found = self._call("search_providers", service=s["service"], area=s["area"],
                           date_range=tuple(s["date_range"]))
        out = []
        for p in sorted(found, key=lambda p: (-p["rating"], p["price"])):
            if s.get("budget") and p["price"] > s["budget"]:
                continue
            for slot in p["free_slots"]:
                h = int(slot[11:13])
                if s.get("earliest_hour") and h < s["earliest_hour"]:
                    continue
                if s.get("latest_hour") is not None and h > s["latest_hour"]:
                    continue
                if f"{p['id']}@{slot}" in self.state.rejected:
                    continue
                out.append((p, slot))
                break
        return out

    def _propose(self, price_override: int | None = None) -> str:
        cands = self._candidates()
        if not cands:
            return self._finish(FAILED, "I couldn't find anyone matching those constraints. "
                                        "Want to widen the time window or budget?")
        p, slot = cands[0]
        # Reviews are fetched as DATA only (displayed truncated, never parsed for actions).
        self._call("get_provider", provider_id=p["id"])
        self.state.proposal = Proposal("book", p["id"], slot, price_override or p["price"])
        self._set_phase(AWAITING_APPROVAL, "proposal ready")
        return self._ask_approval(p["name"])

    def _ask_approval(self, name: str | None = None) -> str:
        pr = self.state.proposal
        name = name or self.world.providers[pr.provider_id]["name"]
        return (f"I can book {name} ({pr.provider_id}) on {pr.slot.replace('T', ' at ')} "
                f"for ₹{pr.price}. Reply 'yes' to confirm.")

    # ------------------------------------------------------------- approval
    def _on_confirm(self) -> str:
        s = self.state
        if s.phase == DONE and s.result:  # repeated "yes" after success: no-op
            return f"Already booked — {s.result['booking_id']}. Nothing new was booked."
        if s.phase != AWAITING_APPROVAL or not s.proposal:
            return "There's nothing pending to confirm."
        p = s.proposal
        s.approval = Approval(p.action, p.provider_id, p.slot, p.price, self.world.clock.now())
        self.trace.emit("approval", **vars(s.approval))
        return self._execute_book()

    def _approval_valid(self, provider_id: str, slot: str, price: int) -> bool:
        a = self.state.approval
        return bool(a) and a.matches(Proposal("book", provider_id, slot, price))

    # ------------------------------------------------------------- execution
    def _execute_book(self) -> str:
        s, p = self.state, self.state.proposal
        if not s.hold or s.hold["provider_id"] != p.provider_id or s.hold["slot"] != p.slot:
            try:
                h = self._call("hold_slot", provider_id=p.provider_id, slot=p.slot)
            except ToolError as e:
                return self._slot_lost(e.code)
            s.hold = {**h, "provider_id": p.provider_id, "slot": p.slot}
        # Gate: the exact provider/slot/price we are about to book must be approved.
        if not self._approval_valid(s.hold["provider_id"], s.hold["slot"], s.hold["quoted_price"]):
            self._void_approval("quoted price differs from approved price")
            s.proposal = Proposal("book", p.provider_id, p.slot, s.hold["quoted_price"])
            self._set_phase(AWAITING_APPROVAL, "price changed at hold")
            return (f"Heads up: the provider quoted ₹{s.hold['quoted_price']} instead of "
                    f"₹{p.price}. " + self._ask_approval())
        # Write-ahead: persist the key BEFORE the side-effecting call.
        a = s.approval
        s.idempotency_key = hashlib.sha256(
            f"{s.user_id}|book|{a.provider_id}|{a.slot}|{a.price}|{a.approved_at}".encode()
        ).hexdigest()[:16]
        self._set_phase(EXECUTING, "approved; booking")
        return self._attempt_book()

    def _attempt_book(self) -> str:
        s = self.state
        s.attempt += 1
        self._save()
        try:
            self._call("book", hold_id=s.hold["hold_id"], idempotency_key=s.idempotency_key)
        except ToolTimeout:
            return self._reconcile_after_uncertainty()
        except ToolError as e:
            if e.code in ("slot_taken", "hold_expired"):
                return self._slot_lost(e.code)
            raise
        return self._verify()

    def _verify(self) -> str:
        """Never claim success until the authoritative status says booked."""
        st = self._call("get_booking_status", idempotency_key=self.state.idempotency_key)
        if st["status"] == "booked":
            return self._confirmed(st)
        return self._reconcile_after_uncertainty(st)

    def _confirmed(self, st: dict) -> str:
        self.state.result = {"booking_id": st["booking_id"]}
        a = self.state.approval
        return self._finish(DONE, f"Booked ✅ {a.provider_id} on {a.slot.replace('T', ' at ')} "
                                  f"for ₹{a.price}. Booking ID {st['booking_id']}.")

    def _reconcile_after_uncertainty(self, st: dict | None = None) -> str:
        s = self.state
        st = st or self._call("get_booking_status", idempotency_key=s.idempotency_key)
        if st["status"] == "booked":
            return self._confirmed(st)  # BUG-1 fix: was re-querying status via _verify()
        if st["status"] == "failed":
            return self._slot_lost(st.get("reason") or "failed")
        # not_found: retry only within the 30s window and attempt cap; else re-approve.
        fresh = s.approval and self.world.clock.now() - s.approval.approved_at < RETRY_WINDOW_S
        if fresh and s.attempt < self.limits.max_book_attempts:
            self.trace.emit("retry", key=s.idempotency_key, attempt=s.attempt + 1)
            return self._attempt_book()
        self._void_approval("retry window elapsed or attempts exhausted")
        s.idempotency_key, s.hold = None, None
        self._set_phase(AWAITING_APPROVAL, "needs re-approval")
        return ("The booking didn't go through and I've confirmed nothing was booked. "
                + self._ask_approval())

    def _slot_lost(self, code: str) -> str:
        s = self.state
        s.rejected.append(f"{s.proposal.provider_id}@{s.proposal.slot}")
        self._void_approval(code)
        s.hold, s.idempotency_key = None, None
        self.trace.emit("slot_lost", code=code)
        return "That slot was just taken, so nothing was booked. " + self._propose()
