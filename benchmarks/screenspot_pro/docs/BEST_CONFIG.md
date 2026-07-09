# ScreenSpot-Pro 当前最优解（基于已知全部实验）

更新时间：2026-06-06。证据来源：20 样本单变量消融（GPT-5.5 + M3，唯一干净的同批
多臂对照）、累积消融、全量 1581（legacy_baseline，GPT-5.5 87.9%）。参数扫描尚未出
可用结论（多数 arm 还没数据），故本文不依赖它。

## 一句话结论

**最优开关组合 = 只开 `candidate_sort=relevance`，其余优化开关（reasoning_first /
candidate_dedup / coords_crop_local / 累积）全部关闭。** 对应配置：`m3_optimal`
（省调用骨架）或 `quality_8round`（精度骨架）——两者开关组合相同，只差迭代骨架。

## 为什么是"只开 sort"——证据

20 样本消融，off=全关基线，每个 arm 单开一个开关：

| arm | GPT Δ | GPT 救回/掉点 | M3 Δ | M3 救回/掉点 | 结论 |
|---|---|---|---|---|---|
| **abl_sort** | **+3** | **3/0** | **+5** | **7/2** | 两模型最强，GPT 零掉点 ★ |
| abl_coords | +2 | 3/1 | +4 | 5/1 | 次强，但有掉点 |
| abl_dedup | +1 | 2/1 | +4 | 6/2 | 弱，有掉点 |
| abl_reason | +0 | 1/1 | +3 | 5/2 | GPT 无用、有掉点 |
| **on（全开）** | **+1** | 2/1 | **+4** | 5/1 | **比单开 sort 差** |
| abl_accum_text | vs sort −2 | 0/2 | vs sort −5 | 2/7 | 累积负向 |
| abl_accum_img | vs sort −3 | 1/4 | vs sort −4 | 0/4 | 累积更负 |

两个关键事实：

1. **sort 是唯一两模型都强、且 GPT 零掉点的开关。** 最稳的正收益，无争议。
2. **全开 < 只开 sort**（GPT on=+1<sort=+3；M3 on=+4<sort=+5）。reason/dedup/coords
   单看都有正 Δ 但都伴随掉点，叠加后掉点累积抵消救回，反而拖累。所以**不该全开，
   只开 sort 最优**。
3. 累积（context_mode/accumulate_images）确认负向，排除。

因此最优开关 = `candidate_sort=relevance` + 其余优化项全关。这正是 m3_optimal /
quality_8round 当前的设置。

## 推荐配置

| 模型 / 场景 | 用哪个 | 迭代骨架 | 开关 |
|---|---|---|---|
| M3 等单次慢、要省调用 | **`m3_optimal`** | 5 轮 + 只末轮复查（~6 次调用/样本） | 只开 sort |
| GPT/Claude，精度优先、不在乎调用 | **`quality_8round`** | 8 轮 + 每轮复查（~16 次调用/样本） | 只开 sort |

两者开关组合完全相同（只开 sort、不累积、不开 reason/dedup/coords），**唯一区别是
迭代骨架**。

## 必须诚实标出的——尚未验证的部分

下面这些进了"最优解"，但**没有数据支撑，是工程假设**，别当成已证明：

1. **5 轮 vs 8 轮、每轮复查 vs 只末轮复查**——从没在同批对照里比过精度。
   m3_optimal 选 5 轮/末轮纯粹是"M3 单次慢、省调用"的工程取舍。**现有证据无法
   断定 m3_optimal 和 quality_8round 谁精度更高**，只能说 m3_optimal 调用少 ⅔。
2. **缩放 preserve vs target_pixels**——无直接对比（m3_optimal 用 preserve，
   m3_fast_adaptive 用 target_pixels）。
3. **sort 的 +3/+5 增量能否在全量 1581 上保持**——20 样本的结论没在全量验证过。
   仓库现有全量结果（87.9%）跑的是 legacy_baseline（连 sort 都没开），不可比。

上述 1、2 正是参数扫描（`wf_param_sweep.js`，base=quality_8round，26 样本×M3）要
回答的；扫描出结果后本文需更新。

## 下一步验证（让"最优解"从工程假设升级为证据）

1. 等参数扫描跑完 → 确认 5轮/末轮/缩放 这几项相对 quality_8round 是否掉精度。
2. 用 m3_optimal 跑一次全量 1581（M3）→ 确认 sort 的增量在全量成立，并得到
   M3 的全量基准（目前 M3 没有全量数。）
3. 若要 GPT 全量最优，用 quality_8round 跑全量 → 和 legacy_baseline 的 87.9% 直接对比，
   量化"preserve+cache+sort"三项改进在全量上值多少。
