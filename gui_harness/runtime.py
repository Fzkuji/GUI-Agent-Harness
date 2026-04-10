"""
gui_harness.runtime — GUIRuntime: auto-detect the best available LLM provider.

Priority order:
  1. OpenClaw CLI (`openclaw agent`) ← default, no extra cost
  2. Claude Code CLI (`claude -p`) ← uses subscription
  3. Anthropic API (ANTHROPIC_API_KEY) ← pay per token
  4. OpenAI API (OPENAI_API_KEY) ← pay per token

OpenClaw users: just `pip install -e .` and go. GUIRuntime detects
`openclaw` in PATH and routes all LLM calls through it.

Session mode: @agentic_function(summarize={"depth": 0, "siblings": 0})
skips Context tree injection. The OpenClaw session accumulates context
automatically, so each function only sends its own content.

Usage:
    from gui_harness.runtime import GUIRuntime

    runtime = GUIRuntime()                          # auto-detect (recommended)
    runtime = GUIRuntime(provider="openclaw")        # force OpenClaw
    runtime = GUIRuntime(provider="claude-code")     # force Claude Code CLI
    runtime = GUIRuntime(provider="anthropic")       # force Anthropic API
    runtime = GUIRuntime(provider="openai")          # force OpenAI API
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Optional

from agentic.runtime import Runtime

GUI_SYSTEM_PROMPT = """\
You are a GUI automation agent.

Your role:
- Analyze screenshots, OCR results, and detected UI elements
- Identify target elements and their exact pixel coordinates
- Decide the best actions to achieve the given task
- Return structured JSON responses as requested

Rules:
- ALWAYS use coordinates from OCR/detector output — never estimate from visual inspection
- Be precise: wrong coordinates break automation
- Report exactly what you see; do not hallucinate UI elements
"""


def _detect_provider() -> tuple[str, str]:
    """Auto-detect the best available provider.

    Priority: OpenClaw > Claude Code CLI > Anthropic API > OpenAI API.
    OpenClaw is preferred because it uses your existing OpenClaw setup
    (no extra cost, no separate API keys).

    Returns (provider_name, default_model).
    """
    # Prefer OpenClaw — uses your existing OpenClaw config, no extra cost
    if shutil.which("openclaw"):
        return "openclaw", "default"
    # Claude Code CLI — uses subscription, no per-token cost
    if shutil.which("claude"):
        return "claude-code", "sonnet"
    # Fallback to API providers (expensive)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", "claude-sonnet-4-20250514"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", "gpt-4o"
    raise RuntimeError(
        "No LLM provider found. Options (in order of preference):\n"
        "  1. Install OpenClaw (recommended):\n"
        "     https://github.com/openclaw/openclaw\n"
        "  2. Install Claude Code CLI (uses subscription):\n"
        "     npm install -g @anthropic-ai/claude-code && claude login\n"
        "  3. Set ANTHROPIC_API_KEY (API, pay per token)\n"
        "  4. Set OPENAI_API_KEY (API, pay per token)"
    )


class GUIRuntime(Runtime):
    """
    Auto-detecting GUI runtime. Zero configuration for OpenClaw users.

    Detection priority:
      1. openclaw CLI → _OpenClawRuntime (recommended, no extra cost)
      2. claude CLI → ClaudeCodeRuntime (subscription)
      3. ANTHROPIC_API_KEY → AnthropicRuntime (pay per token)
      4. OPENAI_API_KEY → OpenAIRuntime (pay per token)

    Args:
        provider:   Force a provider: "openclaw", "claude-code", "anthropic", "openai".
                    If None, auto-detects.
        model:      Model name override.
        system:     System prompt override.
        max_tokens: Max response tokens (default: 4096).
        **kwargs:   Forwarded to the underlying provider Runtime.
    """

    def __init__(
        self,
        provider: str = None,
        model: str = None,
        system: str = None,
        max_tokens: int = 4096,
        **kwargs,
    ):
        # Detect or use specified provider
        if provider:
            detected_provider = provider
            # Set sensible default model per provider
            default_models = {
                "openclaw": "default",
                "claude-code": "sonnet",
                "anthropic": "claude-sonnet-4-20250514",
                "openai": "gpt-4o",
            }
            detected_model = model or default_models.get(provider, "default")
        else:
            detected_provider, detected_model = _detect_provider()

        use_model = model or detected_model
        use_system = system or GUI_SYSTEM_PROMPT

        # Create the actual provider runtime
        if detected_provider == "openclaw":
            self._inner = _OpenClawRuntime(model=use_model, system=use_system)
        elif detected_provider == "anthropic":
            from agentic.providers.anthropic import AnthropicRuntime
            self._inner = AnthropicRuntime(
                model=use_model,
                system=use_system,
                max_tokens=max_tokens,
                **kwargs,
            )
        elif detected_provider == "openai":
            from agentic.providers.openai import OpenAIRuntime
            self._inner = OpenAIRuntime(
                model=use_model,
                system=use_system,
                max_tokens=max_tokens,
                **kwargs,
            )
        elif detected_provider == "claude-code":
            from agentic.providers.claude_code import ClaudeCodeRuntime
            # Main runtime: execution with Bash only (no local Read/Write/Edit)
            self._inner = ClaudeCodeRuntime(
                model=use_model,
                tools="Bash",
                **kwargs,
            )
            # Planning runtime: no tools, -p mode (for text-only analysis/decisions)
            self._planner = _ClaudeCodePlannerRuntime(
                model=use_model,
                cli_path=self._inner.cli_path,
            )
        else:
            raise ValueError(f"Unknown provider: {detected_provider}")

        super().__init__(model=use_model, max_retries=1)
        self.provider = detected_provider

    def plan(self, content: list[dict], **kwargs) -> str:
        """Call the planning runtime (no tools, pure text).

        Use this for analysis, decision-making, and any call where
        the LLM should NOT execute commands.
        """
        if hasattr(self, '_planner'):
            return self._planner._call(content, **kwargs)
        return self._call(content, **kwargs)

    def _call(
        self,
        content: list[dict],
        model: str = "default",
        response_format: Optional[dict] = None,
    ) -> str:
        """Delegate to the detected provider."""
        return self._inner._call(content, model=model, response_format=response_format)


class _OpenClawRuntime(Runtime):
    """
    Routes LLM calls through `openclaw agent` CLI.

    Uses your existing OpenClaw configuration — no separate API keys,
    no per-token cost beyond what your OpenClaw setup already covers.
    """

    def __init__(self, model: str = "default", system: str = None, timeout: int = 120):
        super().__init__(model=model)
        self.system = system or GUI_SYSTEM_PROMPT
        self.timeout = timeout
        self._openclaw_path = shutil.which("openclaw")
        self._session_id = None  # will be set on first call for continuity

    def _call(
        self,
        content: list[dict],
        model: str = "default",
        response_format: Optional[dict] = None,
    ) -> str:
        import subprocess
        import json
        import uuid

        # Build prompt from content blocks
        # OpenClaw agent has an `image` tool — reference image paths directly
        # so the agent can analyze them with its built-in vision capabilities.
        parts = []
        if self.system:
            parts.append(self.system)
            parts.append("")

        image_paths = []
        for block in content:
            if block.get("type") == "text":
                parts.append(block["text"])
            elif block.get("type") == "image":
                path = block.get("path", "")
                if path:
                    image_paths.append(path)

        # Tell the agent to analyze attached images using its image tool
        if image_paths:
            paths_str = ", ".join(image_paths)
            parts.append(
                f"\nAnalyze the following image(s) using your image tool: {paths_str}"
                f"\nIncorporate the visual analysis into your response."
            )

        if response_format:
            parts.append(f"\nReturn ONLY valid JSON matching: {json.dumps(response_format)}")

        prompt = "\n".join(parts)

        # Assign a session ID for continuity across calls
        if self._session_id is None:
            self._session_id = str(uuid.uuid4())

        cmd = [
            self._openclaw_path, "agent",
            "--message", prompt,
            "--session-id", self._session_id,
            "--json",
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=self.timeout, env=os.environ,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"openclaw agent failed (exit {result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )

        # Parse JSON output — extract reply text from payloads
        try:
            data = json.loads(result.stdout.strip())
            payloads = data.get("result", {}).get("payloads", [])
            if payloads:
                return payloads[0].get("text", result.stdout.strip())
            return data.get("reply", data.get("message", result.stdout.strip()))
        except json.JSONDecodeError:
            return result.stdout.strip()


class _ClaudeCodePlannerRuntime(Runtime):
    """Claude Code CLI in print mode with no tools — for pure text planning.

    Uses `claude -p --tools ""` for each call (single-shot, no persistent session).
    Cannot execute any commands, read/write files, or use any tools.
    Only returns text responses.  Supports images via stream-json input format.
    """

    def __init__(self, model: str = "opus", cli_path: str = None, timeout: int = 120):
        super().__init__(model=model)
        self.cli_path = cli_path or shutil.which("claude")
        self.timeout = timeout

    def _call(
        self,
        content: list[dict],
        model: str = "default",
        response_format=None,
    ) -> str:
        import subprocess

        use_model = model if model != "default" else self.model

        has_images = any(
            b.get("type") == "image" and (b.get("path") or b.get("data"))
            for b in content
        )

        if has_images:
            return self._call_with_images(content, use_model, response_format)

        # Text-only: simple path
        parts = [b["text"] for b in content if b.get("type") == "text"]
        prompt = "\n".join(parts)

        cmd = [self.cli_path, "-p", "--tools", "", "--model", use_model]
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout)

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code planner failed (exit {result.returncode}): "
                f"{result.stderr.strip()[:200]}"
            )
        return result.stdout.strip()

    def _call_with_images(self, content: list[dict], model: str, response_format=None) -> str:
        """Stream-json mode for image support."""
        import subprocess
        import base64

        anthropic_content = []
        for block in content:
            if block.get("type") == "text":
                anthropic_content.append({"type": "text", "text": block["text"]})
            elif block.get("type") == "image":
                path = block.get("path", "")
                if path and os.path.isfile(path):
                    with open(path, "rb") as f:
                        data = base64.b64encode(f.read()).decode()
                    ext = os.path.splitext(path)[1].lower()
                    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext.lstrip("."), "image/png")
                    anthropic_content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    })

        if response_format:
            anthropic_content.append({
                "type": "text",
                "text": f"\n\nRespond with ONLY valid JSON matching: {json.dumps(response_format)}",
            })

        stream_msg = json.dumps({
            "type": "user",
            "message": {"role": "user", "content": anthropic_content},
        })

        cmd = [
            self.cli_path, "-p",
            "--tools", "",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--model", model,
        ]

        result = subprocess.run(cmd, input=stream_msg, capture_output=True, text=True, timeout=self.timeout)

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code planner failed (exit {result.returncode}): "
                f"{result.stderr.strip()[:200]}"
            )

        # Parse stream-json output
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "result":
                    return data.get("result", "")
                if data.get("type") == "assistant" and "message" in data:
                    msg = data["message"]
                    if isinstance(msg, dict) and "content" in msg:
                        texts = [b["text"] for b in msg["content"] if b.get("type") == "text"]
                        if texts:
                            return "\n".join(texts)
            except (json.JSONDecodeError, KeyError):
                continue

        return result.stdout.strip()

    def reset(self):
        """No-op — print mode has no persistent session."""
        pass
