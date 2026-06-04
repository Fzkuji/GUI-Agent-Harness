# ScreenSpot v2 — GUI 元素定位

ScreenSpot v2 是 ScreenSpot 系列的多平台 GUI 元素定位基准测试。

- 模型: **GPT-5.5** (openai-codex)
- 总样本数: **1272 / 1272** ✅ 完成
- 方法: iterative_zoom (8 rounds)
- 总准确率: **95.83%** (1219 correct / 39 wrong / 14 WF)

---

## 运行结果

| 模型 | 结果 | 准确率 | 状态 |
|------|------|--------|------|
| **GPT-5.5** | 1272/1272 | **95.83%** | ✅ 完成 |

## 平台分布 (GPT-5.5)

| 平台 | 结果 | C/W/WF | 准确率 |
|------|------|--------|--------|
| **Android** | 211 | 206/5/0 | **97.6%** |
| **iOS** | 238 | 231/6/1 | **97.5%** |
| **macOS** | 147 | 139/2/6 | **98.6%** |
| **Windows** | 159 | 147/5/7 | **96.7%** |
| **Web (forum)** | 79 | 75/4/0 | **94.9%** |
| **Web (gitlab)** | 73 | 72/1/0 | **98.6%** |
| **Web (shop)** | 245 | 235/10/0 | **95.9%** |
| **Web (tool)** | 120 | 114/6/0 | **95.0%** |
| **合计** | **1272** | **1219/39/14** | **95.83%** |

## 运行信息
- 运行目录: `runs/screenspot_pro/screenspot_v2_full_20260602_1157/`
- 脚本: `run.sh`
- 原始 shard: `runs/screenspot_pro/screenspot_v2_full_20260602_1157/v2/shards/shard_*.jsonl`
- 错误: 59 个 (provider_transport=13, no_verified_target=1, 其余 runtime)
