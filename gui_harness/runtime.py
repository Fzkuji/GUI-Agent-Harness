"""
gui_harness.runtime — GUIRuntime: auto-detect the best available LLM provider.

Priority order:
  1. Anthropic API (ANTHROPIC_API_KEY env var)
  2. OpenAI API (OPENAI_API_KEY env var)
  3. Claude Code CLI (claude binary in PATH)

OpenClaw users: OpenClaw sets ANTHROPIC_API_KEY or OPENAI_API_KEY in its
environment, so GUIRuntime auto-detects and works out of the box.
No manual configuration needed.

Session mode: @agentic_function(summarize={"depth": 0, "siblings": 0})
ensures the OpenClaw agent's session handles context accumulation.
Each function only sends its own content to the LLM.

Usage:
    from gui_harness.runtime import GUIRuntime

    runtime = GUIRuntime()  # auto-detects provider
    # or explicitly:
    runtime = GUIRuntime(provider="anthropic", model="claude-sonnet-4-20250514")
    runtime = GUIRuntime(provider="openai", model="gpt-4o")
"""

from __future__ import annotations

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

    Returns (provider_name, default_model).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", "claude-sonnet-4-20250514"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", "gpt-4o"
    if shutil.which("claude"):
        return "claude-code", "sonnet"
    raise RuntimeError(
        "No LLM provider found. Set one of:\n"
        "  - ANTHROPIC_API_KEY (recommended)\n"
        "  - OPENAI_API_KEY\n"
        "  - Install Claude Code CLI: npm install -g @anthropic-ai/claude-code\n"
        "\n"
        "OpenClaw users: OpenClaw sets these automatically. "
        "Make sure OpenClaw is running."
    )


class GUIRuntime(Runtime):
    """
    Auto-detecting GUI runtime.

    Picks the best available provider based on environment:
      - ANTHROPIC_API_KEY → AnthropicRuntime (Claude, with prompt caching)
      - OPENAI_API_KEY → OpenAIRuntime (GPT-4o vision)
      - claude CLI → ClaudeCodeRuntime (no API key, uses subscription)

    OpenClaw users: OpenClaw manages API keys in its environment.
    GUIRuntime auto-detects them — zero configuration needed.

    Args:
        provider:   Force a provider ("anthropic", "openai", "claude-code").
                    If None, auto-detects.
        model:      Model name override.
        system:     System prompt override.
        max_tokens: Max response tokens (default: 4096).
        **kwargs:   Forwarded to the provider Runtime.
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
            detected_model = model or "default"
        else:
            detected_provider, detected_model = _detect_provider()

        use_model = model or detected_model
        use_system = system or GUI_SYSTEM_PROMPT

        # Create the actual provider runtime
        if detected_provider == "anthropic":
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
                system_prompt=use_system,
                max_tokens=max_tokens,
                **kwargs,
            )
        elif detected_provider == "claude-code":
            from agentic.providers.claude_code import ClaudeCodeRuntime
            self._inner = ClaudeCodeRuntime(
                model=use_model,
                **kwargs,
            )
        else:
            raise ValueError(f"Unknown provider: {detected_provider}")

        super().__init__(model=use_model)
        self.provider = detected_provider

    def _call(
        self,
        content: list[dict],
        model: str = "default",
        response_format: Optional[dict] = None,
    ) -> str:
        """Delegate to the detected provider."""
        return self._inner._call(content, model=model, response_format=response_format)
