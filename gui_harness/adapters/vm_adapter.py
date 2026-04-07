"""
gui_harness.adapters.vm_adapter — VM-based backend configuration.

Configures the unified input system to route actions to a remote VM.
Also patches screenshot to download from VM.

Usage:
    from gui_harness.adapters.vm_adapter import patch_for_vm
    patch_for_vm("http://172.16.105.128:5000")
"""

from __future__ import annotations

import json
import subprocess


def patch_for_vm(vm_url: str):
    """Configure all subsystems to use the VM backend."""
    url = vm_url.rstrip("/")

    # 1. Configure input backend
    from gui_harness.action import input as _input
    _input.configure(vm_url=url)

    # 2. Patch screenshot to download from VM
    import gui_harness.perception.screenshot as _ss
    _ss.take = lambda path="/tmp/gui_agent_screen.png": _vm_screenshot(url, path)
    _ss.take_window = lambda app, out=None: _vm_screenshot(url, out or "/tmp/gui_agent_screen.png")


def _vm_screenshot(vm_url: str, path: str = "/tmp/gui_agent_screen.png") -> str:
    """Download screenshot from VM via curl."""
    subprocess.run(
        ["/usr/bin/curl", "-s", "--connect-timeout", "10", "-m", "15",
         "-o", path, f"{vm_url}/screenshot"],
        capture_output=True, timeout=20,
    )
    return path
