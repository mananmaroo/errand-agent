"""Explicit workflow state. Persisted after every transition so restarts resume safely."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Phases
COLLECTING = "COLLECTING"
PROPOSING = "PROPOSING"
AWAITING_APPROVAL = "AWAITING_APPROVAL"
EXECUTING = "EXECUTING"
DONE = "DONE"
FAILED = "FAILED"

REQUIRED_SLOTS = ("service", "area", "date_range")
RETRY_WINDOW_S = 30  # decided with user: retry same key only within 30s of approval


@dataclass
class Proposal:
    action: str  # book | cancel | reschedule
    provider_id: str
    slot: str
    price: int
    booking_id: str | None = None  # for cancel/reschedule


@dataclass
class Approval:
    """A record our code checks. Created ONLY from an explicit user 'yes'
    while a proposal is pending — never from model output or tool args."""

    action: str
    provider_id: str
    slot: str
    price: int
    approved_at: float
    booking_id: str | None = None

    def matches(self, p: Proposal) -> bool:
        return (self.action, self.provider_id, self.slot, self.price, self.booking_id) == (
            p.action, p.provider_id, p.slot, p.price, p.booking_id)


@dataclass
class WorkflowState:
    user_id: str = "u1"
    phase: str = COLLECTING
    intent: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)  # name -> value
    proposal: Proposal | None = None
    approval: Approval | None = None
    hold: dict | None = None
    idempotency_key: str | None = None  # written BEFORE calling book (write-ahead)
    result: dict | None = None
    rejected: list[str] = field(default_factory=list)  # "provider@slot" already tried
    attempt: int = 0
    pending_memory: str | None = None  # inferred memory key awaiting user confirmation
    memory_asked: list[str] = field(default_factory=list)

    def missing(self) -> list[str]:
        return [s for s in REQUIRED_SLOTS if not self.slots.get(s)]

    # ---- persistence ----
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2))
        tmp.replace(path)  # atomic

    @classmethod
    def load(cls, path: Path) -> "WorkflowState":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text())
        d["proposal"] = Proposal(**d["proposal"]) if d.get("proposal") else None
        d["approval"] = Approval(**d["approval"]) if d.get("approval") else None
        return cls(**d)
