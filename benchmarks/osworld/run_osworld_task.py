#!/usr/bin/env python3
import os, sys
os.environ.setdefault("PYTHONUNBUFFERED", "1")
sys.stdout.reconfigure(line_buffering=True)
# Ensure we load from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
"""
Run a single OSWorld multi_apps task with GUI Agent Harness.

Usage:
    python3 run_osworld_task.py 44                    # task number (1-indexed)
    python3 run_osworld_task.py 44 --vm 172.16.82.132  # custom VM IP
    python3 run_osworld_task.py 44 --max-steps 20      # custom max steps
    python3 run_osworld_task.py 44 --no-setup           # skip VM reset + file download
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
import urllib.request

OSWORLD_DIR = os.path.expanduser("~/OSWorld")
VM_PORT = 5000
VMRUN = "/Applications/VMware Fusion.app/Contents/Public/vmrun"
VMX = os.path.expanduser("~/OSWorld/vmware_vm_data/Ubuntu-arm/Ubuntu.vmx")

def get_task_config(task_num: int) -> dict:
    """Load task config from OSWorld evaluation_examples."""
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


def setup_vm(vm_ip: str, task_config: dict):
    """Revert VM to snapshot and run official OSWorld setup."""
    print(f"Reverting VM to init_state...")
    subprocess.run([VMRUN, "revertToSnapshot", VMX, "init_state"],
                   capture_output=True, timeout=120)
    # start may hang if VM is already running after revert; run in background
    subprocess.Popen([VMRUN, "start", VMX, "gui"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)

    # Wait for VM API — retry longer to ensure VM is fully booted
    vm_url = f"http://{vm_ip}:{VM_PORT}"
    print(f"Waiting for VM at {vm_url}...")
    for i in range(60):
        try:
            urllib.request.urlopen(f"{vm_url}/screenshot", timeout=5)
            time.sleep(3)  # Extra wait after first response to ensure services are ready
            break
        except Exception:
            time.sleep(3)

    # VM only has snap chromium (no google-chrome). OSWorld's setup tries to
    # launch google-chrome which silently fails. Pre-launch chromium with proxy
    # and remote-debugging so Playwright can connect via socat on port 9222.
    # Surge on macOS listens on *:6152; VM reaches macOS at 172.16.82.1
    PROXY_URL = "http://172.16.82.1:6152"
    print(f"Pre-launching Chromium with proxy {PROXY_URL}...")
    try:
        _exec = lambda cmd: urllib.request.urlopen(
            urllib.request.Request(
                f"{vm_url}/execute",
                data=json.dumps({"command": cmd, "shell": True}).encode(),
                headers={"Content-Type": "application/json"},
            ), timeout=30
        )
        # Create google-chrome wrapper pointing to snap chromium (needs sudo)
        # OSWorld's _launch_setup will add --proxy-server flag automatically
        _exec(
            'echo password | sudo -S bash -c \''
            'printf "#!/bin/bash\\nexec /snap/bin/chromium \\"\\$@\\"\\n"'
            ' > /usr/local/bin/google-chrome && chmod +x /usr/local/bin/google-chrome\''
        )
        print("  Chromium proxy wrapper installed.")
    except Exception as e:
        print(f"  Proxy setup warning: {e}")

    # Use official OSWorld SetupController for all config steps
    sys.path.insert(0, OSWORLD_DIR)
    from desktop_env.controllers.setup import SetupController
    setup_controller = SetupController(
        vm_ip=vm_ip,
        server_port=VM_PORT,
        chromium_port=9222,
        vlc_port=8080,
        cache_dir="cache",
        client_password="password",
        screen_width=1920,
        screen_height=1080,
    )

    config = task_config.get("config", [])
    use_proxy = bool(task_config.get("proxy"))
    if config:
        print(f"Running {len(config)} setup steps...")
        try:
            setup_controller.setup(config, use_proxy=use_proxy)
        except Exception as e:
            print(f"  Setup warning: {e}")
    print("VM setup complete.")



def run_task(task_config: dict, vm_ip: str, max_steps: int) -> dict:
    """Run the task using execute_task."""
    os.environ["NO_PROXY"] = f"{vm_ip}/24"
    os.environ["no_proxy"] = f"{vm_ip}/24"

    # Kill stale processes
    subprocess.run(["pkill", "-f", "claude.*stream-json"], capture_output=True)
    time.sleep(1)

    # Clean cache to prevent reading stale files from previous tasks
    import shutil
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cache")
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)

    from gui_harness.adapters.vm_adapter import patch_for_vm
    patch_for_vm(f"http://{vm_ip}:{VM_PORT}")

    # Bring the most relevant window to the foreground so the agent sees it first
    # For tasks with Chrome/browser, activate the browser window
    related_apps = task_config.get("related_apps") or []
    if "chrome" in related_apps or task_config.get("proxy"):
        try:
            _exec_vm = lambda cmd: urllib.request.urlopen(
                urllib.request.Request(
                    f"http://{vm_ip}:{VM_PORT}/execute",
                    data=json.dumps({"command": cmd, "shell": True}).encode(),
                    headers={"Content-Type": "application/json"},
                ), timeout=10
            )
            _exec_vm("wmctrl -a Chromium || wmctrl -a Chrome || true")
            time.sleep(1)
            print("Activated Chrome window for agent's first screenshot.")
        except Exception as e:
            print(f"Warning: could not activate Chrome: {e}")

    from gui_harness.tasks.execute_task import execute_task
    from gui_harness.runtime import GUIRuntime

    runtime = GUIRuntime(provider="claude-code", model="opus")

    related_apps = task_config.get("related_apps") or ["desktop"]
    app_name = related_apps[0] if related_apps else "desktop"

    # Build augmented task description with pre-loaded VM file paths
    task_instruction = task_config["instruction"]

    # Task-specific hints
    task_id = task_config.get("id", "")
    TASK_HINTS = {
        "81c425f5": (
            "\n\nHINT: The xlsx file contains formulas and number formatting (e.g., $ symbols, "
            "rounding). To preserve the original display format, use 'libreoffice --headless "
            "--convert-to csv' on the VM to get the formatted display values, rather than "
            "reading raw formula results with openpyxl."
        ),
    }
    for prefix, hint in TASK_HINTS.items():
        if task_id.startswith(prefix):
            task_instruction += hint
            break
    pre_loaded = []
    for c in task_config.get("config", []):
        if c["type"] == "download":
            for f in c["parameters"]["files"]:
                pre_loaded.append(f["path"])
    if pre_loaded:
        # Read template xlsx structures from their download URLs
        template_info = []
        url_map = {}
        for c in task_config.get("config", []):
            if c["type"] == "download":
                for f in c["parameters"]["files"]:
                    url_map[f["path"]] = f["url"]

        for path in pre_loaded:
            if path.endswith(".xlsx") and path in url_map:
                try:
                    import io, openpyxl
                    data = urllib.request.urlopen(url_map[path], timeout=15).read()
                    wb = openpyxl.load_workbook(io.BytesIO(data))
                    for sh in wb.sheetnames:
                        ws = wb[sh]
                        headers = [str(c.value) for c in next(ws.iter_rows(max_row=1))]
                        template_info.append(
                            f"  - {path}  [sheet='{sh}', columns={headers}, {ws.max_row-1} data rows — FILL THIS TEMPLATE]"
                        )
                except Exception:
                    template_info.append(f"  - {path}")
            else:
                template_info.append(f"  - {path}")

        task_instruction += (
            "\n\nIMPORTANT — Pre-loaded VM files (use these, do NOT recreate):\n"
            + "\n".join(template_info)
            + "\nFor .xlsx templates: fill data into the EXISTING sheet with the EXISTING column headers. "
            "Keep the same sheet name. Do not add new sheets. Save back to the same path."
        )

    result = execute_task(
        task=task_instruction,
        runtime=runtime,
        max_steps=max_steps,
        app_name=app_name,
    )
    return result


def print_result(result: dict, task_num: int, score: float = None):
    """Print task result summary."""
    print()
    print("=" * 60)
    print(f"Task {task_num}: {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"Steps: {result['steps_taken']} | Total: {result.get('total_time', '?')}s")
    if score is not None:
        if score < 0:
            print(f"Score: ERROR (evaluator failed)")
        else:
            print(f"Score: {score:.3f} {'✅' if score >= 1.0 else ('⚠️' if score > 0 else '❌')}")
    print()
    for h in result["history"]:
        status = "OK" if h.get("success") else "FAIL"
        timing = h.get("timing", {})
        step_t = timing.get("step_total", "?")
        output = str(h.get("output", ""))[:120]
        print(f"  {h['step']:2d}. [{status}] {h['action']:15s} ({step_t}s)")
        if output.strip():
            print(f"      output: {output}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run OSWorld multi_apps task")
    parser.add_argument("task_num", type=int, help="Task number (1-indexed)")
    parser.add_argument("--vm", default="172.16.82.132", help="VM IP address")
    parser.add_argument("--max-steps", type=int, default=15, help="Max steps")
    parser.add_argument("--no-setup", action="store_true", help="Skip VM reset")
    parser.add_argument("--no-eval", action="store_true", help="Skip official evaluation")
    args = parser.parse_args()

    task_config = get_task_config(args.task_num)
    task_id = task_config["id"][:8]
    print(f"Task {args.task_num} ({task_id}): {task_config['instruction'][:80]}...")
    print(f"Apps: {task_config.get('related_apps')} | Proxy: {task_config.get('proxy')}")

    if task_config.get("proxy"):
        print("WARNING: This task requires proxy/internet access.")

    if not args.no_setup:
        setup_vm(args.vm, task_config)

    result = run_task(task_config, args.vm, args.max_steps)

    # Run official evaluator before next task reverts the VM
    score = None
    if not args.no_eval:
        here = os.path.dirname(os.path.abspath(__file__))
        eval_script = os.path.join(here, "eval_osworld_task.py")
        print("\n[eval] Running official evaluator...")
        subprocess.run(
            [sys.executable, eval_script, str(args.task_num), "--vm", args.vm],
            capture_output=False,
        )

    print_result(result, args.task_num, score)

    # Clean up
    subprocess.run(["pkill", "-f", "claude.*stream-json"], capture_output=True)


if __name__ == "__main__":
    main()
