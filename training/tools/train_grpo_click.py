#!/usr/bin/env python3
"""GRPO fine-tune Qwen3-VL on the click-only task: given a (near-)final crop
view + instruction, output {"point_2d": [x, y], ...} in [0,1000]-normalized
space. Reward = 1.0 if the point lands inside the GT bbox, else 0.0 (rule-
based, no reward model — see grpo_reward.py).

This is a deliberately narrow first RL experiment (single-turn, not the full
multi-round crop/recrop/final decision loop) to test whether GRPO can lift
click precision at all before attempting the harder multi-turn formulation.

Data: prepare_grpo_click_data.py output (list of {sample_id, image,
prompt_text, gt_bbox_norm1000, ...}).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
from datasets import Dataset, Image as DsImage  # noqa: E402
from peft import LoraConfig  # noqa: E402
from trl import GRPOConfig, GRPOTrainer  # noqa: E402
from transformers import AutoConfig, AutoModelForImageTextToText, AutoProcessor  # noqa: E402

from grpo_reward import click_bbox_reward, harness_stage_reward  # noqa: E402


def build_dataset(data_path: str) -> Dataset:
    rows = json.loads(Path(data_path).read_text(encoding="utf-8"))
    examples = []
    for r in rows:
        ex = {
            "prompt": [{
                "role": "user",
                "content": [
                    {"type": "image"},
                    {"type": "text", "text": r["prompt_text"]},
                ],
            }],
            "image": r["image"],
            "gt_bbox_norm1000": r["gt_bbox_norm1000"],
        }
        if "task" in r:  # harness-stage rows carry their stage for the reward fn
            ex["task"] = r["task"]
        examples.append(ex)
    ds = Dataset.from_list(examples)
    return ds.cast_column("image", DsImage())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--max-steps", type=int, default=0, help="0 = run full num_train_epochs instead")
    ap.add_argument("--num-epochs", type=float, default=1.0)
    ap.add_argument("--num-generations", type=int, default=4)
    ap.add_argument("--per-device-batch", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-6)
    ap.add_argument("--beta", type=float, default=0.02, help="KL penalty vs reference model")
    ap.add_argument("--lora-rank", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--max-prompt-length", type=int, default=2048)
    ap.add_argument("--max-completion-length", type=int, default=128)
    ap.add_argument("--max-pixels", type=int, default=2097152)
    ap.add_argument("--save-steps", type=int, default=50)
    ap.add_argument("--reward", choices=["click", "harness"], default="click",
                    help="click = bare point-in-box; harness = stage-aware (crop containment / click)")
    args = ap.parse_args()

    print(f"loading dataset from {args.data} ...", flush=True)
    ds = build_dataset(args.data)
    print(f"dataset: {len(ds)} rows", flush=True)

    processor = AutoProcessor.from_pretrained(
        args.model, trust_remote_code=True, max_pixels=args.max_pixels)
    if processor.tokenizer.pad_token is None:
        processor.tokenizer.pad_token = processor.tokenizer.eos_token

    print(f"loading model from {args.model} ...", flush=True)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model, dtype=torch.bfloat16, trust_remote_code=True)
    # trl's GRPOTrainer.__init__ does model.warnings_issued["estimate_tokens"] = True
    # unconditionally; some VLM classes (Qwen3VLForConditionalGeneration here)
    # never initialize this HF-internal dict, so the attribute lookup falls
    # through the whole nn.Module chain and raises. Pre-seed it.
    if not hasattr(model, "warnings_issued"):
        model.warnings_issued = {}

    peft_config = LoraConfig(
        r=args.lora_rank, lora_alpha=args.lora_alpha,
        target_modules="all-linear", task_type="CAUSAL_LM",
    )

    # Known trl+VLM GRPO bug (huggingface/trl#3847): unconstrained sampling
    # can emit a vision/image special token as part of ordinary completion
    # text (no real image data behind it), desyncing the image-token count
    # get_rope_index() expects from image_grid_thw and crashing with a
    # position_ids shape mismatch. Ban those token ids from generation.
    vision_special_tokens = [
        "<|vision_start|>", "<|vision_end|>", "<|vision_pad|>",
        "<|image_pad|>", "<|video_pad|>",
    ]
    vision_special_ids = sorted({
        tid for tid in processor.tokenizer.convert_tokens_to_ids(vision_special_tokens)
        if isinstance(tid, int) and tid >= 0
    })
    print(f"suppressing vision special tokens during generation: {vision_special_ids}", flush=True)

    config = GRPOConfig(
        output_dir=args.output_dir,
        max_steps=args.max_steps if args.max_steps > 0 else -1,
        num_train_epochs=args.num_epochs,
        num_generations=args.num_generations,
        per_device_train_batch_size=args.per_device_batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        beta=args.beta,
        max_completion_length=args.max_completion_length,
        bf16=True,
        gradient_checkpointing=True,
        save_steps=args.save_steps,
        save_total_limit=5,
        logging_steps=1,
        report_to=[],
        temperature=1.0,
        generation_kwargs={"suppress_tokens": vision_special_ids},
    )

    trainer = GRPOTrainer(
        model=model,
        reward_funcs=[harness_stage_reward if args.reward == "harness" else click_bbox_reward],
        args=config,
        train_dataset=ds,
        processing_class=processor,
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    print(f"finished, saved to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
