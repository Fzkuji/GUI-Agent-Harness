# Claude Opus 4.7 — ScreenSpot Pro Full

运行目录: `runs/screenspot_pro/claude_opus47_full_screenspot_pro_20260603_1300/`
Provider: `claude-code` / Model: `claude-opus-4`
时间: 2026-06-03 13:00–22:36 HKT
状态: ⏹ 已停止（额度耗尽 → `finish_reason` UnboundLocalError → 1243/1581 标为 wrong_format）

## 最终结果

| 指标 | 数值 |
|------|------|
| 总样本 | 1581 |
| 有效结果 | 338 (21.4%) |
| 正确 | 267 |
| 错误 | 71 |
| Wrong Format (error) | 1243 (78.6%) |
| **有效准确率** | **78.99%** |

## 时间线

| 时间 | 事件 |
|------|------|
| 13:00 | 启动，4 shard 并行 |
| 13:00–14:12 | 正常运行，产出 338 个有效结果 |
| 14:12 | 额度耗尽，开始 `finish_reason` UnboundLocalError |
| 14:12–14:24 | 第一波 254 个 error |
| 14:24–21:46 | **7.4 小时静默**（进程卡死/暂停） |
| 21:46 | 恢复，retry 逻辑重新扫剩余样本 |
| 21:46–22:36 | 第二波 989 个 error |
| ~22:36 | 全部 1581 样本处理完毕，进程退出 |

## 按应用

| 应用 | C/W | Acc% | 样本 |
|------|-----|------|------|
| android_studio | 63/17 | 78.8% | 80 |
| blender | 41/10 | 80.4% | 51 |
| inventor | 53/12 | 81.5% | 65 |
| linux_common | 30/10 | 75.0% | 40 |
| autocad | 24/10 | 70.6% | 34 |
| illustrator | 5/0 | 100% | 5 |
| macos_common | 5/0 | 100% | 5 |
| origin | 0/4 | 0.0% | 4 |
| fruitloops | 1/2 | 33.3% | 3 |
| pycharm | 1/2 | 33.3% | 3 |
| matlab | 2/1 | 66.7% | 3 |
| premiere | 2/1 | 66.7% | 3 |
| vivado | 2/1 | 66.7% | 3 |
| vscode | 2/1 | 66.7% | 3 |
| davinci/excel/eviews/photoshop/powerpoint/quartus/solidworks/stata/unreal_engine/vmware/windows_common/word | 各 3/0 | 100% | 各 3 |

## 按分组

| 分组 | C/W | Acc% | 样本 |
|------|-----|------|------|
| Office | 9/0 | 100% | 9 |
| Creative | 58/13 | 81.7% | 71 |
| OS | 38/10 | 79.2% | 48 |
| Dev | 72/20 | 78.3% | 92 |
| CAD | 82/23 | 78.1% | 105 |
| Scientific | 8/5 | 61.5% | 13 |

## 按 UI 类型

| 类型 | C/W | Acc% | 样本 |
|------|-----|------|------|
| text | 188/32 | 85.5% | 220 |
| icon | 79/39 | 66.9% | 118 |

## 已知问题

- `openai_completions.py` 中 `finish_reason` 变量在 SSE stream 为空时未初始化 → UnboundLocalError
- 额度耗尽后 Max proxy 返回空响应 → 触发此 bug → 所有剩余样本标为 wrong_format
- 需要修复：在 for 循环前初始化 `finish_reason = None`

## 恢复方法

```bash
cd /Users/fzkuji/Documents/GUI\ Agent/GUI-Agent-Harness
# 先修 finish_reason bug，再重跑
bash runs/screenspot_pro/claude_opus47_full_screenspot_pro_20260603_1300/run.sh
```
