# MMBench-GUI-L2 — GUI 元素定位 (多平台)

MMBench-GUI-L2 是 MMBench 系列的 GUI 元素定位基准测试，覆盖手机/桌面多平台应用。

- 模型: **GPT-5.5** (openai-codex)
- 总样本数: **2109 / 3594** (58.7% 完成)
- 方法: iterative_zoom (8 rounds)
- 已完成部分准确率: **92.60%** (1953 correct / 156 wrong / 0 WF)
- 状态: ⏹ **已停止** (额度原因)

---

## 运行结果

| 模型 | 进度 | 正确 | 错误 | 准确率 | 状态 |
|------|------|------|------|--------|------|
| **GPT-5.5** | 2109/3594 | 1953 | 156 | **92.60%** | ⏹ 已停止 |

## 每应用准确率 (已完成部分)

| 应用 | 平台 | C/W | Acc% |
|------|------|-----|------|
| Android Studio | desktop | 4/0 | 100% |
| Amazon | web | 4/0 | 100% |
| AppStore | mobile | 23/0 | 100% |
| App_Market | mobile | 32/0 | 100% |
| Apple_Music | mobile | 22/4 | 84.6% |
| Bilibili | web | 60/5 | 92.3% |
| Calendar | mobile | 62/4 | 93.9% |
| Camera | mobile | 28/3 | 90.3% |
| Chrome | desktop | 21/3 | 87.5% |
| Clock | mobile | 35/3 | 92.1% |
| Disk_Utility | desktop | 7/1 | 87.5% |
| Douban | web | 19/0+17/0 | 100% |
| Douyin | mobile | 36/1 | 97.3% |
| Firefox | desktop | 41/7 | 85.4% |
| Fitness | mobile | 25/1 | 96.2% |
| Gimp | desktop | 17/9 | 65.4% |
| Github | web | 51/3 | 94.4% |
| Health | mobile | 65/3 | 95.6% |
| Home | mobile | 18/0 | 100% |
| Hupu | web | 46/4 | 92.0% |
| Kugou | mobile | 36/0 | 100% |
| LibreOffice_Calc | desktop | 17/8 | 68.0% |
| LibreOffice_Impress | desktop | 28/3+1/1 | 87.9% |
| LibreOffice_Writer | desktop | 11/7 | 61.1% |
| OneNote | desktop | 38/4 | 90.5% |
| Outlook | desktop | 46/5 | 90.2% |
| Podcasts | mobile | 51/3 | 94.4% |
| QQ_Music | mobile | 35/1 | 97.2% |
| Qidian | web | 32/0 | 100% |
| Reddit | web | 31/3 | 91.2% |
| Safari | mobile | 28/3 | 90.3% |
| Setting | mobile | 25/1 | 96.2% |
| Settings | mobile | 55/8 | 87.3% |
| Shortcut | mobile | 23/2 | 92.0% |
| Slack | desktop | 45/5 | 90.0% |
| Spotify | desktop | 37/2 | 94.9% |
| Tencent_Map | mobile | 33/3 | 91.7% |
| Tencent_Video | mobile | 50/2 | 96.2% |
| Thunderbird | desktop | 21/6 | 77.8% |
| Trip | web | 32/2 | 94.1% |
| Tripsy | mobile | 21/1 | 95.5% |
| Twitter | mobile | 129/7 | 94.9% |
| VScode | desktop | 29/7 | 80.6% |
| Weather | mobile | 10/2 | 83.3% |
| Weibo | web | 32/0 | 100% |
| XMind | desktop | 74/5 | 93.7% |
| Ximalaya | mobile | 35/1 | 97.2% |
| YouTube | mobile | 35/1+55/3 | 95.7% |
| Zhihu | web | 32/1 | 97.0% |
| Zotero | desktop | 20/4+55/3 | 91.5% |
| common | multi | 26/0 | 100% |
| screenspot_v2_ios | mobile | 91/1 | 98.9% |

## 运行信息
- 运行目录: `runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040/`
- 断点记录: `runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040/STOPPED_20260603_1256.md`
- 原始 shard: `runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040/mmbench_gui_l2/shards/shard_*.jsonl`

## 恢复方法
```bash
cd /Users/fzkuji/Documents/GUI\ Agent/GUI-Agent-Harness
bash runs/gui_grounding/gui_grounding_mmbench_gui_l2_full_20260602_2040/run.sh
```
