#!/usr/bin/env python3
"""Qwen-VL HTTP API with optional PEFT LoRA adapter loading."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from http.server import ThreadingHTTPServer
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoProcessor

import serve_qwen_vl_api as base


def load_model(model_path: str, adapter_path: str | None, max_pixels: int, min_pixels: int | None) -> None:
    base.MODEL_NAME = Path(model_path).name if not adapter_path else f"{Path(model_path).name}+{Path(adapter_path).name}"

    processor_kwargs: dict[str, Any] = {
        "local_files_only": True,
        "max_pixels": max_pixels,
    }
    if min_pixels is not None:
        processor_kwargs["min_pixels"] = min_pixels
    base.PROCESSOR = AutoProcessor.from_pretrained(model_path, **processor_kwargs)

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

    model_cls = base._pick_model_class(model_path)
    print(f"Using loader: {model_cls.__name__}", flush=True)
    model = model_cls.from_pretrained(model_path, **model_kwargs)
    if adapter_path:
        print(f"Loading LoRA adapter from {adapter_path}", flush=True)
        model = PeftModel.from_pretrained(model, adapter_path, is_trainable=False)
    base.MODEL = model.eval()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--adapter", default="")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--max-pixels", type=int, default=5_760_000)
    parser.add_argument("--min-pixels", type=int, default=None)
    args = parser.parse_args()

    adapter = args.adapter or None
    print(f"Loading model from {args.model}", flush=True)
    if adapter:
        print(f"Adapter: {adapter}", flush=True)
    load_model(args.model, adapter, args.max_pixels, args.min_pixels)
    print(f"Model loaded. Serving on http://{args.host}:{args.port}", flush=True)

    server = ThreadingHTTPServer((args.host, args.port), base.QwenApiHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
