"""
gui_harness.runtime — GUIRuntime: routes LLM calls through OpenClaw gateway.

OpenClaw gateway manages its own session history, so we do NOT inject
Context tree summaries into the LLM prompt. Each exec() call sends
only its own content — the gateway accumulates conversation context.

The Context tree (@agentic_function) still records everything for
debugging and save() — it just doesn't feed back into LLM calls.

Usage:
    from gui_harness.runtime import GUIRuntime

    runtime = GUIRuntime()  # uses localhost:18789 by default

    @agentic_function
    def observe(task):
        return runtime.exec(content=[
            {"type": "text", "text": f"Find: {task}"},
            {"type": "image", "path": "/tmp/screenshot.png"},
        ])
"""

from __future__ import annotations

import base64
import mimetypes
import os
from typing import Optional

import httpx

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
- When in doubt about element identity, use the OCR text as ground truth
- Report exactly what you see; do not hallucinate UI elements
"""


class GUIRuntime(Runtime):
    """
    GUI-optimized runtime that routes calls through OpenClaw gateway.

    Key design: the gateway manages its own conversation session, so
    exec() does NOT inject Context tree summaries. Each call sends
    only its own content blocks.

    Args:
        gateway_url:    OpenClaw gateway URL (default: http://localhost:18789).
        auth_token:     Gateway auth token (reads OPENCLAW_GATEWAY_TOKEN if not set).
        model:          Model name (default: "anthropic/claude-sonnet-4-6").
        system:         System prompt (default: GUI_SYSTEM_PROMPT).
        max_tokens:     Max response tokens (default: 4096).
        timeout:        Request timeout in seconds (default: 120).
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:18789",
        auth_token: str = None,
        model: str = "anthropic/claude-sonnet-4-6",
        system: str = None,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ):
        super().__init__(model=model)
        self.gateway_url = gateway_url.rstrip("/")
        self.auth_token = auth_token or os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")
        self.system = system or GUI_SYSTEM_PROMPT
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._session_messages: list[dict] = []

    def exec(
        self,
        content: list[dict],
        context: Optional[str] = None,
        response_format: Optional[dict] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Call the LLM via OpenClaw gateway.

        Context injection is controlled by each @agentic_function's
        `summarize` parameter:
          - API mode: summarize=None (default) → full context injected
          - Session mode: summarize={"depth": 0, "siblings": 0} → no injection

        When using OpenClaw as the runtime (session mode), set
        summarize={"depth": 0, "siblings": 0} on your @agentic_function
        decorators so only the current call's content is sent.
        """
        return super().exec(content=content, context=context, response_format=response_format, model=model)

    def _call(
        self,
        content: list[dict],
        model: str = "default",
        response_format: Optional[dict] = None,
    ) -> str:
        """Send content to OpenClaw gateway's /v1/chat/completions endpoint."""
        use_model = model if model != "default" else self.model

        # Convert content blocks to OpenAI format
        user_content = []
        for block in content:
            converted = self._convert_block(block)
            if converted:
                user_content.append(converted)

        # Build messages
        messages = [{"role": "system", "content": self.system}]
        messages.extend(self._session_messages)
        messages.append({"role": "user", "content": user_content})

        # Request
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        payload = {
            "model": use_model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        response = httpx.post(
            f"{self.gateway_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        data = response.json()
        reply = data["choices"][0]["message"]["content"]

        # Accumulate session history
        self._session_messages.append({"role": "user", "content": user_content})
        self._session_messages.append({"role": "assistant", "content": reply})

        return reply

    def reset_session(self):
        """Clear conversation history. Start fresh."""
        self._session_messages = []

    def _convert_block(self, block: dict) -> Optional[dict]:
        """Convert a generic content block to OpenAI chat format."""
        block_type = block.get("type", "text")

        if block_type == "text":
            return {"type": "text", "text": block["text"]}

        if block_type == "image":
            # Image from URL
            if "url" in block:
                return {
                    "type": "image_url",
                    "image_url": {"url": block["url"]},
                }

            # Image from base64 data
            if "data" in block:
                media_type = block.get("media_type", "image/png")
                data_url = f"data:{media_type};base64,{block['data']}"
                return {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                }

            # Image from file path
            if "path" in block:
                path = block["path"]
                media_type = mimetypes.guess_type(path)[0] or "image/png"
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
                data_url = f"data:{media_type};base64,{data}"
                return {
                    "type": "image_url",
                    "image_url": {"url": data_url},
                }

        # Unknown block type — pass text representation
        if "text" in block:
            return {"type": "text", "text": block["text"]}

        return None
