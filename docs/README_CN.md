<div align="center">
  <img src="../assets/banner.png" alt="GUI Agent Harness" width="100%" />

  <br />

  <p>
    <strong>自主GUI代理——给它一个任务，它操作桌面。</strong>
    <br />
    <sub>视觉记忆 &bull; 一次学习即可操作 &bull; 支持多种LLM &bull; 本地或虚拟机</sub>
  </p>

  <p>
    <a href="#快速开始"><img src="https://img.shields.io/badge/快速开始-blue?style=for-the-badge" /></a>
    <a href="https://github.com/Fzkuji/OpenProgram"><img src="https://img.shields.io/badge/OpenProgram-green?style=for-the-badge" /></a>
    <a href="https://discord.gg/vfyqn5jWQy"><img src="https://img.shields.io/badge/Discord-7289da?style=for-the-badge&logo=discord&logoColor=white" /></a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/平台-macOS_%7C_Linux-black?logo=apple" />
    <img src="https://img.shields.io/badge/Provider-Claude_%7C_OpenClaw_%7C_OpenAI-orange" />
    <img src="https://img.shields.io/badge/检测-GPA--GUI--Detector-green" />
    <img src="https://img.shields.io/badge/OCR-Apple_Vision_%7C_EasyOCR-blue" />
    <img src="https://img.shields.io/badge/License-MIT-yellow" />
    <img src="https://img.shields.io/badge/OSWorld_Multi--Apps-79.8%25_(72.6/91)-brightgreen" />
  </p>
</div>

---

<p align="center">
  <a href="../README.md">🇺🇸 English</a> ·
  <b>🇨🇳 中文</b>
</p>

---

## 最新动态

- **[2026-04-14]** 🏆 **OSWorld Multi-Apps 79.8%** — 91个任务中得分72.6。4阶段步骤循环 + CLI session持久化 + PRESERVE FORMAT工作习惯。[详细结果 →](../benchmarks/osworld/multi_apps.md)
- **[2026-04-18]** 📦 **OpenProgram** — Agentic Programming 从概念落地为产品：仓库/包/CLI 统一改名为 [OpenProgram](https://github.com/Fzkuji/OpenProgram)。Agentic Programming 保留为范式/哲学名称；OpenProgram 是可发布的框架。Harness 的 import 已迁到 `from openprogram import ...`。
- **[2026-04-07]** 🤖 **Agent原生架构** — 基于 [Agentic Programming](https://github.com/Fzkuji/OpenProgram) 范式重建执行核心，将GUI感知与自由形式的agent动作统一到单一决策循环中。
- **[2026-03-29]** 🎬 **v0.3 — 统一动作与跨平台GUI** — 平台后端自动选择。
- **[2026-03-23]** 🏆 **OSWorld Chrome 93.5%** — 单次尝试43/46，两次尝试97.8%（45/46）。
- **[2026-03-10]** 🚀 **首次发布** — GPA-GUI-Detector + Apple Vision OCR + 模板匹配 + 按应用的视觉记忆。

## 什么是 GUI Agent Harness？

一个将任意LLM变成GUI自动化代理的CLI工具。你给它一个自然语言任务，它自主操作桌面——截图、点击、输入、验证，循环执行直到任务完成。

```bash
gui-agent "安装 Orchis GNOME 主题"
gui-agent --vm http://172.16.82.132:5000 "在Chrome中打开GitHub和Python文档"
```

**设计为LLM工具。** 预期的工作流程是：
1. LLM（Claude Code、OpenClaw等）从用户那里收到一个GUI任务
2. LLM的skill/prompt告诉它调用 `gui-agent` CLI工具
3. `gui-agent` 在内部处理所有GUI感知和交互
4. LLM收到结果摘要

LLM不需要了解GUI自动化的工作原理——它只需调用工具。

## 核心思路

- **视觉记忆** — UI组件首次检测后，由VLM标注并存储为模板。后续遇到时，模板匹配替代昂贵的重新检测（快约5倍，token消耗减少约60倍）。
- **状态转移** — UI被建模为状态图（每个状态由一组可见组件定义）。成功的操作序列被记录为转移关系，供未来重放。
- **4阶段步骤循环** — 每步执行：观察（截图+检测）→ 验证（检查上一步结果）→ 规划（LLM决定下一步操作）→ 执行。所有阶段都是 `@agentic_function` 调用，步骤间有结构化反馈。
- **Provider无关** — 支持 Claude Code CLI、OpenClaw、Anthropic API 或 OpenAI API。自动检测最佳可用provider。

## OSWorld 结果

**Multi-Apps 域：79.8%（91个评估任务中得分72.6）**

| 指标 | 数值 |
|------|------|
| 总任务数 | 101 |
| 已评估 | 91 |
| 被阻塞（缺少凭据） | 10 |
| 通过（得分 = 1.0） | 63 |
| 部分通过（0 < 得分 < 1.0） | 11 |

完整结果：[benchmarks/osworld/multi_apps.md](../benchmarks/osworld/multi_apps.md)

## 快速开始

### 第一步：安装

GUI agent 就是个普通的 OpenProgram 程序——两步：

1. **装 OpenProgram**（host）——见 [github.com/Fzkuji/OpenProgram](https://github.com/Fzkuji/OpenProgram)。
2. **装 GUI agent：**

   ```bash
   openprogram programs install gui
   ```

完事。`gui_agent` 随即注册好，出现在网页 UI 和 `gui-agent` 命令里。第一次跑 `openprogram` 会自动引导你配 provider；GUI agent 在首次使用时会自动下载检测权重 + OCR 模型。

> **macOS：** 在 系统设置 → 隐私与安全性 中给终端授予 屏幕录制 + 辅助功能 权限，它才能看屏幕、控鼠标键盘。NVIDIA GPU 加速、离线预取、进阶参数见 **[docs/install.md](install.md)**。

### 第二步：运行

`--work-dir` 是 agent 可写的绝对路径，按你的系统填对应路径：

```bash
# macOS / Linux — 本地桌面
gui-agent --work-dir /tmp/gui-agent-firefox --app firefox "打开 Firefox 并访问 google.com"

# Windows (PowerShell) — 本地桌面
gui-agent --work-dir C:\temp\gui-agent-firefox --app firefox "打开 Firefox 并访问 google.com"

# 任意平台 — 驱动远程虚拟机（如 OSWorld）
gui-agent --work-dir /tmp/gui-agent-vm --vm http://VM_IP:5000 "安装 Orchis GNOME 主题"

# 指定 provider / 模型
gui-agent --work-dir /tmp/gui-agent --provider claude-code --model opus "在微信中发送你好"
```

### 作为LLM Skill使用

GUI Agent Harness 设计为被LLM作为工具调用。`pip install` 安装完成后，将项目注册为skill，让LLM能够发现并使用它。

LLM的skill系统通常会扫描一个skills目录，寻找包含 `SKILL.md` 的子目录。将GUI Agent Harness复制或软链接到LLM的skills目录即可：

```bash
# 示例：复制到OpenClaw的skills目录
cp -r GUI-Agent-Harness ~/.openclaw/skills/gui-agent

# 或者软链接（推荐——与git保持同步）
ln -s /path/to/GUI-Agent-Harness ~/.openclaw/skills/gui-agent
```

**Claude Code** 从当前工作目录或配置的skill路径中自动发现 `SKILL.md`：

```bash
# 方式1：在项目目录下工作（自动发现）
cd /path/to/GUI-Agent-Harness

# 方式2：添加到Claude Code的skill搜索路径
claude config set skillPaths '["<path-to-GUI-Agent-Harness>"]'
```

注册后，LLM会读取 `SKILL.md`，知道何时以及如何调用 `gui-agent`——无需其他配置。

## CLI 参数

```
gui-agent [OPTIONS] TASK

参数:
  TASK                  自然语言任务描述

选项:
  --vm URL              远程VM HTTP API（如 http://172.16.82.132:5000）
  --provider NAME       强制指定LLM provider：claude-code, openclaw, anthropic, openai
  --model NAME          覆盖模型名（如 opus, sonnet, gpt-4o）
  --max-steps N         最大操作步数（默认：15）
  --app NAME            应用名称，用于组件记忆（默认：desktop）
```

## 架构

```
gui-agent "任务描述"
    │
    ▼
gui_agent()                    ← @agentic_function，驱动循环
    │
    ├── for step in 1..max_steps:
    │       │
    │       ▼
    │   gui_step()             ← @agentic_function，编排
    │       │
    │       ├── 1. 观察     (Python) — 截图 + 检测 + 匹配 + 状态识别
    │       ├── 2. 验证     (LLM)   — 检查上一步操作的结果
    │       ├── 3. 规划     (LLM)   — 决定下一步操作
    │       └── 4. 执行     (Python) — 点击/输入/滚动/通用
    │       │
    │       ▼
    │   build_step_feedback()  ← 结构化结果 → 下一轮迭代
    │
    └── 返回结果摘要
```

**观察** — 纯Python。截图，运行GPA-GUI-Detector + OCR，与存储的组件模板匹配，识别当前UI状态。

**验证** — LLM调用。检查上一步操作后的截图，报告操作是否成功。不决定任务是否完成。

**规划** — LLM调用。看到截图、检测到的组件、验证结果和已知状态转移。选择一个操作（点击、输入、滚动、通用、完成）。

**执行** — 纯Python。执行规划的操作。对于点击，使用模板匹配找到精确坐标。对于"通用"操作，委托给LLM使用完整工具（Bash、文件I/O等）。

## 视觉记忆

UI元素首次被检测时，获得**双重表示**：裁剪的视觉模板（用于快速匹配）和VLM分配的语义标签（用于推理）。按应用存储，跨所有未来会话复用。

```
memory/
├── linux/                     # 平台特定记忆
│   └── apps/
│       ├── desktop/           # 通用桌面组件
│       ├── chromium/          # 浏览器UI
│       │   └── sites/         # 按网站的记忆
│       ├── gimp/
│       └── libreoffice-calc/
│           ├── components.json    # 组件注册表
│           ├── states.json        # UI状态（组件集合）
│           ├── transitions.json   # 状态图边
│           └── components/        # 模板图片
```

**基于活跃度的遗忘** — 组件跟踪连续未匹配次数。15次未匹配后自动移除，保持记忆与应用当前UI同步。

**状态匹配** — 状态是可见组件的集合，通过Jaccard相似度匹配（>0.7 = 相同状态，>0.85 = 自动合并）。

## 检测栈

| 检测器 | 速度 | 检测内容 |
|--------|------|----------|
| [GPA-GUI-Detector](https://huggingface.co/Salesforce/GPA-GUI-Detector) | ~0.3秒 | 图标、按钮、输入框 |
| Apple Vision OCR / EasyOCR | ~1.6秒 | 文本元素 |
| 模板匹配 | ~0.3秒 | 已知组件（首次检测后） |

## 基于 OpenProgram 构建

GUI Agent Harness 基于 [OpenProgram](https://github.com/Fzkuji/OpenProgram) 构建——**Agentic Programming** 范式的参考实现：带有LLM驱动docstring的Python函数变为自主代理。每个函数（`verify_step`、`plan_next_action`、`general_action`）都是一个 `@agentic_function`，精确调用LLM一次并返回结构化数据。

```python
from openprogram import agentic_function

@agentic_function(summarize={"siblings": -1})
def plan_next_action(task, img_path, ..., runtime=None) -> dict:
    """决定下一步操作以完成任务。

    你是一个GUI自动化代理。选择一个要执行的操作。
    ...
    """
    reply = runtime.exec(content=[
        {"type": "text", "text": context},
        {"type": "image", "path": img_path},
    ])
    return parse_json(reply)
```

Docstring就是prompt。函数签名定义接口。框架处理上下文管理、历史摘要和provider抽象。

> **命名说明**：*Agentic Programming* 是范式（哲学 —— 装饰器 + 上下文树 + 元函数）；*OpenProgram* 是产品（承载运行时的 Python 包）。`@agentic_function` 装饰器名保留下来，作为血统标识。

## LLM Provider 优先级

| 优先级 | Provider | 费用 | 备注 |
|--------|----------|------|------|
| 1 | OpenClaw | 订阅制 | 检测到 `openclaw` CLI 自动使用 |
| 2 | Claude Code CLI | 订阅制 | 检测到 `claude` CLI 自动使用 |
| 3 | Anthropic API | 按token计费 | 需要 `ANTHROPIC_API_KEY` |
| 4 | OpenAI API | 按token计费 | 需要 `OPENAI_API_KEY` |

可通过 `--provider` 和 `--model` 参数覆盖。

## 项目结构

```
GUI-Agent-Harness/
├── gui_harness/
│   ├── main.py                # CLI入口 + gui_agent循环
│   ├── runtime.py             # LLM provider自动检测
│   ├── tasks/
│   │   └── execute_task.py    # 4阶段步骤：观察→验证→规划→执行
│   ├── action/
│   │   ├── input.py           # 鼠标/键盘原语
│   │   └── general_action.py  # 自由形式LLM操作（可使用工具）
│   ├── perception/
│   │   └── screenshot.py      # 截图（本地 + VM）
│   ├── planning/
│   │   ├── component_memory.py  # 模板匹配 + 状态管理
│   │   └── learn.py           # 首次应用组件学习
│   ├── memory/                # 记忆管理工具
│   └── adapters/
│       └── vm_adapter.py      # 将所有I/O重定向到远程VM
├── libs/
│   └── agentic-programming/   # OpenProgram 运行时（git 子模块）
│                              # 路径名在上游仓库改名过渡期暂保留
├── benchmarks/
│   └── osworld/               # OSWorld基准测试运行器 + 结果
├── memory/                    # 视觉记忆存储（按平台、按应用）
├── SKILL.md                   # LLM skill定义
└── pyproject.toml
```

## 环境要求

- **Python 3.12+**
- **macOS**（推荐Apple Silicon以使用Vision OCR）或 **Linux**
- 至少一个LLM provider（Claude Code CLI、OpenClaw或API密钥）
- VM自动化需要：OSWorld或兼容的HTTP API

## 许可证

MIT — 详见 [LICENSE](../LICENSE)。

## 引用

```bibtex
@misc{fu2026gui-agent-harness,
  author       = {Fu, Zichuan},
  title        = {GUI Agent Harness: Autonomous GUI Automation with Visual Memory},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/Fzkuji/GUI-Agent-Harness},
}
```

---

<p align="center">
  <sub>基于 <a href="https://github.com/Fzkuji/OpenProgram">OpenProgram</a> 构建 —— Agentic Programming 范式的产品化实现</sub>
</p>
