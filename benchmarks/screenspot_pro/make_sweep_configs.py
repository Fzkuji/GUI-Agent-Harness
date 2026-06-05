#!/usr/bin/env python3
"""从 quality_8round.yaml 派生单变量扫描的 config 组：
  base       = quality_8round 原样（candidate_sort=relevance 已是默认）
  每个 arm   = 在 base 上只翻转一个开关

保证除被翻转项外所有字段与 base 完全一致（单变量）。输出到 configs/sweep/。
"""
from __future__ import annotations
import os
import sys
import yaml
import dataclasses

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from gui_harness.planning.screenspot_locator import ScreenSpotLocatorConfig  # noqa: E402

HERE = os.path.dirname(__file__)
BASE_CFG = os.path.join(HERE, "configs", "quality_8round.yaml")
OUT_DIR = os.path.join(HERE, "configs", "sweep")

# arm 名 -> {翻转的字段: 新值}。base 不翻转。
# 方向说明：翻转后变好 => 该字段当前(base)设置不是最优；翻转后变差 => base 设置有用。
ARMS = {
    "base": {},
    # 关掉默认开着的验证/引导步骤
    "no_crop_check": {"enable_crop_check": False},
    "no_final_recheck": {"enable_final_recheck": False},
    "no_staged_crop": {"enable_staged_crop": False},
    "no_final_cand_detect": {"enable_final_candidate_detect": False},
    "no_final_recrop": {"enable_final_recrop": False},
    # 开启默认关着的（今天测过单变量，这次叠在 sort 基准上）
    "reason_first": {"reasoning_first": True},
    "coords_local": {"coords_crop_local": True},
    # 枚举/数值换档
    "crop_check_last": {"crop_check_mode": "last_only"},
    "dedup_05": {"candidate_dedup_iou": 0.5},
    "scale_target_px": {
        "iterative_scale_mode": "target_pixels",
        "iterative_target_pixels": 1500000,
        "iterative_final_target_pixels": 2500000,
    },
}


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    base_yaml = yaml.safe_load(open(BASE_CFG))
    base_yaml = {k: v for k, v in base_yaml.items() if not str(k).startswith("_")}
    # 用 dataclass 补全所有默认值，使每个 config 完整、显式（便于审阅单变量差异）
    full = dataclasses.asdict(ScreenSpotLocatorConfig(**base_yaml))

    for arm, override in ARMS.items():
        cfg = dict(full)
        cfg.update(override)
        path = os.path.join(OUT_DIR, f"{arm}.yaml")
        header = (
            f"# 单变量扫描 arm: {arm}\n"
            f"# base = quality_8round.yaml（已含 candidate_sort=relevance）\n"
            f"# 本 arm 相对 base 的改动: {override or '（无，基准）'}\n"
        )
        with open(path, "w") as fh:
            fh.write(header)
            yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=True)
        print(f"wrote {arm}.yaml  override={override}")


if __name__ == "__main__":
    main()
