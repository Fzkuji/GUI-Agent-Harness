#!/usr/bin/env python3
"""
GUI Agent — main entry point.

Usage:
    python3 -m gui_harness "Open Firefox and go to google.com"
    python3 gui_harness/main.py "Send hello to John in WeChat"
    python3 gui_harness/main.py --vm http://172.16.105.128:5000 "Click the OK button"
"""

import argparse
import json
import sys
import os

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="GUI Agent — autonomous GUI task execution")
    parser.add_argument("task", help="What to do (natural language)")
    parser.add_argument("--vm", help="VM HTTP API URL (for OSWorld)")
    parser.add_argument("--provider", help="Force LLM provider: openclaw, claude-code, anthropic, openai")
    parser.add_argument("--model", help="Override model name")
    parser.add_argument("--max-steps", type=int, default=15, help="Max actions (default: 15)")
    args = parser.parse_args()

    # VM adapter
    if args.vm:
        from gui_harness.primitives.vm_adapter import patch_for_vm
        patch_for_vm(args.vm)
        print(f"🖥️  VM mode: {args.vm}")

    # Runtime
    from gui_harness.runtime import GUIRuntime
    kwargs = {}
    if args.provider:
        kwargs["provider"] = args.provider
    if args.model:
        kwargs["model"] = args.model

    runtime = GUIRuntime(**kwargs)
    print(f"🤖 Provider: {runtime.provider}")
    print(f"📋 Task: {args.task}")
    print(f"⏱️  Max steps: {args.max_steps}")
    print()

    # Execute
    from gui_harness.tasks.execute_task import execute_task
    result = execute_task(task=args.task, runtime=runtime, max_steps=args.max_steps)

    # Report
    print()
    print("=" * 60)
    print(f"{'✅' if result['success'] else '❌'} Task: {result['task']}")
    print(f"📊 Steps: {result['steps_taken']}")
    print(f"📍 Final: {result['final_state'][:100]}")
    print()
    for h in result["history"]:
        icon = "✅" if h.get("success", True) else "❌"
        print(f"  {h['step']}. {icon} {h['action']} → {h.get('target', '')[:40]}")
        if h.get("reasoning"):
            print(f"     💭 {h['reasoning'][:60]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
