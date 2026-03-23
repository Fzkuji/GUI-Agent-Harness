# GUIClaw 架构设计

> 最后更新：2026-03-24

## 总体架构

```
用户任务 → LLM 决策层 → GUIClaw Skill
                            ├── 检测层 (ui_detector.py)
                            │   ├── GPA-GUI-Detector (YOLO) — UI 组件检测
                            │   └── Apple Vision OCR — 文字识别
                            ├── 记忆层 (app_memory.py)
                            │   ├── 组件记忆 — 学过的组件模板匹配
                            │   ├── 状态识别 — Jaccard 匹配 defining_components
                            │   ├── 遗忘机制 — 连续 N 次未检测到自动删除
                            │   └── 状态合并 — Jaccard > 0.85 自动合并
                            ├── 导航层 (workflow)
                            │   ├── 状态转移图 — BFS 寻路
                            │   ├── 分层验证 — Level 0/1/2
                            │   └── 自动模式 / 探索模式
                            └── 执行层 (platform_input.py)
                                └── pynput — 鼠标/键盘操作
```

## 记忆系统

### 存储结构（拆分存储）

每个 app/site 目录下 4 个独立文件：

```
meta.json          — 元数据（detect_count, forget_threshold）
components.json    — 组件注册表 + 活跃度追踪
states.json        — 状态定义（由 defining_components 集合定义）
transitions.json   — 状态转移图（dict, key = from|action|to）
```

### 组件生命周期

```
新检测到 → learned_at, seen_count=1, consecutive_misses=0
再次检测到 → last_seen=now, seen_count++, consecutive_misses=0
未检测到 → consecutive_misses++
consecutive_misses >= threshold → 自动删除（组件 + 图片 + 状态引用 + 转移引用）
```

### 状态识别

状态由 **defining_components 集合** 定义，不是命名约定。

识别流程：
1. 检测到的组件中筛选 seen_count >= 2 的稳定组件 → stable_set
2. 与每个已知状态的 defining_components 计算 Jaccard 相似度
3. 最高 Jaccard > 0.7 → 匹配到已有状态
4. 所有 < 0.7 → 创建新状态（ID = s_ + 6位 hash）

### 状态合并

两个状态的 defining_components Jaccard > 0.85 → 自动合并：
- 保留 visit_count 更高的状态
- 合并 defining_components（取并集）
- 更新所有 transition 引用

## Workflow 系统

### 核心思路

**不判断"有没有变化"，只判断"有没有到达目标状态"。**

### 两种模式

**自动模式**（有已知路径）：
```
当前状态 s_a → find_path(s_a, target) → [(click:X, s_b), (click:Y, s_c)]
→ 每步点击后验证是否到达预期状态
→ 不需要 LLM 参与，纯组件匹配
```

**探索模式**（无路径）：
```
find_path 返回 None → LLM 看截图决策点什么
→ 每步记录 pending transition
→ 成功 → confirm_transitions → 下次有路径了
→ 失败 → discard_transitions → 不污染状态图
```

### 分层验证

每步点击后，用最低成本验证是否到达预期状态：

```
Level 0: quick_template_check（~0.3s, 0 token）
  → 只匹配目标状态的 defining_components 模板
  → matched_ratio > 0.7 → 确认到达
  
Level 1: detect_all + identify_current_state（~2s, 0 token）
  → 完整检测 + Jaccard 匹配
  → 匹配到预期状态 → 继续
  → 匹配到其他已知状态 → 重新寻路
  
Level 2: fallback LLM（~5s, 有 token 消耗）
  → 返回给 LLM："预期到达 s_b，实际在 s_unknown，怎么办？"
  → LLM 决策下一步
```

### workflow 存储

```json
// workflows.json
{
  "check_baggage_fee": {
    "target_state": "s_c8e5f3",
    "description": "Navigate to baggage fee calculator",
    "run_count": 3,
    "success_count": 2
  }
}
```

Workflow 是**目标状态 + BFS 寻路**，不是固定步骤序列。从不同起点出发会走不同路径。

## 检测层

### detect_all() 统一入口

```python
icons, texts, merged, w, h = detect_all(img_path)
```

- GPA-GUI-Detector（必须）— 检测 UI 组件 bounding box
- Apple Vision OCR（可选）— 识别文字 + 坐标
- 两者结果合并去重

### 三种视觉方法

| 方法 | 返回 | 用途 |
|------|------|------|
| OCR (detect_text) | 文字 + 坐标 ✅ | 定位文字元素 |
| GPA (detect_icons) | 组件 + 坐标 ✅ | 定位非文字 UI 元素 |
| image tool (LLM) | 语义理解 ⛔ 无坐标 | 理解页面含义 |

**规则：坐标只来自 OCR/GPA/模板匹配，永远不从 image tool 提取。**

## 执行层

### 安全协议

```
OBSERVE → ENSURE APP READY → ACT+SAVE → REPORT
```

每次点击必须：
1. 截图确认当前状态（OBSERVE）
2. 用检测结果定位目标（DETECT）
3. 通过 click_and_record / click_component 执行（不用 raw click_at）
4. 操作后截图验证结果（VERIFY）

### 输入方式

- 鼠标/键盘：pynput（platform_input.py）
- 中文输入：pbcopy + Cmd+V（不用 kb.type）
- 所有坐标：逻辑像素（Retina ÷2）
