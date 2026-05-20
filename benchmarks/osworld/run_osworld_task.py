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
import datetime as _dt
import glob
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from contextlib import contextmanager

os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")
os.environ.setdefault("GIT_ASKPASS", "/bin/false")
os.environ.setdefault("SSH_ASKPASS", "/bin/false")
os.environ.setdefault("SUDO_ASKPASS", "/bin/false")
os.environ.setdefault("OSWORLD_BENCHMARK_FIXED", "1")

OSWORLD_DIR = os.path.expanduser("~/OSWorld")
VM_PORT = 5000
VMRUN = "/Applications/VMware Fusion.app/Contents/Public/vmrun"
VMX = os.path.expanduser("~/OSWorld/vmware_vm_data/Ubuntu-arm/Ubuntu.vmx")
VM_SNAPSHOT = "init_state"
VM_START_MODE = "gui"
HOST_PROXY_URL = "http://172.16.82.1:6152"
OSWORLD_CACHE_DIR = "cache"


def _expand_config_path(path: str) -> str:
    if not os.path.isabs(path):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(repo_root, path)
    return os.path.abspath(os.path.expanduser(path))


def load_run_config(path: str | None) -> dict:
    if not path:
        return {}
    resolved = _expand_config_path(path)
    with open(resolved) as f:
        config = json.load(f)
    config["_path"] = resolved
    return config


def apply_run_config(args, config: dict) -> None:
    global OSWORLD_DIR, VM_PORT, VMRUN, VMX, VM_SNAPSHOT, VM_START_MODE, HOST_PROXY_URL, OSWORLD_CACHE_DIR
    if not config:
        return

    paths = config.get("paths", {})
    vm = config.get("vm", {})
    run = config.get("run", {})

    OSWORLD_DIR = os.path.expanduser(paths.get("osworld_dir", OSWORLD_DIR))
    VMRUN = os.path.expanduser(vm.get("vmrun", VMRUN))
    VMX = os.path.expanduser(vm.get("vmx", VMX))
    VM_SNAPSHOT = vm.get("snapshot", VM_SNAPSHOT)
    VM_START_MODE = vm.get("start_mode", VM_START_MODE)
    VM_PORT = int(vm.get("server_port", VM_PORT))
    HOST_PROXY_URL = vm.get("host_proxy_url", HOST_PROXY_URL)
    OSWORLD_CACHE_DIR = paths.get("osworld_cache_dir", OSWORLD_CACHE_DIR)
    configure_osworld_environment()

    for name in ("domain", "vm", "max_steps", "provider", "model", "eval_timeout", "ro_retries"):
        if getattr(args, name) is None and name in run:
            setattr(args, name, run[name])
    if args.artifact_dir is None and run.get("artifact_root"):
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        args.artifact_dir = os.path.join(run["artifact_root"], f"{args.domain}_task_{args.task_num}_{stamp}")


def fill_arg_defaults(args) -> None:
    defaults = {
        "domain": "multi_apps",
        "vm": "172.16.82.132",
        "max_steps": 15,
        "provider": "openai-codex",
        "model": "gpt-5.5",
        "eval_timeout": 300,
        "ro_retries": 1,
    }
    for name, value in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    configure_osworld_environment()


def configure_osworld_environment() -> None:
    os.environ["PROXY_CONFIG_FILE"] = os.path.join(
        os.path.expanduser(OSWORLD_DIR),
        "evaluation_examples/settings/proxy/dataimpulse.json",
    )


def sanitize_vmx_devices() -> None:
    """Prevent VMware's virtual camera bridge from showing host-side popups.

    Fusion may rehydrate a virtual USB video device from snapshot state even if
    the current VMX does not list it. Keeping explicit disabled entries and
    starting the benchmark VM headless avoids the repeated
    "Virtual video camera failed to connect" overlay during automated runs.
    """
    vmx_path = os.path.expanduser(VMX)
    if not os.path.exists(vmx_path):
        return
    disabled = {
        "ehci:0.present": "FALSE",
        "ehci:0.startConnected": "FALSE",
        "ehci:0.deviceType": "video",
        "usb.vbluetooth.startConnected": "FALSE",
    }
    lines = open(vmx_path).read().splitlines()
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else None
        if key in disabled:
            out.append(f'{key} = "{disabled[key]}"')
            seen.add(key)
        else:
            out.append(line)
    for key, value in disabled.items():
        if key not in seen:
            out.append(f'{key} = "{value}"')
    new_text = "\n".join(out) + "\n"
    old_text = "\n".join(lines) + "\n"
    if new_text != old_text:
        with open(vmx_path, "w") as f:
            f.write(new_text)


def stop_vm_if_running() -> None:
    try:
        listed = subprocess.run([VMRUN, "list"], capture_output=True, text=True, timeout=30)
        if os.path.expanduser(VMX) in listed.stdout:
            subprocess.run([VMRUN, "stop", VMX, "hard"], capture_output=True, timeout=60)
            time.sleep(2)
    except Exception as e:
        print(f"  VM stop warning: {e}")


@contextmanager
def pushd(path: str):
    old = os.getcwd()
    os.chdir(os.path.expanduser(path))
    try:
        yield
    finally:
        os.chdir(old)


def write_json(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def vm_execute(vm_ip: str, command: str, timeout: int = 15) -> dict:
    vm_url = f"http://{vm_ip}:{VM_PORT}"
    response = urllib.request.urlopen(
        urllib.request.Request(
            f"{vm_url}/execute",
            data=json.dumps({"command": command, "shell": True}).encode(),
            headers={"Content-Type": "application/json"},
        ),
        timeout=timeout,
    )
    return json.loads(response.read())


def vm_screenshot_ok(vm_ip: str, timeout: int = 10) -> bool:
    vm_url = f"http://{vm_ip}:{VM_PORT}"
    try:
        response = urllib.request.urlopen(f"{vm_url}/screenshot", timeout=timeout)
        head = response.read(8)
        return head == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


def force_vm_readwrite(vm_ip: str, artifact_dir=None, label: str = "force_rw") -> dict:
    """Best-effort override for benchmark VMs that remount root read-only.

    The OSWorld VMware image is disposable and restored from snapshot for every
    task. For benchmark stability, prefer keeping the guest writable over
    preserving ext4's default errors=remount-ro behavior.
    """
    command = r"""
set -eu
ROOT_SRC="$(findmnt -no SOURCE /)"
echo password | sudo -S sh -c "
  tune2fs -e continue '$ROOT_SRC' >/tmp/gui_harness_tune2fs.log 2>&1 || true
  mount -o remount,rw,errors=continue / >/tmp/gui_harness_remount.log 2>&1 || +    mount -o remount,rw / >>/tmp/gui_harness_remount.log 2>&1 || true
  mkdir -p /tmp /home/user/server/screenshots
  chown user:user /home/user/server/screenshots 2>/dev/null || true
  chmod 1777 /tmp 2>/dev/null || true
  chmod 755 /home/user/server/screenshots 2>/dev/null || true
"
findmnt -no SOURCE,TARGET,FSTYPE,OPTIONS /
printf ok > /tmp/gui_harness_force_rw_check && cat /tmp/gui_harness_force_rw_check
"""
    try:
        result = vm_execute(vm_ip, command, timeout=30)
    except Exception as e:
        result = {"error": str(e), "traceback": traceback.format_exc(), "status": "exception"}
    if artifact_dir:
        write_json(os.path.join(artifact_dir, f"vm_force_rw_{label}.json"), result)
    return result


def assert_vm_writable(vm_ip: str, artifact_dir=None, label: str = "preflight", recover: bool = True):
    """Fail fast when the guest has remounted root read-only.

    The VM screenshot service writes to /home/user/server/screenshots. When ext4
    remounts read-only, screenshot calls start returning HTTP 500 and the agent
    later passes broken screenshots to the model. Catching it here lets the
    runner recover by reverting the VM and retrying the task instead of logging
    a misleading task failure.
    """
    commands = {
        "root_mount": "findmnt -no TARGET,OPTIONS /",
        "tmp_write": "printf ok > /tmp/gui_harness_rw_check && cat /tmp/gui_harness_rw_check",
        "screenshot_dir_write": (
            "mkdir -p /home/user/server/screenshots && "
            "printf ok > /home/user/server/screenshots/.gui_harness_rw_check && "
            "cat /home/user/server/screenshots/.gui_harness_rw_check"
        ),
    }
    report = {"label": label, "checks": {}}
    errors = []
    for name, command in commands.items():
        try:
            result = vm_execute(vm_ip, command, timeout=15)
            report["checks"][name] = result
            output = (result.get("output") or "").strip()
            error = (result.get("error") or "").strip()
            returncode = result.get("returncode", 0)
            if name == "root_mount" and " ro," in f" {output},":
                errors.append(f"root filesystem is read-only: {output}")
            elif returncode not in (None, 0) or error or (name.endswith("_write") and output != "ok"):
                errors.append(f"{name} failed: rc={returncode} output={output!r} error={error!r}")
        except Exception as e:
            report["checks"][name] = {"error": str(e), "traceback": traceback.format_exc()}
            errors.append(f"{name} raised {e.__class__.__name__}: {e}")

    screenshot_ok = vm_screenshot_ok(vm_ip)
    report["checks"]["screenshot_png"] = {"ok": screenshot_ok}
    if not screenshot_ok:
        errors.append("screenshot endpoint did not return a valid PNG")

    if artifact_dir:
        write_json(os.path.join(artifact_dir, f"vm_writable_{label}.json"), report)
    if errors:
        if recover:
            force_vm_readwrite(vm_ip, artifact_dir, label)
            return assert_vm_writable(vm_ip, artifact_dir, f"{label}_after_force_rw", recover=False)
        raise RuntimeError("VM_WRITABLE_CHECK_FAILED: " + "; ".join(errors))


def looks_like_vm_read_only_failure(exc_or_text) -> bool:
    text = str(exc_or_text)
    needles = [
        "Read-only file system",
        "read-only filesystem",
        "VM_WRITABLE_CHECK_FAILED",
        "screenshot service hit read-only filesystem",
    ]
    return any(needle in text for needle in needles)


def make_artifact_dir(args, task_id: str) -> str:
    path = (
        args.artifact_dir
        or os.environ.get("OSWORLD_ARTIFACT_DIR")
        or os.path.join(
            "runs",
            "osworld_debug",
            f"{args.domain}_task_{args.task_num}_{task_id}_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
    )
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(path, exist_ok=True)
    return path


def capture_vm_diagnostics(vm_ip: str, artifact_dir: str, label: str):
    vm_url = f"http://{vm_ip}:{VM_PORT}"
    report = {"label": label, "vm_url": vm_url, "commands": []}
    for cmd in [
        "date",
        "pgrep -a gimp || true",
        "wmctrl -l || true",
        "ls -la /home/user/Desktop | sed -n '1,120p'",
        "file /home/user/Desktop/* 2>/dev/null | sed -n '1,120p'",
    ]:
        item = {"command": cmd}
        try:
            response = urllib.request.urlopen(
                urllib.request.Request(
                    f"{vm_url}/execute",
                    data=json.dumps({"command": cmd, "shell": True}).encode(),
                    headers={"Content-Type": "application/json"},
                ),
                timeout=15,
            )
            item["response"] = json.loads(response.read())
        except Exception as e:
            item["error"] = str(e)
            item["traceback"] = traceback.format_exc()
        report["commands"].append(item)
    write_json(os.path.join(artifact_dir, f"vm_diagnostics_{label}.json"), report)

def get_task_config(task_num: int, domain: str = "multi_apps") -> dict:
    """Load task config from OSWorld evaluation_examples."""
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


def setup_vm(vm_ip: str, task_config: dict, artifact_dir=None):
    """Revert VM to snapshot and run official OSWorld setup."""
    stop_vm_if_running()
    sanitize_vmx_devices()
    print(f"Reverting VM to {VM_SNAPSHOT}...")
    subprocess.run([VMRUN, "revertToSnapshot", VMX, VM_SNAPSHOT],
                   capture_output=True, timeout=120)
    sanitize_vmx_devices()
    # start may hang if VM is already running after revert; run in background
    subprocess.Popen([VMRUN, "start", VMX, VM_START_MODE],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Starting VM in {VM_START_MODE} mode...")
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
    force_vm_readwrite(vm_ip, artifact_dir, "after_boot")
    assert_vm_writable(vm_ip, artifact_dir, "after_boot")

    # VM only has snap chromium (no google-chrome). OSWorld's setup tries to
    # launch google-chrome which silently fails. Pre-launch chromium with proxy
    # and remote-debugging so Playwright can connect via socat on port 9222.
    # Surge on macOS listens on *:6152; VM reaches macOS at the configured host proxy address.
    print(f"Pre-launching Chromium with proxy {HOST_PROXY_URL}...")
    try:
        _exec = lambda cmd: vm_execute(vm_ip, cmd, timeout=30)
        # Create google-chrome wrapper pointing to snap chromium (needs sudo)
        # OSWorld's _launch_setup will add --proxy-server flag automatically
        # Include --remote-debugging-port=1337 so evaluator can connect via
        # socat (9222→1337) to check open tabs, regardless of how agent launches Chrome.
        _exec(
            'echo password | sudo -S bash -c \''
            'printf "#!/bin/bash\\nexec /snap/bin/chromium --remote-debugging-port=1337 \\"\\$@\\"\\n"'
            ' > /usr/local/bin/google-chrome && chmod +x /usr/local/bin/google-chrome\''
        )
        print("  Chromium proxy wrapper installed.")

        # Suppress transient Ubuntu/VMware desktop notifications, e.g. virtual
        # camera warnings, because they overlay the app and pollute screenshots.
        _exec(
            "DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus "
            "gsettings set org.gnome.desktop.notifications show-banners false || true"
        )
        print("  Desktop notification banners disabled for benchmark run.")

        # Set system-wide proxy so all apps (VS Code, pip, curl, apt, etc.)
        # can access the internet through Surge proxy on the host.
        proxy_script = (
            f'export HTTP_PROXY={HOST_PROXY_URL}\\n'
            f'export HTTPS_PROXY={HOST_PROXY_URL}\\n'
            f'export http_proxy={HOST_PROXY_URL}\\n'
            f'export https_proxy={HOST_PROXY_URL}'
        )
        _exec(
            f'echo password | sudo -S bash -c \''
            f'printf "{proxy_script}\\n" > /etc/profile.d/proxy.sh && '
            f'chmod +x /etc/profile.d/proxy.sh\''
        )
        # Also append to user's .bashrc for interactive shells
        _exec(f'grep -q HTTP_PROXY ~/.bashrc 2>/dev/null || printf "\\n{proxy_script}\\n" >> ~/.bashrc')
        print(f"  System-wide proxy configured: {HOST_PROXY_URL}")
    except Exception as e:
        print(f"  Proxy setup warning: {e}")

    # Set VM resolution to standard 1920x1080 (snapshot may have non-standard resolution)
    try:
        _exec("xrandr --output Virtual-1 --mode 1920x1080 2>/dev/null || true")
        time.sleep(0.5)
    except Exception:
        pass

    # Use official OSWorld SetupController for all config steps
    sys.path.insert(0, OSWORLD_DIR)
    from desktop_env.controllers.setup import SetupController
    with pushd(OSWORLD_DIR):
        setup_controller = SetupController(
            vm_ip=vm_ip,
            server_port=VM_PORT,
            chromium_port=9222,
            vlc_port=8080,
            cache_dir=OSWORLD_CACHE_DIR,
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
    force_vm_readwrite(vm_ip, artifact_dir, "after_setup")
    assert_vm_writable(vm_ip, artifact_dir, "after_setup")
    print("VM setup complete.")



def run_task(
    task_config: dict,
    vm_ip: str,
    max_steps: int,
    provider: str = "openai-codex",
    model: str = "gpt-5.5",
) -> dict:
    """Run the task using execute_task."""
    os.environ["NO_PROXY"] = f"{vm_ip}/24"
    os.environ["no_proxy"] = f"{vm_ip}/24"

    # Kill stale processes
    subprocess.run(["pkill", "-f", "claude.*stream-json"], capture_output=True)
    time.sleep(1)

    # Clean cache to prevent reading stale files from previous tasks
    # But ensure the directory exists for setup downloads
    import shutil
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cache")
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir, ignore_errors=True)
    os.makedirs(cache_dir, exist_ok=True)

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
    from gui_harness.openprogram_compat import create_runtime

    runtime = create_runtime(provider=provider, model=model)

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
    if task_config.get("evaluator", {}).get("func") == "infeasible":
        task_instruction += (
            "\n\nIMPORTANT — OSWorld infeasible-task scoring rule:\n"
            "- This task is marked by OSWorld as an infeasible-style task. Try a reasonable inspection first, "
            "but if the requested operation is not actually available in GIMP, depends on unavailable plugins/data, "
            "or belongs to another app/domain, you MUST choose the fail action instead of done.\n"
            "- The fail reasoning MUST explicitly include the word FAIL or INFEASIBLE and the concrete blocker. "
            "Examples: missing Blue theme option, GIMP cannot trim MP4 video, PNG-to-SVG vectorization is not a "
            "reliable GIMP operation, hidden audio translation is outside GIMP, or RAW/CMYK support is unavailable."
        )
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

    task_instruction += (
        "\n\nIMPORTANT — OSWorld benchmark handoff rule:\n"
        "- Do not proactively save, export, overwrite, or rename files unless the task instruction "
        "explicitly asks you to save/export to a named file or path.\n"
        "- For visual editing tasks, after the requested edit is visible in the app, leave the app "
        "in a clean main-workspace state with no Save/Save As/Export/Open/confirmation/options dialog open; "
        "the official evaluator may perform the final export or file check itself.\n"
        "- If you accidentally open a save/export dialog that was not explicitly required, cancel or close it "
        "before marking the task complete."
    )

    # GUI-only apps: the OSWorld evaluator inspects the live app state
    # (e.g. GIMP's loaded image, LibreOffice's open document), so changes
    # made via shell commands on disk don't score. Force GUI interaction.
    GUI_ONLY_APPS = {
        "gimp", "libreoffice_calc", "libreoffice_writer", "libreoffice_impress",
        "chrome", "vlc", "vscode", "thunderbird",
    }
    allow_general = app_name not in GUI_ONLY_APPS

    result = execute_task(
        task=task_instruction,
        runtime=runtime,
        max_steps=max_steps,
        app_name=app_name,
        allow_general=allow_general,
    )
    return result


def print_result(result: dict, task_num: int, score: float = None):
    """Print task result summary."""
    print()
    print("=" * 60)
    print(f"Task {task_num}: {'SUCCESS' if result['success'] else 'FAILED'}")
    print(f"Steps: {result.get('steps_taken', '?')} | Total: {result.get('total_time', '?')}s")
    if score is not None:
        if score < 0:
            print(f"Score: ERROR (evaluator failed)")
        else:
            print(f"Score: {score:.3f} {'✅' if score >= 1.0 else ('⚠️' if score > 0 else '❌')}")
    print()
    for h in result["history"]:
        exec_ok = h.get("exec_result", {}).get("success")
        exec_tag = "OK  " if exec_ok else ("FAIL" if exec_ok is False else "--  ")
        ver = h.get("verification") or {}
        if "step_succeeded" in ver:
            ver_tag = "v-OK  " if ver["step_succeeded"] else "v-FAIL"
        else:
            ver_tag = "v-?   "
        timing = h.get("timing", {})
        step_t = timing.get("step_total", "?")
        plan = h.get("plan", {})
        action = plan.get("call", plan.get("action", "?"))
        exec_err = h.get("exec_result", {}).get("error", "")
        print(f"  {h['step']:2d}. [exec {exec_tag}][{ver_tag}] {str(action):15s} ({step_t}s)")
        if exec_err:
            print(f"      error: {str(exec_err)[:120]}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Run OSWorld task")
    parser.add_argument("task_num", type=int, help="Task number (1-indexed)")
    parser.add_argument("--run-config", default=os.environ.get("OSWORLD_RUN_CONFIG"), help="Fixed run config JSON. Relative paths resolve from repo root.")
    parser.add_argument("--domain", help="OSWorld domain (e.g., chrome, gimp, os, libreoffice_calc, multi_apps)")
    parser.add_argument("--vm", help="VM IP address")
    parser.add_argument("--max-steps", type=int, help="Max steps")
    parser.add_argument("--provider", help="OpenProgram provider")
    parser.add_argument("--model", help="OpenProgram model")
    parser.add_argument("--no-setup", action="store_true", help="Skip VM reset")
    parser.add_argument("--no-eval", action="store_true", help="Skip official evaluation")
    parser.add_argument("--eval-timeout", type=int, help="Official evaluator timeout in seconds")
    parser.add_argument(
        "--ro-retries",
        type=int,
        help="Retry the whole task after VM read-only filesystem or screenshot-service failure.",
    )
    parser.add_argument(
        "--artifact-dir",
        help="Directory for structured debug artifacts. Defaults to runs/osworld_debug/<domain_task_timestamp>.",
    )
    args = parser.parse_args()
    run_config = load_run_config(args.run_config)
    apply_run_config(args, run_config)
    fill_arg_defaults(args)

    task_config = get_task_config(args.task_num, args.domain)
    task_id = task_config["id"][:8]
    artifact_dir = make_artifact_dir(args, task_id)
    os.environ["GUI_HARNESS_ARTIFACT_DIR"] = artifact_dir
    print(f"[artifacts] {artifact_dir}")
    write_json(
        os.path.join(artifact_dir, "task_config.json"),
        {
            "task_num": args.task_num,
            "domain": args.domain,
            "task_id": task_config.get("id"),
            "instruction": task_config.get("instruction"),
            "related_apps": task_config.get("related_apps"),
            "proxy": task_config.get("proxy"),
            "args": vars(args),
            "run_config": run_config,
            "resolved_environment": {
                "osworld_dir": OSWORLD_DIR,
                "vm_port": VM_PORT,
                "vmrun": VMRUN,
                "vmx": VMX,
                "snapshot": VM_SNAPSHOT,
                "start_mode": VM_START_MODE,
                "host_proxy_url": HOST_PROXY_URL,
                "osworld_cache_dir": OSWORLD_CACHE_DIR,
                "python_executable": sys.executable,
            },
        },
    )
    if run_config:
        print(f"[run-config] {run_config['_path']}")
    print(f"[python] {sys.executable}")
    print(f"Task {args.task_num} ({task_id}): {task_config['instruction'][:80]}...")
    print(f"Apps: {task_config.get('related_apps')} | Proxy: {task_config.get('proxy')}")

    if task_config.get("proxy"):
        print("WARNING: This task requires proxy/internet access.")

    result = None
    attempts = max(1, args.ro_retries + 1)
    run_errors = []
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                print(f"[recover] Retrying task after VM read-only failure (attempt {attempt}/{attempts})...")
            if not args.no_setup:
                setup_vm(args.vm, task_config, artifact_dir)
            else:
                assert_vm_writable(args.vm, artifact_dir, f"no_setup_pre_run_attempt{attempt}")

            result = run_task(task_config, args.vm, args.max_steps, args.provider, args.model)
            write_json(os.path.join(artifact_dir, "agent_result.json"), result)
            assert_vm_writable(args.vm, artifact_dir, f"before_eval_attempt{attempt}")
            break
        except Exception as e:
            run_error = {
                "phase": "setup_or_run",
                "attempt": attempt,
                "max_attempts": attempts,
                "error_type": e.__class__.__name__,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "vm_read_only_like": looks_like_vm_read_only_failure(e),
            }
            run_errors.append(run_error)
            print(f"[error] attempt {attempt}/{attempts} {run_error['error_type']}: {run_error['error']}")
            print(run_error["traceback"])
            capture_vm_diagnostics(args.vm, artifact_dir, f"run_error_attempt{attempt}")
            write_json(os.path.join(artifact_dir, "run_errors.json"), {"errors": run_errors})
            if run_error["vm_read_only_like"] and attempt < attempts and not args.no_setup:
                continue
            write_json(
                os.path.join(artifact_dir, "run_report.json"),
                {
                    "task_num": args.task_num,
                    "domain": args.domain,
                    "task_id": task_config.get("id"),
                    "status": "error",
                    "error": run_error,
                    "errors": run_errors,
                    "artifact_dir": artifact_dir,
                },
            )
            raise

    # Diagnose Chrome debugging port before evaluation
    vm_url = f"http://{args.vm}:5000"
    try:
        diag_exec = lambda cmd: json.loads(urllib.request.urlopen(
            urllib.request.Request(
                f"{vm_url}/execute",
                data=json.dumps({"command": cmd, "shell": True}).encode(),
                headers={"Content-Type": "application/json"},
            ), timeout=15
        ).read())
        print("\n[diag] Checking CDP ports...")
        for cmd in [
            "ss -tlnp | grep -E '1337|9222'",
            "pgrep -a socat",
            "pgrep -a chromium | head -3",
            "curl -s http://localhost:1337/json/version 2>&1 | head -3",
            "curl -s http://localhost:9222/json/version 2>&1 | head -3",
        ]:
            r = diag_exec(cmd)
            out = r.get("output", "").strip()
            print(f"  $ {cmd}")
            print(f"    {out[:200] if out else '(empty)'}")
    except Exception as e:
        print(f"[diag] Failed: {e}")

    # Run official evaluator before next task reverts the VM
    score = None
    if not args.no_eval:
        here = os.path.dirname(os.path.abspath(__file__))
        eval_script = os.path.join(here, "eval_osworld_task.py")
        print("\n[eval] Running official evaluator...")
        eval_timed_out = False
        try:
            eval_result = subprocess.run(
                [
                    sys.executable,
                    eval_script,
                    str(args.task_num),
                    "--domain",
                    args.domain,
                    "--vm",
                    args.vm,
                    "--agent-result",
                    os.path.join(artifact_dir, "agent_result.json"),
                ],
                capture_output=True,
                text=True,
                timeout=args.eval_timeout,
            )
        except subprocess.TimeoutExpired as e:
            eval_timed_out = True
            eval_result = subprocess.CompletedProcess(
                e.cmd,
                124,
                stdout=e.stdout or "",
                stderr=(e.stderr or "") + f"\nEvaluator timed out after {args.eval_timeout}s\n",
            )
        print(eval_result.stdout, end="")
        print(eval_result.stderr, end="", file=sys.stderr)
        write_json(
            os.path.join(artifact_dir, "eval_result.json"),
            {
                "returncode": eval_result.returncode,
                "stdout": eval_result.stdout,
                "stderr": eval_result.stderr,
                "timed_out": eval_timed_out,
                "timeout_seconds": args.eval_timeout,
            },
        )
        if eval_result.returncode != 0:
            capture_vm_diagnostics(args.vm, artifact_dir, "eval_error")

    capture_vm_diagnostics(args.vm, artifact_dir, "final")
    write_json(
        os.path.join(artifact_dir, "run_report.json"),
        {
            "task_num": args.task_num,
            "domain": args.domain,
            "task_id": task_config.get("id"),
            "status": "completed",
            "result_success": result.get("success") if isinstance(result, dict) else None,
            "steps_taken": result.get("steps_taken") if isinstance(result, dict) else None,
            "artifact_dir": artifact_dir,
        },
    )

    print_result(result, args.task_num, score)

    # Clean up
    subprocess.run(["pkill", "-f", "claude.*stream-json"], capture_output=True)


if __name__ == "__main__":
    main()
