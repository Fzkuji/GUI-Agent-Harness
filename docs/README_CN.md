<div align="center">
  <img src="../assets/banner.png" alt="GUI Agent Skills" width="100%" />

  <br />

  <p>
    <strong>你的 AI 终于能看见屏幕了——而且像人一样使用它。</strong>
    <br />
    <sub>视觉记忆 • 一次学习即复用 • 零硬编码选择器</sub>
  </p>

  <p>
    <a href="#-快速开始"><img src="https://img.shields.io/badge/快速开始-blue?style=for-the-badge" /></a>
    <a href="https://github.com/openclaw/openclaw"><img src="https://img.shields.io/badge/OpenClaw-必需-red?style=for-the-badge" /></a>
    <a href="https://discord.gg/vfyqn5jWQy"><img src="https://img.shields.io/badge/Discord-7289da?style=for-the-badge&logo=discord&logoColor=white" /></a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/平台-macOS_%7C_Linux-black?logo=apple" />
    <img src="https://img.shields.io/badge/运行时-OpenClaw-orange" />
    <img src="https://img.shields.io/badge/检测-GPA--GUI--Detector-green" />
    <img src="https://img.shields.io/badge/OCR-Apple_Vision_%7C_EasyOCR-blue" />
    <img src="https://img.shields.io/badge/License-MIT-yellow" />
    <img src="https://img.shields.io/badge/OSWorld_Chrome-93.5%25-brightgreen" />
    <img src="https://img.shields.io/badge/OSWorld_Multi--Apps-54.3%25-green" />
  </p>
</div>

---

<p align="center">
  <a href="../README.md">🇺🇸 English</a> ·
  <b>🇨🇳 中文</b>
</p>

---

## 🔥 更新日志

- **[2026-03-30]** 📐 **ImageContext 坐标系统** — 用 `ImageContext` 类替代双空间模型。`detect_all()` 返回图片像素坐标（不做转换），裁剪与 scale 无关。`pixel_scale` 从 `backingScaleFactor` 获取（不再用 `图片尺寸/屏幕尺寸`）。修复非全屏截图的组件裁剪偏移 bug。[测试 →](../tests/test_image_context.py)
- **[2026-03-29]** 🎬 **v0.3 — 统一操作接口 & 跨平台 GUI** — `gui_action.py` 作为所有 GUI 操作的统一入口。平台后端（`mac_local.py`、`http_remote.py`）通过 `--remote` 自动切换。`activate.py` 负责平台检测。OSWorld Multi-Apps：**54.3%**（44/81）。[查看结果 →](../benchmarks/osworld/multi_apps.md)
- **[2026-03-24]** 🧠 **智能工作流导航** — 目标状态分层验证（模板匹配 → 全量检测 → LLM 回退）。通过 `detect_all` 自动跟踪性能。
- **[2026-03-23]** 🏆 **OSWorld 基准测试（Chrome）** — **单轮尝试：93.5%**（43/46），**最多两轮尝试：97.8%**（45/46）。[查看结果 →](../benchmarks/osworld/)
- **[2026-03-23]** 🔄 **记忆系统重构** — 拆分存储、组件自动遗忘（连续 15 次未命中 → 删除）、基于 Jaccard 相似度的状态合并。
- **[2026-03-22]** 🔍 **统一检测管线** — `detect_all()` 作为单一入口；原子化的 检测 → 匹配 → 执行 → 验证 循环。
- **[2026-03-21]** 🌐 **跨平台支持** — GPA-GUI-Detector 可处理任意 OS 截图（Linux VM、远程服务器等）。
- **[2026-03-10]** 🚀 **初始发布** — GPA-GUI-Detector + Apple Vision OCR + 模板匹配 + 应用视觉记忆。

## 📖 技能总览

GUI Agent Skills 由一个**主技能**（`SKILL.md`）编排 **7 个专用子技能**，各自负责 GUI 自动化的不同方面：

<div align="center">

### **驱动视觉 GUI 自动化的 7 个技能**

| 技能 | 说明 |
|:---|:---|
| 👁️&nbsp;**[gui‑observe](../skills/gui-observe/)** | 截屏捕获、OCR 文字提取、当前状态识别。Agent 的眼睛——每次操作前必先执行。 |
| 🎓&nbsp;**[gui‑learn](../skills/gui-learn/)** | 首次接触应用的学习——通过 GPA-GUI-Detector 检测所有 UI 组件，让 VLM 逐一标注，过滤重复，存入视觉记忆。 |
| 🖱️&nbsp;**[gui‑act](../skills/gui-act/)** | 统一操作执行——检测 → 匹配 → 执行 → 差异对比 → 保存，一个原子化流程。处理点击、输入等所有 UI 交互。 |
| 💾&nbsp;**[gui‑memory](../skills/gui-memory/)** | 视觉记忆管理——拆分存储（components/states/transitions）、浏览器站点隔离、活跃度遗忘、状态合并。 |
| 🔄&nbsp;**[gui‑workflow](../skills/gui-workflow/)** | 状态图导航与工作流自动化——记录成功的任务序列，分层验证回放，BFS 路径规划。 |
| 📊&nbsp;**[gui‑report](../skills/gui-report/)** | 任务性能追踪——自动记录耗时、token 用量、成功/失败日志。 |
| ⚙️&nbsp;**[gui‑setup](../skills/gui-setup/)** | 新机器首次设置——安装依赖、下载模型、配置辅助功能权限。 |

</div>

主 `SKILL.md` 作为编排层：定义安全协议（INTENT → OBSERVE → VERIFY → ACT → CONFIRM → REPORT）、视觉与命令的边界，并按需路由到子技能。Agent 首先读取 `SKILL.md`，然后按需加载子技能。

## 🔄 工作方式

> **你**："用微信给小明发消息说明天见"

```
OBSERVE  → 截屏，识别当前状态
           ├── 当前应用：访达（不是微信）
           └── 需要切换到微信

STATE    → 检查微信记忆
           ├── 之前学过？是（24 个组件）
           ├── OCR 可见文字：["聊天", "通讯录", "收藏", "搜索", ...]
           ├── 状态识别："initial"（89% 匹配）
           └── 当前状态可用组件：18 个 → 用这些做匹配

NAVIGATE → 查找联系人"小明"
           ├── 模板匹配 search_bar → 找到（conf=0.96）→ 点击
           ├── 粘贴"小明"（剪贴板 → Cmd+V）
           ├── OCR 搜索结果 → 找到 → 点击
           └── 新状态："click:小明"（聊天窗口打开）

VERIFY   → 确认打开了正确的聊天
           ├── OCR 聊天标题 → "小明" ✅
           └── 不对？→ 中止

ACT      → 发送消息
           ├── 点击输入框（模板匹配）
           ├── 粘贴"明天见"（剪贴板 → Cmd+V）
           └── 按回车

CONFIRM  → 验证消息已发送
           ├── OCR 聊天区域 → "明天见" 可见 ✅
           └── 完成
```

<details>
<summary>📖 更多示例</summary>

### "帮我扫描一下电脑有没有恶意软件"

```
OBSERVE  → 截屏 → CleanMyMac X 不在前台 → 激活
           ├── 获取主窗口边界（选最大窗口，跳过状态栏面板）
           └── OCR 识别当前状态

STATE    → 检查 CleanMyMac X 记忆
           ├── OCR 可见文字：["Smart Scan", "Malware Removal", "Privacy", ...]
           ├── 状态识别："initial"（92% 匹配）
           └── 可匹配组件：21 个

NAVIGATE → 点击侧边栏 "Malware Removal"
           ├── 在窗口内查找元素（精确匹配，窗口边界过滤）
           ├── 点击 → 新状态："click:Malware_Removal"
           └── OCR 确认新状态（87% 匹配）

ACT      → 点击 "Scan" 按钮
           ├── 查找 "Scan"（精确匹配，选底部位置 — 避免匹配到 "Deep Scan"）
           └── 点击 → 扫描开始

POLL     → 等待完成（事件驱动，无固定休眠）
           ├── 每 2 秒：截屏 → OCR 检查 "No threats"
           └── 找到目标 → 立即继续

CONFIRM  → "No threats found" ✅
```

### "看看我的 GPU 训练还在跑吗"

```
OBSERVE  → 截屏 → Chrome 已打开
           └── 识别目标：JupyterLab 标签页

NAVIGATE → 找到 JupyterLab 标签
           ├── OCR 标签栏或使用书签
           └── 点击切换

EXPLORE  → 多个终端标签可见
           ├── 截屏终端区域
           ├── LLM 视觉分析 → 识别 nvitop 所在标签
           └── 点击正确的标签

READ     → 截屏终端内容
           ├── LLM 读取 GPU 使用率表格
           └── 报告："8 块 GPU，7 块 100% — 实验正在运行" ✅
```

### "用活动监视器杀掉 GlobalProtect"

```
OBSERVE  → 截屏当前状态
           └── GlobalProtect 和活动监视器都不在前台

ACT      → 启动两个应用
           ├── open -a "GlobalProtect"
           └── open -a "Activity Monitor"

EXPLORE  → 截屏活动监视器窗口
           ├── LLM 视觉 → "网络标签页活跃，右上角搜索框为空"
           └── 决定：先点击搜索框

ACT      → 搜索进程
           ├── 点击搜索框（根据探索结果定位）
           ├── 粘贴 "GlobalProtect"（剪贴板 → Cmd+V，绝不用 cliclick 输入）
           └── 等待过滤结果

VERIFY   → 进程列表中找到目标 → 选中

ACT      → 结束进程
           ├── 点击工具栏的停止按钮 (X)
           └── 确认对话框弹出

VERIFY   → 点击 "Force Quit"

CONFIRM  → 截屏 → 进程列表为空 → 已终止 ✅
```

</details>

## 📋 前置要求

GUI Agent Skills 是一个 **OpenClaw 技能** — 它运行在 [OpenClaw](https://github.com/openclaw/openclaw) 内部，利用 OpenClaw 的 LLM 编排来推理 UI 操作。它**不是**独立的 API、命令行工具或 Python 库。你需要：

1. **[OpenClaw](https://github.com/openclaw/openclaw)** 已安装并运行
2. **macOS + Apple Silicon**（*推荐*）— 启用 Apple Vision OCR 以获得高精度文字检测。同时支持 **Linux**（本地或通过 HTTP API 远程控制 VM，如 OSWorld）。
3. **辅助功能权限** 已授予 OpenClaw / Terminal（仅 macOS）

LLM（Claude、GPT 等）由 OpenClaw 配置提供 — GUI Agent Skills 本身不直接调用任何外部 API。

## 🚀 快速开始

**1. 克隆并安装**
```bash
git clone https://github.com/Fzkuji/GUI-Agent-Skills.git
cd GUI-Agent-Skills
bash scripts/setup.sh
```

**2. 授予辅助功能权限**

系统设置 → 隐私与安全性 → 辅助功能 → 添加 Terminal / OpenClaw

**3. 配置 OpenClaw**

在 `~/.openclaw/openclaw.json` 中添加：
```json
{
  "skills": { "entries": { "gui-agent": { "enabled": true } } },
  "tools": { "exec": { "timeoutSec": 300 } }
}
```

> ⚠️ **`timeoutSec: 300`** 很重要 — GUI Agent Skills 的操作链（截屏 → 检测 → 点击 → 等待 → 验证）可能较长，推荐 5 分钟超时。默认超时太短会中途终止命令。

然后直接和你的 OpenClaw 智能体对话 — 它会自动读取 `SKILL.md` 并处理一切。

## 🏗️ 架构

<p align="center">
  <img src="../assets/architecture.png" alt="GUI Agent Skills 架构图" width="700" />
</p>

GUI Agent Skills 将 GUI 智能体从**无状态**（每步重新感知所有内容）转变为**有状态**（学习、记忆、复用），通过三个核心机制实现：

### 1. 统一组件记忆（Unified Component Memory）

> **问题**：现有 GUI 智能体将每次截屏当作全新的感知任务——即便面对已经见过上百次的界面。

当 UI 元素首次被检测到时，GUI Agent Skills 创建一个**双重表征**：裁切的视觉模板（用于快速匹配）和 VLM 赋予的语义标签（用于推理）。这对组合存储在每个应用的记忆中，跨所有后续交互复用。

**检测与标注：**
- [GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)（YOLO 架构）检测 UI 组件 → 返回带坐标的边界框，但*不提供语义标签*
- Apple Vision OCR 提取可见文字及精确边界框
- VLM（Claude、GPT 等）为每个检测到的元素赋予语义标签（"搜索按钮"、"设置图标"）
- 结果：每个组件同时携带**视觉模板**和**语义标签**

**模板匹配与复用：**
- 后续截屏中，已存储的模板通过归一化互相关进行匹配
- 匹配结果通过目标应用的窗口边界验证（防止被重叠应用产生的误匹配）
- 匹配到的组件携带之前赋予的标签——无需再调用 VLM

**基于活跃度的遗忘：**
- 每个组件追踪 `consecutive_misses`——每当完整检测周期未能重新检测到该组件时递增
- 连续 **15 次**未命中后，组件自动删除（级联删除相关状态和转移）
- 随着应用 UI 更新，记忆自动保持同步

```
memory/apps/
├── wechat/
│   ├── meta.json              # 元数据（detect_count, forget_threshold）
│   ├── components.json        # 组件注册表 + 活跃度追踪
│   ├── states.json            # 状态（由组件集合定义）
│   ├── transitions.json       # 状态转移（字典结构，去重）
│   ├── components/            # 裁切的 UI 元素图片
│   │   ├── search_bar.png
│   │   └── emoji_button.png
│   └── workflows/             # 保存的任务序列
├── chromium/
│   ├── components.json        # 浏览器 UI 组件
│   └── sites/                 # ⭐ 每个网站独立记忆（相同结构）
│       ├── united.com/
│       ├── delta.com/
│       └── amazon.com/
```

### 2. 基于组件的状态转移建模（Component-Based State Transition Modeling）

> **问题**：知道"屏幕上有什么"还不够——Agent 还需要知道"点击 X 会发生什么"。

UI 被建模为**有向状态图**，每个状态由一组可见组件定义。

**状态定义与匹配：**
- 状态 `s = {c₁, c₂, ..., cₙ}` 是当前屏幕上的组件集合
- 使用 **Jaccard 相似度**匹配状态：`J(s, s') = |s ∩ s'| / |s ∪ s'|`
- 匹配阈值 > 0.7 → 识别当前状态
- 合并阈值 > 0.85 → 相似状态自动合并（防止状态爆炸）

**转移记录与 pending-confirm 验证：**
- 每次点击记录转移元组：`(操作前状态, 被点击组件, 操作后状态)`
- 转移**不会**立即提交——它们作为 *pending* 积累
- 只有当任务**成功完成**时，所有 pending 转移才被确认并写入图
- 失败时 → 所有 pending 转移被丢弃（防止探索性点击污染导航图）

**BFS 路径规划：**
- 积累的转移形成有向图 `G = (S, E)`
- 给定当前状态 `sᶜ` 和目标状态 `sᵗ`，BFS 找到最短操作序列
- 实现直接导航到任何已访问过的状态，无需重新探索
- 不存在路径？→ 回退到探索模式，使用 VLM 推理

```json
// states.json
{
  "state_0": {
    "defining_components": ["Chat_tab", "Cowork_tab", "Search", "Ideas"],
    "description": "应用主视图"
  },
  "state_1": {
    "defining_components": ["Chat_tab", "Account", "Billing", "Usage"],
    "description": "设置页面"
  }
}

// transitions.json — 在 state_0 点击 Settings → 到达 state_1
{
  "state_0": { "Settings": "state_1" },
  "state_1": { "Chat_tab": "state_0" }
}
```

### 3. 渐进式视觉到语义的定位（Progressive Visual-to-Semantic Grounding）

> **问题**：VLM 会产生坐标幻觉。所有现有 GUI 智能体都让 VLM 估计像素位置——导致误点和级联失败。

GUI Agent Skills 随着记忆积累，**渐进地**从图像级转向文本级定位：

**阶段 1 — 图像级定位（陌生界面）：**
- 检测器提供边界框，OCR 提取文字
- VLM 接收完整截图来理解场景
- VLM 决定与哪个元素交互
- 组件被标注并存入记忆
- 这个昂贵的过程**每个组件只发生一次**

**阶段 2 — 文本级定位（熟悉界面）：**
- 模板匹配识别屏幕上的已知组件
- VLM 接收一个**组件名称列表**（如 `[搜索, 设置, 个人资料, 聊天]`）——*而非*截图
- VLM 按名称选择目标（如"点击设置"）
- 系统通过已存储模板将名称解析为精确坐标
- **VLM 永远不估计像素位置**

**为什么这很重要：**
1. **无坐标幻觉** — 坐标完全来自模板匹配
2. **无冗余视觉处理** — 熟悉界面在纯文本空间处理
3. **成本随使用递减** — 随着记忆增长，更多交互使用文本级定位，延迟降低约 5.3 倍，token 消耗降低约 60-100 倍

**分层验证**（工作流执行期间）：

| 层级 | 方法 | 速度 | 使用场景 |
|------|------|------|----------|
| **Level 0** | 模板匹配目标组件 | ~0.3s | 默认首选检查 |
| **Level 1** | 全量检测 + 状态识别 | ~2s | Level 0 失败或有歧义 |
| **Level 2** | VLM 视觉回退 | ~5s+ | Level 1 无法确定状态 |

### 检测引擎

| 检测器 | 速度 | 检测内容 |
|--------|------|----------|
| **[GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)** | ~0.3s | 图标、按钮、输入框 |
| **Apple Vision OCR** | ~1.6s | 文字元素（中英文） |
| **模板匹配** | ~0.3s | 已知组件（首次学习后） |

## 🔴 视觉 vs 命令

GUI Agent Skills 用视觉检测做**决策**，用最高效的方式做**执行**：

| | 必须基于视觉 | 可以用键盘/命令 |
|---|---|---|
| **什么** | 判断状态、定位元素、验证结果 | 快捷键（Ctrl+L）、文字输入、系统命令 |
| **为什么** | Agent 必须先看到屏幕再行动 | 执行可以用最快的方式 |
| **原则** | **决策 = 视觉，执行 = 最佳工具** | |

### 三种视觉方法

| 方法 | 返回 | 用途 |
|------|------|------|
| **OCR** (`detect_text`) | 文字 + 坐标 ✅ | 找文字标签、链接、菜单项 |
| **GPA-GUI-Detector** (`detect_icons`) | 边界框 + 坐标 ✅（无标签） | 找图标、按钮、非文字元素 |
| **image 工具** (LLM 视觉) | 语义理解 ⛔ 不提供坐标 | 理解场景，决定点击什么 |

## 🛡️ 安全与协议

每个操作遵循统一的 检测→匹配→执行→保存 协议：

| 步骤 | 内容 | 原因 |
|------|------|------|
| **检测** | 截屏 + OCR + GPA-GUI-Detector | 获取屏幕元素和坐标 |
| **匹配** | 对比已保存的记忆组件 | 复用已学习的元素（跳过重复检测） |
| **决策** | LLM 选择目标元素 | 视觉理解驱动决策 |
| **执行** | 点击检测坐标 / 键盘快捷键 | 用最佳工具执行 |
| **再检测** | 操作后再次截屏 + OCR + 检测 | 查看发生了什么变化 |
| **差异** | 对比操作前后（出现/消失/持续） | 理解状态转移 |
| **保存** | 更新记忆：组件、标签、转移、页面 | 为未来复用而学习 |

**代码层面强制的安全规则：**
- ✅ 发送消息前验证聊天对象（OCR 读取标题）
- ✅ 操作限制在窗口范围内（不点击目标应用外部）
- ✅ 精确文字匹配（防止 "Scan" 匹配到 "Deep Scan"）
- ✅ 最大窗口检测（多窗口应用跳过状态栏面板）
- ✅ 超时后不盲点 — 截屏 + 检查
- ✅ 每次任务后强制报告耗时和 token 增量

## 🗂️ 项目结构

```
GUI-Agent-Skills/
├── SKILL.md                   # 🧠 主技能——编排层
│                              #    安全协议、视觉/命令边界、按需路由子技能
├── skills/                    # 📖 子技能（7 个专用模块）
│   ├── gui-observe/SKILL.md   #   👁️ 截屏、OCR、状态识别
│   ├── gui-learn/SKILL.md     #   🎓 检测组件、标注、过滤、保存
│   ├── gui-act/SKILL.md       #   🖱️ 统一流程：检测→匹配→执行→差异→保存
│   ├── gui-memory/SKILL.md    #   💾 记忆结构、浏览器 sites/、清理规则
│   ├── gui-workflow/SKILL.md  #   🔄 状态图导航、工作流重放
│   ├── gui-report/SKILL.md    #   📊 任务性能追踪
│   └── gui-setup/SKILL.md     #   ⚙️ 新机器首次设置
├── scripts/
│   ├── setup.sh               # 🔧 一键安装
│   ├── activate.py            # 🌐 平台检测 — 检测 OS 并输出平台信息
│   ├── gui_action.py          # 🎯 统一 GUI 操作接口（click/type/key/screenshot）
│   │                          #    通过 --remote 自动选择后端：mac_local 或 http_remote
│   ├── backends/              # 🔌 平台后端
│   │   ├── mac_local.py       #     macOS：cliclick + AppleScript
│   │   └── http_remote.py     #     远程 VM：通过 HTTP API 调用 pyautogui（如 OSWorld）
│   ├── ui_detector.py         # 🔍 检测引擎（GPA-GUI-Detector + OCR + Swift 窗口信息）
│   ├── app_memory.py          # 🧠 视觉记忆（学习/检测/点击/验证/learn_site）
│   └── template_match.py      # 🎯 模板匹配工具
├── memory/                    # 🔒 视觉记忆（gitignored 但至关重要）
│   ├── apps/<appname>/        #   每个应用的记忆：
│   │   ├── meta.json          #     元数据（detect_count, forget_threshold）
│   │   ├── components.json    #     组件注册表 + 活跃度追踪
│   │   ├── states.json        #     状态（由组件集合定义）
│   │   ├── transitions.json   #     状态转移（字典结构，去重）
│   │   ├── components/        #     模板图片
│   │   ├── pages/             #     页面截图
│   │   └── sites/<domain>/    #   每个网站的记忆（浏览器专用，相同结构）
├── platforms/                  # 🌐 平台指南与检测
│   ├── detect.py              #     平台自动检测脚本
│   ├── macos.md               #     macOS 特定技巧与注意事项
│   ├── linux.md               #     Linux 特定技巧与注意事项
│   └── DESIGN.md              #     跨平台架构设计
├── benchmarks/osworld/        # 📈 OSWorld 基准测试结果
├── assets/                    # 🎨 架构图、banner
├── actions/
│   ├── _actions_macos.yaml    # 📋 macOS 操作定义
│   └── _actions_linux.yaml    # 📋 Linux 操作定义
├── docs/
│   ├── core.md                # 📚 经验教训与硬规则
│   └── README_CN.md           # 🇨🇳 中文文档
├── LICENSE                    # 📄 MIT
└── requirements.txt
```

## 📦 环境要求

- **macOS** + Apple Silicon（M1/M2/M3/M4）— 本地 GUI 自动化
- **Linux**（Ubuntu 22.04+）— 通过 HTTP API 远程控制 VM
- **辅助功能权限**（仅 macOS）：系统设置 → 隐私与安全性 → 辅助功能
- 其余依赖由 `bash scripts/setup.sh` 自动安装

## 🤝 生态系统

| | |
|---|---|
| 🦞 **[OpenClaw](https://github.com/openclaw/openclaw)** | AI 助手框架 — 将 GUI Agent Skills 作为技能加载 |
| 🔍 **[GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector)** | Salesforce/GPA-GUI-Detector — 通用 UI 元素检测模型 |
| 💬 **[Discord 社区](https://discord.gg/vfyqn5jWQy)** | 获取帮助，分享反馈 |

## 📄 许可证

MIT — 详见 [LICENSE](../LICENSE)。

---

## 📌 引用

如果 GUI Agent Skills 对你的研究有帮助，请引用：

```bibtex
@misc{fu2026gui-agent-skills,
  author       = {Fu, Zichuan},
  title        = {GUI Agent Skills: Visual Memory-Driven GUI Automation for macOS},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/Fzkuji/GUI-Agent-Skills},
}
```

---

## ⭐ Star History

<p align="center">
  <a href="https://star-history.com/#Fzkuji/GUI-Agent-Skills&Date">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Fzkuji/GUI-Agent-Skills&type=Date&theme=dark" />
      <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Fzkuji/GUI-Agent-Skills&type=Date" />
      <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Fzkuji/GUI-Agent-Skills&type=Date" width="600" />
    </picture>
  </a>
</p>

<p align="center">
  <sub>由 🦞 GUI Agent Skills 团队构建 · 基于 <a href="https://github.com/openclaw/openclaw">OpenClaw</a></sub>
</p>
