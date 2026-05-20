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
from contextlib import contextmanager

OSWORLD_DIR = os.path.expanduser("~/OSWorld")
sys.path.insert(0, OSWORLD_DIR)
os.environ["PROXY_CONFIG_FILE"] = os.path.join(
    OSWORLD_DIR,
    "evaluation_examples/settings/proxy/dataimpulse.json",
)

VM_PORT = 5000


@contextmanager
def pushd(path: str):
    old = os.getcwd()
    os.chdir(os.path.expanduser(path))
    try:
        yield
    finally:
        os.chdir(old)


def agent_declared_infeasible(path: str | None) -> tuple[bool, str]:
    if not path:
        return False, "no agent result path provided"
    try:
        data = json.load(open(path))
    except Exception as e:
        return False, f"could not read agent result: {e}"

    if data.get("infeasible_declared") is True:
        return True, "agent_result.infeasible_declared=true"

    texts = []
    for key in ("summary", "issues"):
        value = data.get(key)
        if value:
            texts.append(str(value))
    for item in data.get("history", []):
        plan = item.get("plan", {}) if isinstance(item, dict) else {}
        call = plan.get("call", plan.get("action", ""))
        reasoning = plan.get("reasoning") or plan.get("args", {}).get("reasoning") or ""
        goal = plan.get("goal", "")
        if call == "fail":
            return True, f"history step {item.get('step')} used fail action"
        texts.extend([str(reasoning), str(goal)])

    joined = "\n".join(texts).lower()
    markers = ("fail", "infeasible", "unfeasible", "impossible", "not feasible", "cannot be done")
    if any(marker in joined for marker in markers):
        return True, "agent text explicitly declared infeasible/fail"
    return False, "no explicit infeasible/fail declaration found"


def get_task_config(task_num: int, domain: str = "multi_apps") -> dict:
    test_all = json.load(open(os.path.join(OSWORLD_DIR, "evaluation_examples/test_all.json")))
    task_ids = test_all.get(domain, [])
    if not task_ids:
        raise ValueError(f"Domain '{domain}' not found. Available: {list(test_all.keys())}")
    if task_num < 1 or task_num > len(task_ids):
        raise ValueError(f"Task {task_num} out of range (1-{len(task_ids)})")

    tid = task_ids[task_num - 1]
    files = glob.glob(os.path.join(OSWORLD_DIR, f"evaluation_examples/examples/{domain}/{tid}*.json"))
    if not files:
        raise FileNotFoundError(f"Task config not found for {tid}")

    config = json.load(open(files[0]))
    config["_task_num"] = task_num
    return config


def main():
    parser = argparse.ArgumentParser(description="Evaluate completed OSWorld task")
    parser.add_argument("task_num", type=int, help="Task number (1-indexed)")
    parser.add_argument("--domain", default="multi_apps", help="OSWorld domain")
    parser.add_argument("--vm", default="172.16.82.132", help="VM IP address")
    parser.add_argument("--agent-result", help="GUI harness agent_result.json for scoring infeasible tasks")
    args = parser.parse_args()

    task_config = get_task_config(args.task_num, args.domain)
    task_id = task_config["id"][:8]
    print(f"Evaluating task {args.task_num} ({task_id})...")
    print(f"Instruction: {task_config['instruction'][:100]}")

    evaluator = task_config.get("evaluator", {})
    if evaluator.get("func") == "infeasible":
        declared, reason = agent_declared_infeasible(args.agent_result)
        print("Evaluator: infeasible-style task")
        print(f"Agent infeasible declaration: {'yes' if declared else 'no'} ({reason})")
        score = 1.0 if declared else 0.0
    else:
        from eval_only import EvalOnlyEnv
        try:
            with pushd(OSWORLD_DIR):
                # EvalOnlyEnv uses a relative cache_dir. Construct it after
                # switching to OSWorld so getters write into the same cache
                # tree that was created during initialization.
                env = EvalOnlyEnv(vm_ip=args.vm, server_port=VM_PORT, task_id=task_config["id"])
                env.load_task(task_config)
                score = float(env.evaluate())
        except Exception as e:
            print(f"Evaluator error: {e}")
            score = -1.0

    print()
    print("=" * 60)
    if score < 0:
        print(f"Score: N/A  ⚠️  EVAL_ERROR")
    elif score >= 1.0:
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
