# ScreenSpot-Pro 定位器配置（configs/）

每个 `.yaml` 是一套完整的 `ScreenSpotLocatorConfig`，一个文件配置整个 run 的行为
（LlamaFactory 风格，不用环境变量）。跑法：

```bash
python benchmarks/screenspot_pro/run_screenspot_pro.py \
  --config benchmarks/screenspot_pro/configs/<名字>.yaml \
  --annotation <app>.json --indexes <range> --provider <p> --model <m> ...
```

本文件解释这些配置**为什么存在、各自怎么来的、互相什么关系**。

## TL;DR — 该用哪个

| 场景 | 用哪个 |
|---|---|
| 追求最高精度、不在乎 LLM 调用次数（GPT / Claude） | `quality_8round` |
| M3 等单次推理慢的模型，要省调用 | **`m3_optimal`**（现有证据下的最优） |
| 复现/对照最原始结果 | `legacy_baseline`（仅对照，勿用于新实验） |

仓库里全量 1581 样本的 GPT-5.5 结果（87.9%）跑的是 **`legacy_baseline`** —— 它是
**基准不是最优**，后续配置都是在它基础上逐项改进。

## 演进关系

```
legacy_baseline  ──+preserve缩放 +cache prompt +candidate_sort──►  quality_8round
（最原始基线,8轮）                                                  （质量优先,8轮,精度最高）
       │
       └──5轮+只末轮复查（省调用骨架,适合M3慢模型）──►  m3_fast  ──+candidate_sort──►  m3_optimal ★
                                                          │                          （现有证据下最优）
                                                          ├─缩放换target_pixels──►  m3_fast_adaptive
                                                          └─（更早的同类版,已废弃）  fast
```

两条优化主线：
1. **prompt/缩放/候选质量**（不增加调用）：fill→preserve、legacy→cache、+candidate_sort。
   这三项都进了 quality_8round；其中 candidate_sort 是消融里**唯一确认稳定正收益**的开关。
2. **省调用**（为 M3 这种单次慢的模型）：8 轮每轮复查 → 5 轮只末轮复查，
   每样本 LLM 调用从 ~16 降到 ~6。这条线是 m3_fast / m3_fast_adaptive / fast。

`m3_optimal` = 两条线的交集（省调用骨架 + candidate_sort），是目前不依赖参数扫描
即可确定的最优组合。

## 关键字段对照

| 字段 | legacy_baseline | quality_8round | m3_fast | m3_fast_adaptive | **m3_optimal** | fast(废弃) |
|---|---|---|---|---|---|---|
| iterative_rounds | 8 | 8 | 5 | 5 | 5 | 5 |
| crop_check_mode | every | every | last_only | last_only | last_only | last_only |
| enable_final_recheck | True | True | False | False | False | False |
| crop_retry_limit | 6 | 6 | 3 | 3 | 3 | 3 |
| candidate_sort | none | **relevance** | none | none | **relevance** | none |
| iterative_scale_mode | fill | preserve | preserve | target_pixels | preserve | preserve |
| iterative_max_side | 2048 | 0(不限) | 3072 | 0 | 3072 | 0 |
| iterative_prompt_layout | legacy | cache | cache | cache | cache | cache |
| context_mode | single | single | single | single | single | single |
| 每样本调用量(约) | ~16 | ~16 | ~6 | ~6 | ~6 | ~6 |

## 各配置详解

### legacy_baseline（原 main_baseline）— 最原始基线
复现 main(a3d0a35) 的设置：`fill` 老缩放（中小图放大填满 max_side=2048）+ `legacy`
内联 prompt + 8 轮 + 每轮复查，无 candidate_sort。**全量 1581 GPT-5.5 结果（87.9%）跑的就是它。**
定位是基准/对照，不是最优。

### quality_8round（原 known_good）— 质量优先
在 legacy_baseline 上做三项改进：缩放 `fill→preserve`（不缩中小图，小目标更清晰）、
prompt `legacy→cache`（规则前置吃缓存，省 token，行为等价）、`candidate_sort none→relevance`。
保留 8 轮 + 每轮复查（精度优先）。精度最高但调用最多。`start_full_autoretry.py` 全量跑默认用它。

### m3_fast（原 m3_best）— M3 省调用骨架
为 M3 这种单次推理慢的模型设计：5 轮 + 只末轮复查（`crop_check_mode=last_only`）+
复查拒绝时 `widen` 回退到更宽的框（不从头重裁、不打转）+ 图限 `max_side=3072`
（修 MiniMax HTTP400）。调用量比 quality_8round 少约 ⅔。**但漏了 candidate_sort。**

### m3_fast_adaptive（原 m3_target）— 自适应缩放变体
与 m3_fast 同骨架，唯一差异：缩放用 `target_pixels`（按裁剪框大小自动定放大倍数，
送模型的图像素量恒定 ~1.5MP/final ~2.5MP）。preserve 与 target_pixels 哪个更好
尚未直接对比（参数扫描的 `scale_target_px` arm 在测）。同样没开 candidate_sort。

### m3_optimal ★ — 现有证据下的最优
= m3_fast 省调用骨架 + `candidate_sort=relevance`。把"省调用"和"唯一确认有收益的
开关"合到一起，与 m3_fast 唯一差异就是 candidate_sort。是当前不依赖参数扫描即可
确定的最优组合，可直接拿去跑全量验证。

### fast — ⚠️ 已废弃
最早的省调用版（5 轮 + 只末轮复查），但缩放不限边、未限 3072。被 m3_fast 完全覆盖。
保留仅为历史可追溯，新实验勿用。

## 消融证据（结论来源）

- **candidate_sort=relevance** — 20 样本单变量消融里唯一稳定正收益：M3 +5/20、GPT +3/20，
  无副作用。所以它进了 quality_8round 和 m3_optimal。
- **context_mode=accumulate / accumulate_images** — 确认**负向**（M3、GPT 一致），
  所有配置都正确保持 `single`。原因：单步定位任务不受益跨轮记忆，累积会把早轮
  的试探性裁剪当成既定上下文反复确认、关掉纠偏，并让多轮候选坐标系交叉。
- **reasoning_first / candidate_dedup_iou / coords_crop_local** — 20 样本上无稳定收益，
  暂不开（各配置保持默认关闭）。
- 轮数（8 vs 5）、复查频率（每轮 vs 末轮）、缩放（preserve vs target_pixels）哪个更优
  尚无定论 —— 正在跑的参数扫描（`wf_param_sweep.js` + `aggregate_sweep.py`，base=quality_8round）
  在 26 样本 × M3 上回答这些。

## 消融/扫描专用配置（非正式策略，勿直接用于跑分）

- `ablation_off.yaml` / `ablation_on.yaml` — 20 样本消融的全关/全开对照组。
- `abl_reason / abl_sort / abl_dedup / abl_coords.yaml` — 四个单变量消融臂。
- `abl_accum_text / abl_accum_img.yaml` — 累积消融臂（已验证负向，留作负结果记录）。
- `sweep/` 子目录 — `make_sweep_configs.py` 从 quality_8round 派生的全参数单变量扫描 arm。
