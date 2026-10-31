"""One trace per run, JSONL. Secrets and free text are sanitised before writing."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_SECRET = re.compile(r"(api[_-]?key|token|secret|password)", re.I)
MAX_STR = 120


def sanitise(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: ("***" if _SECRET.search(str(k)) else sanitise(x)) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [sanitise(x) for x in v]
    if isinstance(v, str) and len(v) > MAX_STR:
        return v[:MAX_STR] + "…"
    return v


class Tracer:
    def __init__(self, path: Path | None, run_id: str):
        self.path, self.run_id, self.events = path, run_id, []
        self.tokens = 0
        self.cost = 0.0

    def emit(self, kind: str, **data: Any) -> None:
        ev = {"run": self.run_id, "seq": len(self.events), "kind": kind, **sanitise(data)}
        self.events.append(ev)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(ev) + "\n")

    def transition(self, frm: str, to: str, why: str) -> None:
        if frm != to:
            self.emit("state", frm=frm, to=to, why=why)

    def tool(self, name: str, args: dict, fn):
        t0 = time.perf_counter()
        try:
            out = fn()
            self.emit("tool", name=name, args=args, ok=True, result=out,
                      latency_ms=round((time.perf_counter() - t0) * 1000, 2))
            return out
        except Exception as e:  # recorded then re-raised to the agent
            self.emit("tool", name=name, args=args, ok=False,
                      error=f"{type(e).__name__}: {e}",
                      latency_ms=round((time.perf_counter() - t0) * 1000, 2))
            raise
