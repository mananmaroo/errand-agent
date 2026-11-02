"""Interactive chat against the mock world.

  python -m errand_agent.cli                       # happy-ish world
  python -m errand_agent.cli --world timeout       # book times out but actually succeeded
  python -m errand_agent.cli --world price         # quote at hold time differs
  python -m errand_agent.cli --fresh               # wipe saved state + memory first

The trace streams to traces/<run>.jsonl; view it live in a second pane with
  python -m errand_agent.view traces/<run>.jsonl --follow
Type /restart to simulate a process restart (state + memory survive), /quit to exit.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .agent import Agent
from .mocks import Scenario, World

WORLDS = {
    "default": lambda: Scenario(book_sequence=["success"] * 10),
    "timeout": lambda: Scenario(book_sequence=["timeout_booked"] + ["success"] * 10),
    "timeout_lost": lambda: Scenario(book_sequence=["timeout_not_booked"] + ["success"] * 10),
    "price": lambda: Scenario(book_sequence=["success"] * 10, price_drift={"E-201": 1.2, "P-103": 1.1}),
    "random": lambda: Scenario(seed=42),  # the spec's 70/15/15 split, seeded
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", choices=WORLDS, default="default")
    ap.add_argument("--store", default=".store/cli")
    ap.add_argument("--run", default="demo")
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()
    store = Path(args.store)
    if args.fresh and store.exists():
        shutil.rmtree(store)
    trace_dir = Path("traces")
    (trace_dir / f"{args.run}.jsonl").unlink(missing_ok=True)

    world = World(WORLDS[args.world]())
    world.seed_booking("u1", "E-202", "2026-10-20T10:00", status="completed")  # "last time"
    agent = Agent(world, store, run_id=args.run, trace_dir=trace_dir)
    print(f"Errand agent · world={args.world} · trace → traces/{args.run}.jsonl")
    print("Try: Find a plumber for my kitchen tap this week, mornings only, under ₹1,500\n")
    if msg := agent.resume():
        print(f"agent> {msg}\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/restart":
            agent = Agent(world, store, run_id=args.run, trace_dir=trace_dir)
            print("agent> (restarted)" + (f" {m}" if (m := agent.resume()) else "") + "\n")
            continue
        print(f"agent> {agent.handle(text)}\n")


if __name__ == "__main__":
    main()
