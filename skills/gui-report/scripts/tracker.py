#!/usr/bin/env python3
"""GUI task tracker — records baseline and computes deltas for time, context, and operations."""

import argparse
import json
import os
import time

STATE_FILE = os.path.join(os.path.dirname(__file__), ".tracker_state.json")


def start(args):
    """Record baseline before a GUI task."""
    state = {
        "task": args.task or "unnamed",
        "start_time": time.time(),
        "context_start": args.context or 0,
        "screenshots": 0,
        "clicks": 0,
        "learns": 0,
        "detects": 0,
        "image_calls": 0,
        "notes": [],
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    print(f"📊 Tracker started: {state['task']} (context baseline: {_fmt_tokens(state['context_start'])})")


def tick(args):
    """Increment a counter (screenshots, clicks, learns, detects, image_calls)."""
    if not os.path.exists(STATE_FILE):
        print("⚠ No active tracker. Call `start` first.")
        return
    with open(STATE_FILE) as f:
        state = json.load(f)
    key = args.counter
    if key not in state:
        print(f"⚠ Unknown counter: {key}")
        return
    state[key] = state.get(key, 0) + (args.n or 1)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    print(f"  +{args.n or 1} {key} (total: {state[key]})")


def note(args):
    """Add a free-form note to the current task."""
    if not os.path.exists(STATE_FILE):
        print("⚠ No active tracker.")
        return
    with open(STATE_FILE) as f:
        state = json.load(f)
    state.setdefault("notes", []).append(args.text)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    print(f"  📝 Note added")


def report(args):
    """Generate final report with deltas."""
    if not os.path.exists(STATE_FILE):
        print("⚠ No active tracker. Nothing to report.")
        return

    with open(STATE_FILE) as f:
        state = json.load(f)

    elapsed = time.time() - state["start_time"]
    context_delta = (args.context or 0) - state["context_start"]

    # Format time
    if elapsed < 60:
        time_str = f"{elapsed:.1f}s"
    elif elapsed < 3600:
        time_str = f"{elapsed/60:.1f}min"
    else:
        time_str = f"{elapsed/3600:.1f}h"

    # Build operations list
    ops = []
    for key in ["screenshots", "clicks", "learns", "detects", "image_calls"]:
        v = state.get(key, 0)
        if v > 0:
            ops.append(f"{v}×{key}")

    print("=" * 60)
    print(f"📊 GUI Task Report: {state['task']}")
    print("=" * 60)
    print(f"⏱  Duration:    {time_str}")
    print(f"📦 Context:     {_fmt_tokens(state['context_start'])} → {_fmt_tokens(args.context or 0)} (+{_fmt_tokens(context_delta)})")
    print(f"🔧 Operations:  {', '.join(ops) if ops else 'none tracked'}")
    if state.get("notes"):
        print(f"📝 Notes:")
        for n in state["notes"]:
            print(f"   - {n}")
    print("=" * 60)

    # Save report to log
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_entry = {
        "task": state["task"],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(elapsed, 1),
        "context_start": state["context_start"],
        "context_end": args.context or 0,
        "context_delta": context_delta,
        "operations": {k: state.get(k, 0) for k in ["screenshots", "clicks", "learns", "detects", "image_calls"]},
        "notes": state.get("notes", []),
    }
    log_file = os.path.join(log_dir, "task_history.jsonl")
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"💾 Saved to {log_file}")

    # Cleanup state
    os.remove(STATE_FILE)


def history(args):
    """Show recent task history."""
    log_file = os.path.join(os.path.dirname(__file__), "..", "logs", "task_history.jsonl")
    if not os.path.exists(log_file):
        print("No task history yet.")
        return
    with open(log_file) as f:
        lines = f.readlines()
    limit = args.limit or 10
    entries = [json.loads(l) for l in lines[-limit:]]

    print(f"{'Task':<30} {'Duration':>10} {'Context Δ':>12} {'Date'}")
    print("-" * 70)
    for e in entries:
        delta = e.get("context_delta", 0)
        dur = f"{e['duration_s']:.0f}s" if e["duration_s"] < 60 else f"{e['duration_s']/60:.1f}m"
        print(f"{e['task']:<30} {dur:>10} {_fmt_tokens(delta):>12} {e['timestamp']}")
    print("-" * 70)
    total_delta = sum(e.get("context_delta", 0) for e in entries)
    print(f"{'Total':>42} {_fmt_tokens(total_delta):>12}  ({len(entries)} tasks)")


def _fmt_tokens(n):
    if abs(n) < 1000:
        return f"{n}"
    elif abs(n) < 1_000_000:
        return f"{n/1000:.1f}k"
    else:
        return f"{n/1_000_000:.2f}M"


def main():
    parser = argparse.ArgumentParser(description="GUI task tracker")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Begin tracking a task")
    p_start.add_argument("--task", help="Task name")
    p_start.add_argument("--context", type=int, help="Current context size (from session_status)")

    p_tick = sub.add_parser("tick", help="Increment a counter")
    p_tick.add_argument("counter", choices=["screenshots", "clicks", "learns", "detects", "image_calls"])
    p_tick.add_argument("-n", type=int, default=1)

    p_note = sub.add_parser("note", help="Add a note")
    p_note.add_argument("text")

    p_report = sub.add_parser("report", help="Generate final report")
    p_report.add_argument("--context", type=int, help="Final context size (from session_status)")

    p_hist = sub.add_parser("history", help="Show task history")
    p_hist.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()
    if args.command == "start":
        start(args)
    elif args.command == "tick":
        tick(args)
    elif args.command == "note":
        note(args)
    elif args.command == "report":
        report(args)
    elif args.command == "history":
        history(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
