# gui-workflow 设计文档

> 最后更新：2026-03-24
> 修改此模块前请先读完本文档

## 设计背景

### 核心洞察

**不需要判断"页面有没有变化"，只需要判断"有没有到达目标状态"。**

早期设计尝试用像素对比（cv2.absdiff）判断点击后页面是否变化。测试发现：
- 鼠标移动、光标闪烁、时钟更新 → 像素必然有差异，但页面状态没变
- Toggle/checkbox 状态变化 → 像素差异极小（< 0.001），检测不到
- 页面微滚动 → 几乎所有像素偏移，误判为大变化

最终结论：**变化检测是错误的抽象。正确的抽象是目标验证。**

### 为什么 workflow 不是"录制宏"

录制宏：记录固定的坐标序列 [(661, 188), (650, 250), ...]
- 分辨率变了 → 失效
- 页面布局变了 → 失效
- 从不同起始状态 → 无法执行

Workflow 是导航图：记录状态转移关系 {s_a --click:X--> s_b}
- 分辨率变了 → 模板匹配找到新坐标，照样走
- 布局变了但组件在 → 模板匹配找到新位置
- 不同起点 → BFS 找不同路径到达同一目标

## 分层验证策略

### 为什么要分层

每次点击后都跑完整的 detect_all 太浪费：
- GPA-GUI-Detector: ~0.3s
- OCR: ~1.6s
- 总计 ~2s/步

如果一个 workflow 有 5 步，全量检测需要 10 秒。但如果已知目标状态的组件，快速模板匹配只需要 ~0.3s/步，5 步只要 1.5 秒。

### 三个层级

**Level 0: quick_template_check（~0.3s, 0 token）**
- 只匹配目标状态的 defining_components 模板
- 比如目标状态有 8 个组件，只做 8 次模板匹配
- matched_ratio > 0.7 → 确认到达
- 失败原因：组件外观变了（网站更新）、不在目标页面

**Level 1: detect_all + identify_current_state（~2s, 0 token）**
- 完整检测当前页面的所有组件
- 用 Jaccard 匹配已知状态
- 匹配到预期状态 → 继续（Level 0 模板过时了，下次会重新学习）
- 匹配到其他已知状态 → 可能走错了，重新 find_path
- 匹配不到任何已知状态 → 升级 Level 2

**Level 2: fallback LLM（~5s+, 有 token 消耗）**
- 返回 ("fallback", current_state, step_index, reason)
- LLM 看截图判断怎么回事，接管后续操作
- LLM 的操作记录为新的 pending transitions

### 为什么 Level 0 阈值是 0.7

目标状态有 10 个 defining_components：
- 全匹配 → 1.0（完美到达）
- 7/10 匹配 → 0.7（可能有 3 个组件位置微调或被遮挡，但大概率在对的页面）
- 5/10 匹配 → 0.5（不太确定，需要完整检测确认）
- 3/10 匹配 → 0.3（大概率不在目标页面）

0.7 是在"误报"和"漏报"之间的平衡点。

## 两种模式

### 自动模式

前提：transitions.json 里有从当前状态到目标状态的路径。

```
identify_current_state → s_a
find_path(s_a, target) → [(click:X, s_b), (click:Y, target)]
→ 执行 click:X → Level 0 验证 s_b → 执行 click:Y → Level 0 验证 target
→ 成功
```

特征：不需要 LLM 参与，纯组件匹配 + 模板执行。快速、确定性、零 token。

### 探索模式

前提：没有到目标的已知路径。

```
find_path → None
→ LLM 看截图，决定点什么
→ 每步：click → detect_all → identify_or_create_state → pending transition
→ 成功 → confirm_transitions → 路径保存，下次自动执行
→ 失败 → discard_transitions → 不保存错误路径
```

特征：LLM 主导决策，每步截图+检测+推理。慢但能处理未知场景。

### 渐进式学习

第一次 → 探索模式（慢，有 token 消耗）
↓ 成功后 transitions 保存
第二次 → 自动模式（快，零 token）

这就是 workflow 的价值：**把 LLM 的一次性决策转化为可复用的导航知识。**

## workflows.json

```json
{
  "check_baggage_fee": {
    "target_state": "s_c8e5f3",
    "description": "Navigate to baggage fee calculator",
    "created_at": "2026-03-23 15:30:00",
    "last_run": "2026-03-23 16:00:00",
    "run_count": 3,
    "success_count": 2
  }
}
```

Workflow 只记录目标状态，不记录固定路径。路径在运行时由 find_path BFS 计算。

`run_count` / `success_count` 用于追踪可靠性。

## execute_workflow 返回值

```python
("success", state_id)                        # 到达目标
("fallback", current_state, step_idx, reason) # 需要 LLM 接管
("error", message)                            # 无法执行（无路径等）
```

调用方（gui-act）根据返回值决定：
- success → 继续任务
- fallback → LLM 看截图接管
- error → 报告给用户

## 被废弃的设计

### 像素对比变化检测（assess_change）

实现过，后来删了。原因：
- 全图像素对比受鼠标、光标、时钟、动画干扰
- 无法检测 toggle/checkbox 这种有意义的微小变化
- 分块对比、排除动态区域等改进增加复杂度但不能根本解决问题
- 最终发现"变化检测"是错误的抽象

### meta_workflow（跨 app workflow）

设计了跨 app 的元 workflow，支持变量替换和嵌套。从未使用过，删了。
原因：过度设计，实际场景中 LLM 可以直接编排跨 app 操作。

### detect_workflow_conflict / plan_workflow

空实现的 TODO 函数，删了。
