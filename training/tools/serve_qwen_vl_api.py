#!/usr/bin/env python3
"""Small local HTTP API for Qwen VL models.

It exposes `/generate` and an OpenAI-like `/v1/chat/completions` endpoint for
GUI Agent Harness calls. The loader supports Qwen2.5-VL and Qwen3-VL local
checkpoints.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import torch
from qwen_vl_utils import process_vision_info
from transformers import (
    AutoModelForImageTextToText,
    AutoProcessor,
    Qwen2_5_VLForConditionalGeneration,
    Qwen3VLForConditionalGeneration,
)


MODEL = None
PROCESSOR = None
MODEL_LOCK = threading.Lock()
MODEL_NAME = "Qwen-VL"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    body = handler.rfile.read(length)
    return json.loads(body.decode("utf-8"))


def _save_data_url(data_url: str) -> str:
    header, encoded = data_url.split(",", 1)
    suffix = ".png"
    if "jpeg" in header or "jpg" in header:
        suffix = ".jpg"
    tmp_dir = Path(tempfile.gettempdir()) / "qwen_vl_api_images"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    path = tmp_dir / f"image_{time.time_ns()}{suffix}"
    path.write_bytes(base64.b64decode(encoded))
    return str(path)


def _normalize_image_value(value: str) -> str:
    if value.startswith("data:image/"):
        return _save_data_url(value)
    if value.startswith("file://"):
        return value
    if value.startswith("/") or Path(value).exists():
        return value
    return value


def _normalize_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    normalized = []
    for item in content:
        if not isinstance(item, dict):
            normalized.append({"type": "text", "text": str(item)})
            continue

        item_type = item.get("type")
        if item_type == "image_url":
            image_url = item.get("image_url", {})
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            normalized.append({"type": "image", "image": _normalize_image_value(str(url))})
        elif item_type == "image":
            image_value = item.get("image") or item.get("path") or item.get("url")
            normalized.append({"type": "image", "image": _normalize_image_value(str(image_value))})
        elif item_type == "text":
            normalized.append({"type": "text", "text": str(item.get("text", ""))})
        else:
            normalized.append(item)
    return normalized


def _build_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "messages" in payload:
        messages = []
        for message in payload["messages"]:
            messages.append(
                {
                    "role": message.get("role", "user"),
                    "content": _normalize_content(message.get("content", "")),
                }
            )
        return messages

    prompt = payload.get("prompt") or payload.get("text") or ""
    image_path = payload.get("image") or payload.get("image_path") or payload.get("screenshot")
    content: list[dict[str, str]] = []
    if image_path:
        content.append({"type": "image", "image": _normalize_image_value(str(image_path))})
    content.append({"type": "text", "text": str(prompt)})
    return [{"role": "user", "content": content}]


def generate(payload: dict[str, Any]) -> str:
    assert MODEL is not None
    assert PROCESSOR is not None

    messages = _build_messages(payload)
    max_new_tokens = int(payload.get("max_new_tokens", payload.get("max_tokens", 256)))
    temperature = float(payload.get("temperature", 0.0))
    do_sample = temperature > 0

    text = PROCESSOR.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = PROCESSOR(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    )
    inputs = inputs.to("cuda" if torch.cuda.is_available() else "cpu")

    generation_kwargs = {
        "max_new_tokens": max_new_tokens,
        "do_sample": do_sample,
    }
    if do_sample:
        generation_kwargs["temperature"] = temperature

    with MODEL_LOCK:
        with torch.inference_mode():
            generated_ids = MODEL.generate(**inputs, **generation_kwargs)

    trimmed_ids = [
        output_ids[len(input_ids) :] for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
    ]
    responses = PROCESSOR.batch_decode(trimmed_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return responses[0].strip()


class QwenApiHandler(BaseHTTPRequestHandler):
    server_version = "QwenVLHTTP/0.2"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/health", "/v1/models"}:
            payload = {
                "status": "ok",
                "model": MODEL_NAME,
                "cuda": torch.cuda.is_available(),
                "device_count": torch.cuda.device_count(),
            }
            _json_response(self, 200, payload)
            return
        _json_response(self, 404, {"error": f"unknown path: {path}"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/generate", "/v1/chat/completions"}:
            _json_response(self, 404, {"error": f"unknown path: {path}"})
            return

        try:
            payload = _read_json(self)
            content = generate(payload)
            if path == "/v1/chat/completions":
                response = {
                    "id": f"qwen-vl-{time.time_ns()}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": MODEL_NAME,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                }
            else:
                response = {"model": MODEL_NAME, "response": content}
            _json_response(self, 200, response)
        except Exception as exc:
            _json_response(
                self,
                500,
                {
                    "error": repr(exc),
                    "traceback": traceback.format_exc(limit=8),
                },
            )


def _pick_model_class(model_path: str):
    name = Path(model_path).name.lower()
    if "qwen3-vl" in name:
        return Qwen3VLForConditionalGeneration
    if "qwen2.5-vl" in name or "qwen2_5_vl" in name:
        return Qwen2_5_VLForConditionalGeneration
    return AutoModelForImageTextToText


def load_model(model_path: str, max_pixels: int, min_pixels: int | None) -> None:
    global MODEL, PROCESSOR, MODEL_NAME

    MODEL_NAME = Path(model_path).name
    processor_kwargs: dict[str, Any] = {
        "local_files_only": True,
        "max_pixels": max_pixels,
    }
    if min_pixels is not None:
        processor_kwargs["min_pixels"] = min_pixels
    PROCESSOR = AutoProcessor.from_pretrained(model_path, **processor_kwargs)

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model_kwargs: dict[str, Any] = {
        "torch_dtype": dtype,
        "local_files_only": True,
    }
    if torch.cuda.is_available():
        model_kwargs["device_map"] = "cuda:0"
    attn_impl = os.environ.get("QWEN_API_ATTN_IMPL")
    if attn_impl:
        model_kwargs["attn_implementation"] = attn_impl

    model_cls = _pick_model_class(model_path)
    print(f"Using loader: {model_cls.__name__}", flush=True)
    MODEL = model_cls.from_pretrained(model_path, **model_kwargs).eval()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-pixels", type=int, default=5_760_000)
    parser.add_argument("--min-pixels", type=int, default=None)
    args = parser.parse_args()

    print(f"Loading model from {args.model}", flush=True)
    load_model(args.model, args.max_pixels, args.min_pixels)
    print(f"Model loaded. Serving on http://{args.host}:{args.port}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), QwenApiHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
