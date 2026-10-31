"""The 'model': turns a user message into a structured Parse. It ONLY extracts
facts and intent. It never sees tool output and cannot create approvals.

ScriptedModel is deterministic (offline, reproducible). A live LLM can implement
the same `parse()` interface; the agent treats its output as a suggestion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

WEEK = ("2026-11-02", "2026-11-07")
DAYS = {"monday": "2026-11-02", "tuesday": "2026-11-03", "wednesday": "2026-11-04",
        "thursday": "2026-11-05", "friday": "2026-11-06", "saturday": "2026-11-07"}
SERVICES = {"plumber": "plumber", "plumbing": "plumber", "tap": "plumber",
            "electrician": "electrician", "ac": "ac_servicing", "a/c": "ac_servicing"}
AREAS = ("koramangala", "indiranagar", "hsr")


@dataclass
class Parse:
    intent: str | None = None  # book | reschedule | cancel | confirm | deny | None
    slots: dict = field(default_factory=dict)
    tokens: int = 0


class ScriptedModel:
    name = "scripted-v1"

    def parse(self, text: str) -> Parse:
        t = text.lower().strip()
        p = Parse(tokens=len(t.split()))
        if re.fullmatch(r"(yes|y|yep|confirm|go ahead|book it|ok|okay)[.! ]*", t):
            p.intent = "confirm"
            return p
        if re.fullmatch(r"(no|n|nope|cancel that|don'?t)[.! ]*", t):
            p.intent = "deny"
            return p
        if "move" in t or "reschedule" in t:
            p.intent = "reschedule"
        elif re.search(r"\bcancel\b", t):
            p.intent = "cancel"
        elif any(w in t for w in ("book", "find", "need", "get me")):
            p.intent = "book"
        for w, s in SERVICES.items():
            if re.search(rf"\b{re.escape(w)}\b", t):
                p.slots["service"] = s
                break
        for a in AREAS:
            if a in t:
                p.slots["area"] = a
        if "this week" in t:
            p.slots["date_range"] = WEEK
        for d, iso in DAYS.items():
            if d in t:
                p.slots["date_range"] = (iso, iso)
        if m := re.search(r"(?:under|below|max|budget)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)", t):
            p.slots["budget"] = int(m.group(1).replace(",", ""))
        if "mornings only" in t or "morning" in t:
            p.slots["latest_hour"] = 11
        if m := re.search(r"not before (\d{1,2})", t):
            p.slots["earliest_hour"] = int(m.group(1))
        if "same" in t and "last time" in t:
            p.slots["same_as_last"] = True
        return p
