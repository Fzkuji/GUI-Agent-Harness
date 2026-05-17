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

from gui_harness.openprogram_compat import agentic_function


@agentic_function(render_range={"depth": 0, "siblings": 0})
def general_action(sub_task: str, task_context: str = "", runtime=None) -> dict:
    """Execute a free-form sub-task on a remote Ubuntu VM using any available tools."""
    from gui_harness.utils import parse_json

    if runtime is None:
        raise ValueError("general_action() requires a runtime argument")
    rt = runtime

    # Build data with VM access info
    data_parts = []
    if task_context:
        data_parts.append(task_context)
    data_parts.append(f"Sub-task: {sub_task}")

    try:
        from gui_harness.action import input as _action_input
        vm_url = getattr(_action_input, '_vm_url', None)
        if vm_url:
            data_parts.append(f"""VM API endpoint: {vm_url}
Run commands:  curl -s -X POST {vm_url}/execute -H 'Content-Type: application/json' -d '{{"command": "YOUR_COMMAND", "shell": true}}'
Read files:    curl -s -X POST {vm_url}/execute -H 'Content-Type: application/json' -d '{{"command": "cat /path/to/file", "shell": true}}'
Fetch web via proxy: curl -s --proxy http://172.16.82.1:6152 'URL'""")
    except Exception:
        pass

    data_parts.append(
        "Use any available tools — shell commands, file I/O, package "
        "installs, web browsing — to complete the sub-task.\n\n"
        "Constraints:\n"
        "- The environment is a REMOTE Ubuntu VM, not local macOS. Every "
        "command and file operation must target the VM via its API; "
        "never use local macOS commands, paths, or apps.\n"
        "- Explore first: before writing new files or scripts, list the "
        "working directory on the VM to reuse existing scripts/templates.\n"
        "- When extracting or copying data, read directly from source "
        "files and copy verbatim — never paraphrase from your own "
        "knowledge.\n"
        "- For website data, curl the page (with the proxy) and parse "
        "the real HTML; do not generate site content from memory. If "
        "curl returns empty content, an HTTP error, or a WAF challenge "
        "(202), you MUST return success=false — never fall back to "
        "invented data.\n"
        "- Preserve format: apply only the changes the sub-task asks "
        "for; keep original dimensions, format, and structure intact.\n"
        "- Verify the output against the sub-task spec before returning "
        "success=true (e.g. check an image's size/mode/format).\n\n"
        "Reply with ONLY this JSON object, no other text:\n"
        '{"success": true, "output": "what you did and the result", '
        '"error": null}'
    )

    reply = rt.exec(content=[
        {"type": "text", "text": "\n\n".join(data_parts)},
    ])

    try:
        return parse_json(reply)
    except Exception:
        return {"success": True, "output": reply[:500]}
