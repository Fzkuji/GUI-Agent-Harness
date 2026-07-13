"""Compatibility boundary for the OpenProgram dependency.

GUI Agent Harness only needs three OpenProgram concepts:
- ``agentic_function`` for execution tracing and runtime injection
- ``create_runtime`` for provider setup
- a readable action catalog string for planner prompts

Keep OpenProgram internals out of the rest of the harness so provider and
package refactors in OpenProgram do not force matching changes here.
"""

from __future__ import annotations

import importlib
import os
import types
from typing import Callable

from openprogram import agentic_function

from gui_harness.error_monitor import infer_phase_from_stack, record_runtime_error


def _load_create_runtime() -> Callable:
    candidates = (
        "openprogram",
        "openprogram.providers",
        "openprogram.legacy_providers",
    )
    errors: list[str] = []

    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            errors.append(f"{module_name}: {exc}")
            continue

        create = getattr(module, "create_runtime", None)
        if callable(create):
            return create
        errors.append(f"{module_name}: create_runtime missing")

    details = "; ".join(errors)
    raise ImportError(f"No compatible OpenProgram create_runtime found. {details}")


def _default_max_retries() -> int:
    raw = os.environ.get("GUI_HARNESS_OPENPROGRAM_MAX_RETRIES", "5")
    try:
        return max(1, int(raw))
    except ValueError:
        return 5


_ANTHROPIC_MAX_IMG_BYTES = 4_500_000  # API hard limit 5MB/image (HTTP 400 above it)
# Claude Code's Read tool downscales to 2000px long edge and tells the model
# "[Image: original WxH, displayed at wxh. Multiply coordinates by k ...]".
# Claude's grounding is calibrated to exactly this protocol (computer-use
# training): raw 4K via the API scores 30% on SSPro-baseline50 single-shot,
# this protocol 44-48%, the real CLI channel 68%. Opt out per-process with
# GUI_HARNESS_CLAUDE_CC_PROTOCOL=0.
_CC_MAX_SIDE = 2000


def _cc_protocol_enabled() -> bool:
    return os.environ.get("GUI_HARNESS_CLAUDE_CC_PROTOCOL", "1") != "0"


def _prepare_image_for_anthropic(path: str) -> tuple[str, str]:
    """Return (send_path, metadata_line) per the Claude Code image protocol.

    - >2000px long edge: downscale to 2000 (LANCZOS) and return the CC
      metadata line so the model grounds in the displayed space and maps
      back with the explicit factor. Answers stay in ORIGINAL pixel space.
    - >4.5MB after that (or with protocol off): same-resolution JPEG
      re-encode — Anthropic hard-rejects >5MB images (HTTP 400).
    """
    from PIL import Image

    meta_line = ""
    try:
        size_ok = os.path.getsize(path) <= _ANTHROPIC_MAX_IMG_BYTES
    except OSError:
        return path, meta_line

    if _cc_protocol_enabled():
        im = Image.open(path)
        W, H = im.size
        if max(W, H) > _CC_MAX_SIDE:
            k = max(W, H) / _CC_MAX_SIDE
            w, h = round(W / k), round(H / k)
            cache_dir = os.path.join(os.path.dirname(path), "_anthropic_cc2000_cache")
            os.makedirs(cache_dir, exist_ok=True)
            out = os.path.join(
                cache_dir, os.path.splitext(os.path.basename(path))[0] + ".png")
            if not os.path.exists(out) or os.path.getsize(out) == 0:
                im.resize((w, h), Image.LANCZOS).save(out, "PNG")
            meta_line = (f"[Image: original {W}x{H}, displayed at {w}x{h}. "
                         f"Multiply coordinates by {k:.2f} to map to original image.]")
            path = out
            try:
                size_ok = os.path.getsize(path) <= _ANTHROPIC_MAX_IMG_BYTES
            except OSError:
                return path, meta_line

    if size_ok:
        return path, meta_line
    cache_dir = os.path.join(os.path.dirname(path), "_anthropic_jpeg_cache")
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(
        cache_dir, os.path.splitext(os.path.basename(path))[0] + ".jpg")
    if not os.path.exists(out) or os.path.getsize(out) == 0:
        im = Image.open(path).convert("RGB")
        for quality in (92, 85, 75, 60):
            im.save(out, "JPEG", quality=quality)
            if os.path.getsize(out) <= _ANTHROPIC_MAX_IMG_BYTES:
                break
    return out, meta_line


def _wrap_exec_for_anthropic_images(runtime) -> None:
    """Route every image content block through the Claude image protocol.

    One choke point instead of patching each of the ~10 call sites in
    gui_harness.planning that send {"type": "image", "path": ...} blocks.
    Oversized images are downscaled per the CC protocol and the metadata
    line rides along as a text block right before the image.
    """
    original_exec = runtime.exec

    def exec_with_shrink(*args, **kwargs):
        content = kwargs.get("content")
        if content is None and args:
            content, args = args[0], args[1:]
        if isinstance(content, list):
            new_content = []
            for block in content:
                if (isinstance(block, dict) and block.get("type") == "image"
                        and block.get("path")):
                    send_path, meta_line = _prepare_image_for_anthropic(block["path"])
                    if meta_line:
                        new_content.append({"type": "text", "text": meta_line})
                    new_content.append({**block, "path": send_path})
                else:
                    new_content.append(block)
            content = new_content
        if content is not None:
            kwargs["content"] = content
        return original_exec(*args, **kwargs)

    runtime.exec = exec_with_shrink


_CLAUDE_CLI_EXE = os.environ.get(
    "GUI_HARNESS_CLAUDE_CLI_EXE", os.path.expanduser("~/.local/bin/claude.exe"))


class _ClaudeCliRuntime:
    """Runtime adapter that shells out to the Claude Code CLI per exec.

    This IS the channel Claude's grounding is calibrated to (computer-use
    training environment): the CLI's Read tool downscales >2000px images and
    annotates '[Image: original WxH, displayed at wxh. Multiply by k]', the
    image enters as a tool result, and the CC system prompt applies. SSPro
    baseline50 single-shot: 68% here vs 30% raw direct API. Stateless: one
    fresh CLI session per exec, like Runtime.exec with context_mode single.
    """

    def __init__(self, model: str, max_retries: int = 3):
        self.model = model
        self.max_retries = max(1, int(max_retries))
        self.thinking_level = "off"  # CLI owns its own thinking; kept for API parity

    def exec(self, content=None, timeout_s: float | None = None, **_kw) -> str:
        import subprocess

        parts = []
        for block in content or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "text")
            if btype == "text" and block.get("text"):
                parts.append(str(block["text"]))
            elif btype == "image" and block.get("path"):
                parts.append(
                    f"Read the image file at {os.path.abspath(block['path'])} now.")
        prompt = "\n\n".join(parts)
        deadline = (timeout_s or 300) + 120  # CLI startup + tool-loop overhead
        last_err = None
        for _attempt in range(self.max_retries):
            try:
                p = subprocess.run(
                    [_CLAUDE_CLI_EXE, "-p", prompt, "--model", self.model,
                     "--allowedTools", "Read"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=deadline, stdin=subprocess.DEVNULL)
                if p.returncode == 0 and (p.stdout or "").strip():
                    return p.stdout.strip()
                last_err = RuntimeError(
                    f"claude-cli rc={p.returncode}: {(p.stderr or '')[:200]}")
            except subprocess.TimeoutExpired as exc:
                last_err = exc
        raise last_err


class _LocalOpenAIRuntime:
    """Runtime adapter for any OpenAI-compatible /chat/completions endpoint.

    Built for local checkpoint servers (training/tools/serve_qwen_vl_*_api.py)
    so the FULL harness pipeline (commit gate, staged crops, detector
    candidates) can drive a fine-tuned model. Endpoint comes from
    GUI_HARNESS_LOCAL_API_BASE (default http://127.0.0.1:8000/v1). Stateless:
    one single-turn request per exec, like context_mode single.
    """

    def __init__(self, model: str, max_retries: int = 3):
        self.model = model
        self.max_retries = max(1, int(max_retries))
        self.thinking_level = "off"  # kept for API parity
        self.base_url = os.environ.get(
            "GUI_HARNESS_LOCAL_API_BASE", "http://127.0.0.1:8000/v1").rstrip("/")

    @staticmethod
    def _image_to_data_url(path: str) -> str:
        import base64
        import io

        from PIL import Image

        with Image.open(path) as im:
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=92)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    def exec(self, content=None, timeout_s: float | None = None, **_kw) -> str:
        import time

        import requests

        blocks = []
        for block in content or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "text")
            if btype == "text" and block.get("text"):
                blocks.append({"type": "text", "text": str(block["text"])})
            elif btype == "image" and block.get("path"):
                blocks.append({"type": "image_url", "image_url": {
                    "url": self._image_to_data_url(block["path"])}})
        payload = {
            "model": self.model,
            "max_tokens": 512,
            "temperature": 0.0,
            "messages": [{"role": "user", "content": blocks}],
        }
        deadline = (timeout_s or 180) + 60  # generation + server-side image resize
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(f"{self.base_url}/chat/completions",
                                     json=payload, timeout=deadline)
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
                if (text or "").strip():
                    return text
                last_err = RuntimeError("local-openai: empty completion")
            except Exception as exc:  # noqa: BLE001 - retry any transport failure
                last_err = exc
            time.sleep(min(10, 2 ** attempt))
        record_runtime_error(last_err, phase=infer_phase_from_stack(), content=content)
        raise last_err


def create_runtime(provider: str | None = None, model: str | None = None, **kwargs):
    """Create an OpenProgram runtime without binding to one provider module path."""
    if provider == "local-openai":
        return _LocalOpenAIRuntime(
            model or "qwen3-vl-4b",
            max_retries=kwargs.get("max_retries", _default_max_retries()))
    if provider == "claude-cli":
        return _ClaudeCliRuntime(
            model or "claude-opus-4-7",
            max_retries=kwargs.get("max_retries", _default_max_retries()))
    create = _load_create_runtime()
    if model:
        kwargs["model"] = model
    kwargs.setdefault("max_retries", _default_max_retries())
    runtime = create(provider=provider, **kwargs)
    # Some provider runtimes accept-and-ignore compatibility kwargs. Apply the
    # retry budget after construction as well so Harness callers get the
    # requested behavior consistently.
    if hasattr(runtime, "max_retries"):
        runtime.max_retries = max(1, int(kwargs["max_retries"]))
    _disable_default_openprogram_tools(runtime)
    if provider == "claude-code":
        _wrap_exec_for_anthropic_images(runtime)
    return runtime


def _disable_default_openprogram_tools(runtime) -> None:
    """Keep GUI Harness LLM calls text-only unless a caller opts into tools.

    Newer OpenProgram runtimes expose built-in coding tools by default when
    tools is omitted. GUI Harness already owns desktop actions through its
    action registry, so planner/locator/verification calls should not receive
    OpenProgram bash/read/write tools implicitly.
    """
    exec_fn = getattr(runtime, "exec", None)
    if not callable(exec_fn) or getattr(runtime, "_gui_harness_tools_wrapped", False):
        return

    def exec_without_default_tools(self, *args, **exec_kwargs):
        if "tools" in exec_kwargs and exec_kwargs["tools"] is not None:
            try:
                return exec_fn(*args, **exec_kwargs)
            except Exception as exc:
                content = exec_kwargs.get("content")
                if content is None and args:
                    content = args[0]
                record_runtime_error(exc, phase=infer_phase_from_stack(), content=content)
                raise

        # Runtime.exec currently only publishes _current_tools when the value
        # is truthy, so passing tools=[] alone is not enough to suppress the
        # provider default tools. Set the ContextVar around the call instead.
        runtime_mod = importlib.import_module("openprogram.agentic_programming.runtime")
        token = runtime_mod._current_tools.set([])
        try:
            try:
                return exec_fn(*args, **exec_kwargs)
            except Exception as exc:
                content = exec_kwargs.get("content")
                if content is None and args:
                    content = args[0]
                record_runtime_error(exc, phase=infer_phase_from_stack(), content=content)
                raise
        finally:
            runtime_mod._current_tools.reset(token)

    runtime.exec = types.MethodType(exec_without_default_tools, runtime)
    runtime._gui_harness_tools_wrapped = True


def build_action_catalog(available: dict) -> str:
    """Build the planner-visible action catalog from a function registry.

    Only parameters marked ``source="llm"`` are shown. Context-filled values
    such as screenshot path, app name, and runtime stay hidden.
    """
    lines: list[str] = []

    for name, spec in available.items():
        description = spec.get("description", "")
        input_spec = spec.get("input", {})

        llm_params: list[str] = []
        param_details: list[str] = []
        for param_name, param_info in input_spec.items():
            if param_info.get("source") != "llm":
                continue

            type_obj = param_info.get("type", str)
            type_name = getattr(type_obj, "__name__", None) or str(type_obj)
            llm_params.append(f"{param_name}: {type_name}")

            detail = f"    {param_name}"
            if param_info.get("description"):
                detail += f": {param_info['description']}"
            options = param_info.get("options")
            if options:
                option_text = ", ".join(f'"{value}"' for value in options)
                detail += f" (options: {option_text})"
            param_details.append(detail)

        signature = f"{name}({', '.join(llm_params)})" if llm_params else f"{name}()"
        lines.append(signature)

        if description:
            lines.append(f"    {description}")
        lines.extend(param_details)

        if llm_params:
            example_args = ", ".join(
                f'"{param.split(":")[0].strip()}": "..."' for param in llm_params
            )
            lines.append(f'    call: {{"call": "{name}", "args": {{{example_args}}}}}')
        else:
            lines.append(f'    call: {{"call": "{name}"}}')
        lines.append("")

    return "\n".join(lines)
