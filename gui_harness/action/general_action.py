"""
gui_harness.action.general_action — general-purpose action executed by the agent.

Unlike GUI actions (click, type, etc.) which are specific operations,
general_action gives the agent a sub-task description and lets it use
any available tools to complete it: shell commands, file I/O, keyboard
shortcuts, web browsing, etc.

The agent runs in interactive mode with full tool access (Bash, Read,
Write, etc.) and reports the result when done.
"""

from __future__ import annotations

from agentic import agentic_function

_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        from gui_harness.runtime import GUIRuntime
        _runtime = GUIRuntime()
    return _runtime


@agentic_function(summarize={"depth": 0, "siblings": 0})
def general_action(sub_task: str, task_context: str = "", runtime=None) -> dict:
    """Execute a sub-task using any available tools.

    You are given a specific sub-task to complete. You have full freedom
    to use any tools and methods available to you:
    - Run shell commands (bash)
    - Read and write files
    - Use keyboard shortcuts via pyautogui
    - Browse the web
    - Install packages
    - Anything else you need

    Complete the sub-task and report the result.

    Return JSON:
    {
      "success": true/false,
      "output": "what you did and the result",
      "error": null or "error description"
    }
    """
    from gui_harness.utils import parse_json

    rt = runtime or _get_runtime()

    # Add VM context if available
    vm_info = ""
    try:
        from gui_harness.action import input as _action_input
        vm_url = getattr(_action_input, '_vm_url', None)
        if vm_url:
            vm_info = f"""
IMPORTANT: You are operating on a REMOTE Ubuntu VM, NOT on local macOS.
All commands and file operations must target the VM at {vm_url}.

To run commands on the VM:
  curl -s -X POST {vm_url}/execute -H 'Content-Type: application/json' -d '{{"command": "YOUR_COMMAND", "shell": true}}'
To read files on the VM:
  curl -s -X POST {vm_url}/execute -H 'Content-Type: application/json' -d '{{"command": "cat /path/to/file", "shell": true}}'
To write files on the VM:
  curl -s -X POST {vm_url}/execute -H 'Content-Type: application/json' -d '{{"command": "echo content > /path/to/file", "shell": true}}'

Do NOT use local macOS commands, local file paths, or local applications.
All paths like /home/user/... are on the VM.
"""
    except Exception:
        pass

    # Build prompt with full context
    prompt_parts = []
    if task_context:
        prompt_parts.append(task_context)
    prompt_parts.append(f"Sub-task: {sub_task}")
    if vm_info:
        prompt_parts.append(vm_info)
    prompt_parts.append(
        "IMPORTANT: When extracting or copying data (descriptions, names, numbers, text), "
        "always read directly from source files. Do NOT generate or paraphrase content from "
        "your own knowledge — copy verbatim from the actual data.\n\n"
        "IMPORTANT: When you need data from a website (e.g., IMDB, Wikipedia, etc.), use "
        "curl with proxy to fetch the actual webpage HTML on the VM and parse it with Python. "
        "Use: curl -s --proxy http://172.16.82.1:6152 'URL' to fetch pages via the proxy. "
        "Then parse with python3 and BeautifulSoup. Do NOT rely on your own knowledge to generate website content.\n\n"
        "CRITICAL: If curl/requests returns empty content, HTTP error, WAF challenge (202), "
        "or you cannot get real data from the website, you MUST return {\"success\": false, "
        "\"error\": \"Failed to fetch web data\", \"output\": \"description of what went wrong\"}. "
        "NEVER fall back to generating data from your own knowledge. If you cannot get real data, FAIL the task."
    )
    prompt_parts.append("Complete this and return JSON with success/output/error.")

    reply = rt.exec(content=[
        {"type": "text", "text": "\n".join(prompt_parts)},
    ])

    try:
        return parse_json(reply)
    except Exception:
        return {"success": True, "output": reply[:500]}
