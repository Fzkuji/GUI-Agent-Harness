#!/usr/bin/env python3
"""
Evaluate a completed OSWorld multi_apps task using the official evaluator.

Must be run BEFORE the next task (which reverts the VM snapshot).

Usage:
    python3 eval_osworld_task.py 47               # evaluate task 47
    python3 eval_osworld_task.py 47 --vm 172.16.82.132
"""

import argparse
import glob
import json
import os
import sys

OSWORLD_DIR = os.path.expanduser("~/OSWorld")
sys.path.insert(0, OSWORLD_DIR)

VM_PORT = 5000


def get_task_config(task_num: int) -> dict:
    test_all = json.load(open(os.path.join(OSWORLD_DIR, "evaluation_examples/test_all.json")))
    task_ids = test_all.get("multi_apps", [])
    if task_num < 1 or task_num > len(task_ids):
        raise ValueError(f"Task {task_num} out of range (1-{len(task_ids)})")

    tid = task_ids[task_num - 1]
    files = glob.glob(os.path.join(OSWORLD_DIR, f"evaluation_examples/examples/multi_apps/{tid}*.json"))
    if not files:
        raise FileNotFoundError(f"Task config not found for {tid}")

    config = json.load(open(files[0]))
    config["_task_num"] = task_num
    return config


def main():
    parser = argparse.ArgumentParser(description="Evaluate completed OSWorld task")
    parser.add_argument("task_num", type=int, help="Task number (1-indexed)")
    parser.add_argument("--vm", default="172.16.82.132", help="VM IP address")
    args = parser.parse_args()

    task_config = get_task_config(args.task_num)
    task_id = task_config["id"][:8]
    print(f"Evaluating task {args.task_num} ({task_id})...")
    print(f"Instruction: {task_config['instruction'][:100]}")

    from eval_only import EvalOnlyEnv
    env = EvalOnlyEnv(vm_ip=args.vm, server_port=VM_PORT)
    env.load_task(task_config)
    score = float(env.evaluate())

    print()
    print("=" * 60)
    if score >= 1.0:
        print(f"Score: {score:.3f}  ✅  PASS")
    elif score > 0:
        print(f"Score: {score:.3f}  ⚠️  PARTIAL")
    else:
        print(f"Score: {score:.3f}  ❌  FAIL")
    print("=" * 60)

    return score


if __name__ == "__main__":
    score = main()
    sys.exit(0 if score > 0 else 1)
