"""
gui_harness.adapters.vm_adapter — VM-based backend configuration.

Configures the unified input system to route actions to a remote VM.
Also patches screenshot to download from VM.

Usage:
    from gui_harness.adapters.vm_adapter import patch_for_vm
    patch_for_vm("http://172.16.105.128:5000")
"""

from __future__ import annotations

from contextlib import contextmanager
import os
import subprocess
import threading
import time

from gui_harness.perception import screenshot as _screenshot


_HOST_TAKE = _screenshot.take
_HOST_TAKE_WINDOW = _screenshot.take_window
_TARGET_LOCK = threading.RLock()


def _select_vm(vm_url: str) -> None:
    url = vm_url.rstrip("/")
    from gui_harness.action import input as _input

    _input.configure(vm_url=url)
    _screenshot.take = lambda path="/tmp/gui_agent_screen.png": _vm_screenshot(
        url, path
    )
    _screenshot.take_window = (
        lambda app, out=None: _vm_screenshot(
            url, out or "/tmp/gui_agent_screen.png"
        )
    )


def patch_for_vm(vm_url: str):
    """Configure all subsystems to use the VM backend."""
    with _TARGET_LOCK:
        _select_vm(vm_url)


@contextmanager
def target_session(vm_url: str | None = None):
    """Select one screen target for a bounded call and restore it afterwards."""
    from gui_harness.action import input as _input

    with _TARGET_LOCK:
        previous_target = _input.get_default_name()
        previous_target_object = _input.get_target(previous_target)
        previous_backend = _input._backend
        previous_vm_url = _input._vm_url
        previous_take = _screenshot.take
        previous_take_window = _screenshot.take_window
        try:
            if vm_url:
                _select_vm(vm_url)
            else:
                _input.set_default("local")
                _screenshot.take = _HOST_TAKE
                _screenshot.take_window = _HOST_TAKE_WINDOW
            yield
        finally:
            _input.register(previous_target, previous_target_object)
            _input.set_default(previous_target)
            _input._backend = previous_backend
            _input._vm_url = previous_vm_url
            _screenshot.take = previous_take
            _screenshot.take_window = previous_take_window


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _vm_screenshot(vm_url: str, path: str = "/tmp/gui_agent_screen.png") -> str:
    """Download screenshot from VM via curl.

    Retries on transient failures and validates the result is a real PNG.
    A silent failure here is the root of the screenshot-read cascade: an
    unchecked curl leaves a stale or 0-byte file at ``path``, downstream
    detection then crashes ('need at least one array to stack') and the
    corrupt file gets sent to the model as an invalid image (HTTP 400).
    """
    errors: list[str] = []
    for attempt in range(3):
        try:
            proc = subprocess.run(
                ["/usr/bin/curl", "-sS", "--connect-timeout", "10", "-m", "15",
                 "-o", path, f"{vm_url}/screenshot"],
                capture_output=True, timeout=20,
            )
        except subprocess.TimeoutExpired:
            errors.append(f"attempt {attempt + 1}: curl timed out")
            time.sleep(1.0 * (attempt + 1))
            continue

        if proc.returncode != 0:
            errors.append(
                f"attempt {attempt + 1}: curl exit {proc.returncode}: "
                f"{proc.stderr.decode('utf-8', 'replace').strip()}"
            )
            time.sleep(1.0 * (attempt + 1))
            continue

        # curl succeeded — verify the file is a non-empty, real PNG.
        try:
            with open(path, "rb") as fh:
                head = fh.read(8)
        except OSError as e:
            errors.append(f"attempt {attempt + 1}: cannot read {path}: {e}")
            time.sleep(1.0 * (attempt + 1))
            continue

        size = os.path.getsize(path) if os.path.exists(path) else 0
        if size == 0 or head != _PNG_MAGIC:
            errors.append(
                f"attempt {attempt + 1}: not a PNG (size={size}, "
                f"head={head!r}) — VM /screenshot likely returned an error body"
            )
            time.sleep(1.0 * (attempt + 1))
            continue

        return path

    raise RuntimeError(
        f"VM screenshot failed after 3 attempts ({vm_url}/screenshot):\n"
        + "\n".join(errors)
    )
