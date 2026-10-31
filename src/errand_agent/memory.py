"""Cross-session user memory. Each fact is marked `stated` (user said it) or
`inferred` (derived by the agent). Inferred facts are never used without
confirmation; forgotten keys are deleted AND blocked from being re-inferred.
"""
from __future__ import annotations

import json
from pathlib import Path

STATED, INFERRED = "stated", "inferred"
LABELS = {"area": "area", "earliest_hour": "earliest time",
          "preferred_provider": "preferred technician"}


class Memory:
    def __init__(self, path: Path, clock):
        self.path, self.clock = path, clock
        d = json.loads(path.read_text()) if path.exists() else {}
        self.facts: dict[str, dict] = d.get("facts", {})
        self.forgotten: set[str] = set(d.get("forgotten", []))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"facts": self.facts, "forgotten": sorted(self.forgotten)}, indent=2))
        tmp.replace(self.path)

    def state(self, key: str, value) -> None:
        """User said it: stated, and an explicit restatement lifts a forget-block."""
        self.forgotten.discard(key)
        self.facts[key] = {"value": value, "source": STATED, "updated_at": self.clock.now()}
        self._save()

    def infer(self, key: str, value) -> bool:
        if key in self.forgotten or self.facts.get(key, {}).get("source") == STATED:
            return False
        self.facts[key] = {"value": value, "source": INFERRED, "updated_at": self.clock.now()}
        self._save()
        return True

    def forget(self, key: str) -> bool:
        hit = [k for k in self.facts if k == key or k.startswith(key + ":")]
        for k in hit:
            del self.facts[k]
            self.forgotten.add(k)
        self.forgotten.add(key)
        self._save()
        return bool(hit)

    def stated(self, key: str):
        f = self.facts.get(key)
        return f["value"] if f and f["source"] == STATED else None

    def inferred(self, key: str):
        f = self.facts.get(key)
        return f["value"] if f and f["source"] == INFERRED else None

    def describe(self) -> str:
        if not self.facts:
            return "I don't have any saved preferences for you."
        rows = []
        for k, f in sorted(self.facts.items()):
            base, _, svc = k.partition(":")
            label = LABELS.get(base, base) + (f" ({svc})" if svc else "")
            val = f"{f['value']}:00" if base == "earliest_hour" else f["value"]
            rows.append(f"- {label}: {val} [{f['source']}]")
        return "Here's what I remember:\n" + "\n".join(rows) + \
               "\nSay 'forget my area' (etc.) or correct anything."
