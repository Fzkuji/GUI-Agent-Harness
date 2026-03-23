# gui-memory 设计文档

> 最后更新：2026-03-24
> 修改此模块前请先读完本文档

## 设计背景

### 为什么从 profile.json 拆分为 4 文件

最初所有数据（components, states, transitions）存在单个 `profile.json` 里。问题：
- 遗忘机制需要频繁更新 components 的活跃度字段，每次都要读写整个 profile
- 组件数量多的 profile（如 united_com 96 个组件）JSON 文件 50KB+
- 状态合并只改 states 和 transitions，不需要重写 components

拆分后每个文件独立读写，只更新变化的部分。

### 为什么用 JSON 而不是 SQLite

- JSON 是 memory/ 目录下的 gitignored 文件，每台机器自己生成
- 组件数量通常 < 200，读写性能不是瓶颈
- JSON 可直接人工检查和调试
- 不引入额外依赖

## 组件遗忘机制

### 核心问题

组件只增不减导致：
- profile 越来越大
- 模板匹配越来越慢（每次检测要和所有已存组件比较）
- 过时组件（网站改版后消失的按钮）永远占着 memory

### 设计决策

**遗忘基于检测频率，不是时间**：
- 用 `consecutive_misses` 而不是 `days_since_last_seen`
- 原因：用户可能几周不操作某个 app，但组件并没有过时。只有在**实际检测了该 app 但找不到组件**的情况下才应该遗忘
- 每次对该 app/site 调用 `learn_from_screenshot()` 时，detect_all 的结果自动更新所有组件的活跃度

**threshold 默认 15**：
- 太低（5）→ 组件位置微调就被误删
- 太高（50）→ 过时组件保留太久
- 15 次检测约等于操作该 app 15 次以上都没看到这个组件

**早期保护**：
- `detect_count <= forget_threshold` 时不触发遗忘
- 避免刚学了一个 app，第二次检测就把第一页的组件删了（因为第二次在另一个页面）

### 活跃度字段

```json
{
  "last_seen": "2026-03-23 15:30:00",   // 最后检测到的时间
  "seen_count": 12,                       // 累计检测到次数
  "consecutive_misses": 0                 // 连续未检测到次数
}
```

**匹配判断**：当前检测到的组件名集合 `detected_names` 里有该组件名 → 匹配。位置偏移不影响（位置去重在 learn_from_screenshot 里处理，不在活跃度更新里）。

### 级联删除

删除一个组件时：
1. 删组件图片文件
2. 从 states 的 `defining_components` 中移除
3. `defining_components` 被清空的 state → 删除该 state
4. 引用被删 state 的 transition → 删除该 transition

## 状态系统

### 核心问题

旧系统用 `before_X` / `after_X` 命名状态，导致：
- 同一个页面多次操作产生多个名字不同但实际相同的状态
- BFS 寻路找不到路径（因为状态名不匹配）

### 设计决策

**状态由组件集合定义**：
- 两个状态是否相同取决于它们包含的组件集合是否相似
- 用 Jaccard 相似度量化

**只用稳定组件**：
- 筛选 `seen_count >= 2` 的组件作为 stable_set
- 第一次检测到的新组件不参与状态识别（可能是误检或临时组件）

**Jaccard 阈值**：
- `> 0.7` → 认为是同一状态（匹配）
- `> 0.85` → 两个已有状态自动合并
- 为什么不用更高的阈值：网页上的广告、推荐内容会导致同一页面的组件集合有 10-20% 差异

**状态 ID 格式**：
- `s_` + 组件集合的 MD5 前 6 位
- 确定性：相同组件集合始终生成相同 ID
- 冲突处理：追加 hash 直到唯一

### 状态合并

遍历所有状态对，Jaccard > 0.85 → 合并：
- 保留 visit_count 更高的
- defining_components 取并集
- 更新 transitions 引用
- 循环直到没有可合并的对

## Transitions

### 核心问题

旧系统用 list 追加 transitions，相同操作重复记录导致列表无限增长。

### 设计决策

**Dict 结构**：
- key = `from_state|action|to_state`
- 天然去重，相同操作只更新 count 和 last_used
- BFS 遍历 `transitions.values()` 而不是 list

**pending 机制**：
- 探索时的 transition 先存入内存中的 `_pending_transitions`
- 成功后 `confirm_transitions()` 写入文件
- 失败后 `discard_transitions()` 丢弃
- 避免试错产生的无效路径污染状态图

## 浏览器 sites/ 结构

每个网站是独立的 app，拥有完整的 4 文件 + components/ + pages/ 结构。

域名作为目录名（`united_com` 而不是 `www.united.com/en/us`）。

浏览器本身（chromium）也有自己的 memory，用于 toolbar、settings 等浏览器级 UI。

## 迁移

`migrate_profile_if_needed()` 自动将旧 `profile.json` 拆分为新格式：
- 在 `load_profile()` 时自动调用
- 旧文件重命名为 `.bak` 而不是删除
- 已迁移的目录（meta.json 存在）跳过
