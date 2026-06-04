# Benchmarks Overview — GUI Agent Harness

| Benchmark | Status | Best Model | Best Acc | Samples |
|-----------|--------|------------|----------|---------|
| [ScreenSpot Pro](screenspot_pro/) | Partial | Claude 4.7 | 79.5% | 78/1581 (stratified) / 488/1581 (full stopped) |
| [ScreenSpot v2](screenspot_v2/) | ✅ Done | GPT-5.5 | 95.83% | 1272/1272 |
| [ScreenSpot v1](screenspot_v1/) | ❌ Not run | — | — | 0/~1272 |
| [MMBench-GUI-L2](mmbench_gui_l2/) | ⏹ Stopped | GPT-5.5 | 92.60% | 2109/3594 |
| [OSWorld](osworld/) | Partial | Claude 4.6 | 93.5% (Chrome) | 172+/369 |

## 运行目录结构
```
benchmarks/
  screenspot_pro/     # 主项目
    claude_opus_4_7/  # 模型结果
      results/
        stratified78_report.md
        full_report.md
    claude_opus_4_8/
      results/
        stratified78_report.md
    README.md
  screenspot_v2/
    gpt_5_5/
      results/
        full_report.md
    README.md
  screenspot_v1/
    README.md
  mmbench_gui_l2/
    gpt_5_5/
      results/
        full_report.md
    README.md
  osworld/
    claude_opus_4_6/results/
    gpt_5_5/results/
    not_tested/
    README.md
  README.md (this file)
```

## 原始数据
所有原始 JSONL 结果、错误日志和运行脚本保存在 `runs/` 目录下：
- `runs/screenspot_pro/` — ScreenSpot 系列所有运行
- `runs/gui_grounding/` — MMBench-GUI-L2 等 grounding 基准运行
- `benchmarks/osworld/` — OSWorld 各 domain 结果（早期 Claude Code CLI + GPT-5.5 测试）
