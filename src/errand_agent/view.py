"""Pretty-print a trace file, optionally following it live (for the demo's side pane).

  python -m errand_agent.view traces/demo.jsonl --follow
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

C = {"state": "\033[35m", "tool": "\033[36m", "approval": "\033[32m", "approval_void": "\033[31m",
     "model": "\033[90m", "error": "\033[31m", "retry": "\033[33m", "resume": "\033[33m",
     "turn_summary": "\033[90m"}
R = "\033[0m"


def fmt(e: dict) -> str | None:
    k = e["kind"]
    if k == "state":
        s = f"STATE  {e['frm']} → {e['to']}  ({e['why']})"
    elif k == "tool":
        args = ", ".join(f"{a}={v}" for a, v in e["args"].items())
        out = e["result"] if e["ok"] else f"✗ {e['error']}"
        if isinstance(out, dict) and "reviews" in out:  # show the redaction, not the bulk
            out = {k: out[k] for k in ("id", "name", "price", "rating", "reviews")}
        s = f"TOOL   {e['name']}({args}) → {json.dumps(out)[:90]}  [{e['latency_ms']}ms]"
    elif k == "approval":
        s = f"APPROVE {e['action']} {e['provider_id']} {e['slot']} ₹{e['price']}"
    elif k == "approval_void":
        s = f"VOID   approval ({e['why']})"
    elif k == "model":
        s = f"MODEL  {e['model']} intent={e['intent']} slots={e['slots']}"
    elif k == "turn_summary":
        s = f"──── turn {e['turn']} · {e['phase']} · {e['tool_calls']} calls · ${e['cost_usd']}"
    elif k == "reply":
        return None
    else:
        s = f"{k.upper():6} " + json.dumps({x: y for x, y in e.items() if x not in ('run', 'seq', 'kind')})
    return f"{C.get(k, '')}{s}{R}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--follow", action="store_true")
    a = ap.parse_args()
    p, pos = Path(a.path), 0
    while True:
        if p.exists():
            if p.stat().st_size < pos:  # file was recreated by a new CLI run
                pos = 0
            with p.open() as f:
                f.seek(pos)
                for line in f:
                    if (s := fmt(json.loads(line))):
                        print(s, flush=True)
                pos = f.tell()
        if not a.follow:
            break
        time.sleep(0.3)


if __name__ == "__main__":
    main()
