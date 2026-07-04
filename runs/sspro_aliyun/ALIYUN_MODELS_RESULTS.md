# 阿里云 Token Plan 视觉模型 × 本 harness(迭代缩放)× ScreenSpot-Pro

> 状态:**中途暂停(partial)**。qwen3.7-plus 跑到 504/1581 后按决定暂停,转入
> "先研究榜上 70% 模型测法、再拆错样优化流程"的阶段,故本文记录当前部分结果,
> 待流程优化后重跑全量再更新为最终版。

## 配置

- 管线:`benchmarks/screenspot_pro/configs/sspro_stack_zoom.yaml`(GPA-GUI-Detector YOLO
  + OCR 候选 → 迭代缩放裁剪精修 → commit gate)。三条线**同一套 harness**,唯一变量是底层视觉模型。
- 端点:阿里云 Token Plan OpenAI 兼容 `/chat/completions`,base64 data URL 传图。
- runner:`benchmarks/screenspot_pro/run_sspro_aliyun.py`,2 分片并行,skip-existing 续跑。
- 判分:预测点落在 GT bbox 内即 correct。

## 跨模型对比(同配置,ScreenSpot-Pro)

| 模型 | 类型 | 完成 | 正确率(含错) | 备注 |
|---|---|---|---|---|
| GPT-5.5 | 通用 | 1581 | **87.9%**(同配置)/ 88.7% | 参照上限 |
| **qwen3.7-plus** | 通用 | **504/1581(暂停)** | **62.9%**(317/504) | 剔除 22 条 error 后真实定位 **65.7%** |
| M3 | 通用 | 1581 | 47.4% | 参照下限 |

qwen3.7-plus 位置稳定落在 M3 与 GPT-5.5 之间。

## qwen3.7-plus 分组(仅已答样本,504 中 482 已答)

| 组 | 正确/总 | 正确率 |
|---|---|---|
| Scientific | 41/50 | 82.0% |
| Office | 49/64 | 76.6% |
| OS | 11/15 | 73.3% |
| CAD | 58/83 | 69.9% |
| Dev | 46/76 | 60.5% |
| Creative | 112/194 | 57.7% |

## 错样诊断(165 条已答错样)

| 类型 | 占比 | 含义 |
|---|---|---|
| 完全找错(>3×bbox对角) | 45% | 选错元素 / 密集工具栏语义消歧失败 |
| 邻近偏移(0.5–3×) | 28% | 点到相邻元素 |
| 小图标近失(<0.5×) | 26% | 区域对、目标仅 ~20px、落点差几十像素 |

GT 目标普遍是 4K 图里 `19×25`、`20×25` px 的工具栏小图标;错误高度集中在
Android Studio / CAD 这类近似图标密集界面。**主要瓶颈是"选错元素"(45%)而非纯精度。**

## 内容审查

- qwen3.7-plus:504 题中 **9 条** `data_inspection_failed`(平台内容审查拒答),如实计错、不重跑。
- **kimi-k2.7-code**:因平台审查对长提示大量拦截(`data_inspection_failed`),无法有效跑分,已放弃。
- **kimi-k2.6**:YOLO 每进程占资源,2 并行名额全给 qwen 提速,资源让位未跑全。

## 结论(阶段性)

同一套为 GPT-5.5 调优的迭代缩放 harness,换到 qwen3.7-plus 上得 62.9%(真实定位 65.7%),
明显低于 GPT-5.5 的 87.9%。榜上 Qwen3.5-27B / UI-Venus 等约 70%,提示当前流程对 qwen
存在优化空间——下一步先厘清那些模型的评测/方法差异,再针对"选错元素为主"的错样改流程,
而非继续盲跑。
