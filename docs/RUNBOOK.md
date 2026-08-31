# GUI Agent Harness 运行手册

> 给 agent / 人类的一份端到端操作指南。照做就能跑。
> 最后更新：2026-04-17

---

## 目录

1. [环境准备（一次性）](#1-环境准备一次性)
2. [项目安装](#2-项目安装)
3. [运行 GUI Agent CLI](#3-运行-gui-agent-cli)
4. [作为 LLM skill 调用](#4-作为-llm-skill-调用)
5. [跑 OSWorld benchmark](#5-跑-osworld-benchmark)
6. [文件路径速查](#6-文件路径速查)
7. [常见问题](#7-常见问题)

---

## 1. 环境准备（一次性）

新机器需要装好这些东西：

### 1.1 系统要求

- macOS（Apple Silicon 优先）或 Linux
- Python ≥ 3.12
- Node.js（装 Claude Code CLI 用）

### 1.2 Claude Code CLI（LLM provider）

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

登录后确认：

```bash
claude --version
```

### 1.3 VMware Fusion + OSWorld VM（只有跑 OSWorld 需要）

- 安装 VMware Fusion
- 从旧机器拷贝整个 `~/OSWorld/vmware_vm_data/` 目录（约 44GB）到新机器同样位置
- 确认 VM 里有名叫 `init_state` 的快照

### 1.4 OSWorld 代码库（只有跑 OSWorld 需要）

```bash
cd ~
git clone https://github.com/xlang-ai/OSWorld.git
cd OSWorld && pip install -e .
```

### 1.5 Surge 代理（可选，VM 联网用）

部分 OSWorld 任务需要 VM 联网。在 macOS 宿主机装 Surge，监听 6152 端口。脚本会自动给 VM 配 `http://172.16.82.1:6152`。

### 1.6 macOS Accessibility 权限

跑本地桌面自动化时：**System Settings → Privacy & Security → Accessibility** → 把终端 app（Terminal / iTerm）加进去。

---

## 2. 项目安装

### 2.1 Clone 代码

```bash
cd ~/Documents
git clone https://github.com/Fzkuji/GUI-Agent-Harness.git
cd GUI-Agent-Harness
```

### 2.2 安装依赖（editable 模式）

```bash
pip install -e .
```

一条命令装完所有依赖：OpenProgram（Agentic Programming 运行时）、ultralytics（GPA-GUI-Detector）、OpenCV、Pillow、numpy、requests 等。

可选的 OCR 支持（Linux 需要）：

```bash
pip install -e ".[ocr]"
```

### 2.3 验证安装

```bash
gui-agent --help
```

看到 usage 说明就算成功。

---

## 3. 运行 GUI Agent CLI

### 3.1 最简用法

```bash
gui-agent --work-dir /tmp/gui-firefox "打开 Firefox 访问 google.com"
```

agent 自己截屏、识别界面、点击、验证，直到任务完成或用完 step。

### 3.2 常用参数

```bash
gui-agent [OPTIONS] TASK

--work-dir PATH       必填。runtime 使用的可写工作目录
--vm URL              远程 VM HTTP API（如 http://172.16.82.132:5000）
--provider NAME       指定 provider: openai-codex / claude-code / anthropic / openai / gemini-cli / gemini
--model NAME          模型名（opus / sonnet / gpt-4o）
--runtime-retries N   可重试模型错误的最大尝试次数（默认 5）
--max-steps N         最大步数（默认 150）
--app NAME            component 记忆的 app 名（默认 desktop）
--no-general          禁用命令行 fallback，只允许 GUI 动作
```

### 3.3 示例

```bash
# 本地桌面
gui-agent --work-dir /tmp/gui-files "把 Desktop 上的 report.pdf 移到 Documents"

# OSWorld VM
gui-agent --work-dir /tmp/gui-vm --vm http://172.16.82.132:5000 "在 Chrome 里打开 GitHub"

# 指定模型
gui-agent --work-dir /tmp/gui-crop --provider claude-code --model opus "Crop 图片顶部 20%"

# 提高步数上限
gui-agent --work-dir /tmp/gui-long --max-steps 30 "完成整个多步任务"
```

### 3.4 程序内调用

```python
from gui_harness.main import gui_agent

result = gui_agent(
    task="打开 Firefox 访问 google.com",
    max_steps=15,
    app_name="firefox",
)
print(result)
# {"task": ..., "success": True, "steps_taken": 7, "total_time": 42.3, "history": [...]}
```

---

## 4. 作为 LLM skill 调用

### 4.1 原理

GUI Agent Harness 是为 LLM 设计的工具：LLM 收到用户的 GUI 任务 → 根据 `SKILL.md` 指引 → 调用 `gui-agent` CLI → 拿回结果。LLM 不需要关心 GUI 识别细节。

### 4.2 给 Claude Code 注册 skill

**方式 1：从项目目录直接运行（自动发现）**

```bash
cd /path/to/GUI-Agent-Harness
claude
# Claude Code 会自动读到当前目录下的 SKILL.md
```

**方式 2：加进 skill 搜索路径**

```bash
claude config set skillPaths '["/path/to/GUI-Agent-Harness"]'
```

**方式 3：软链接到 skills 目录**

```bash
ln -s /path/to/GUI-Agent-Harness ~/.claude/skills/gui-agent
```

### 4.3 给 OpenClaw 注册

```bash
cp -r GUI-Agent-Harness ~/.openclaw/skills/gui-agent
# 或软链
ln -s /path/to/GUI-Agent-Harness ~/.openclaw/skills/gui-agent
```

### 4.4 验证 skill 工作

在 Claude Code 里说：

```
帮我把 Desktop 上的 report.pdf 移到 Documents 文件夹
```

Claude 应该识别出这是 GUI 任务，然后调用 `gui-agent --work-dir /tmp/gui-agent "..."`。

---

## 5. 跑 OSWorld benchmark

### 5.1 单个任务

```bash
cd /path/to/GUI-Agent-Harness
python benchmarks/osworld/run_osworld_task.py <task_num> [options]
```

示例：

```bash
# Multi-Apps 第 88 题
python benchmarks/osworld/run_osworld_task.py 88 --max-steps 15

# GIMP 第 4 题
python benchmarks/osworld/run_osworld_task.py 4 --domain gimp --max-steps 20

# 指定 VM IP
python benchmarks/osworld/run_osworld_task.py 44 --vm 172.16.82.132
```

参数：

```
task_num              任务编号（1-indexed，按 domain 算）
--domain DOMAIN       domain（默认 multi_apps）
                      可选: multi_apps / chrome / gimp / os /
                            libreoffice_calc / libreoffice_impress /
                            libreoffice_writer / thunderbird / vlc / vscode
--vm VM_IP            VM 的 IP（默认 172.16.82.132）
--max-steps N         agent 最大步数（默认 15）
--no-setup            跳过 VM revert（重试同一任务用）
--no-eval             只跑 agent，不跑官方 evaluator
```

脚本会自动：

1. `vmrun revertToSnapshot` 回到 `init_state`
2. 跑 OSWorld 官方 setup（下文件、开应用、开 URL）
3. 装 Chromium proxy wrapper，设系统代理，调分辨率到 1920×1080
4. 跑 `gui_agent()`
5. 跑官方 evaluator 打分
6. 打印分数、步数、耗时、每步动作历史

### 5.2 批量跑

```bash
bash benchmarks/osworld/run_batch.sh <start> <end> [domain]
```

示例：

```bash
# Multi-Apps 全部 101 道
bash benchmarks/osworld/run_batch.sh 1 101 multi_apps

# GIMP 1-26
bash benchmarks/osworld/run_batch.sh 1 26 gimp

# Multi-Apps 81-90
bash benchmarks/osworld/run_batch.sh 81 90 multi_apps
```

每个任务的日志存在 `/tmp/osworld_batch_<domain>/task<N>.log`。跑完会打印总结。

### 5.3 只重跑 evaluator

已经跑过 agent，只想重新评分：

```bash
python benchmarks/osworld/eval_osworld_task.py <task_num> --vm <VM_IP>
```

### 5.4 结果记录

benchmark 每个 domain 的成绩在 `benchmarks/osworld/<domain>.md`，每个任务一行，记分数和备注。跑完自己手动更新这些文档。

---

## 6. 文件路径速查

### 6.1 硬编码的关键路径（在 `run_osworld_task.py` 里）

```python
OSWORLD_DIR = ~/OSWorld                                     # OSWorld 仓库
VMRUN = /Applications/VMware Fusion.app/.../vmrun           # vmrun CLI
VMX = ~/OSWorld/vmware_vm_data/Ubuntu-arm/Ubuntu.vmx        # VM 文件
VM_IP = 172.16.82.132                                       # 默认 VM IP（可被 --vm 覆盖）
PROXY_URL = http://172.16.82.1:6152                         # Surge 代理
```

新机器上路径不一样的话，改这几行或者加 `--vm` 参数。

### 6.2 项目结构

```
GUI-Agent-Harness/
├── gui_harness/
│   ├── main.py                    # CLI 入口 + gui_agent() 循环
│   ├── runtime.py                 # LLM provider 自动检测
│   ├── tasks/execute_task.py      # 4-phase step: observe→verify→plan→dispatch
│   ├── action/input.py            # 鼠标键盘原语
│   ├── action/general_action.py   # 命令行 fallback
│   ├── perception/screenshot.py   # 截屏（本地 + VM）
│   ├── planning/component_memory.py  # 模板匹配 + state 管理
│   ├── memory/app_memory.py       # 记忆读写（原子写 + backup）
│   └── adapters/vm_adapter.py     # 转发到 VM
├── libs/agentic-programming/      # OpenProgram 运行时（git submodule，路径名过渡期保留）
├── benchmarks/osworld/
│   ├── run_osworld_task.py        # 主 runner
│   ├── run_batch.sh               # 批量脚本
│   ├── eval_osworld_task.py       # 只跑 evaluator
│   └── <domain>.md                # 各 domain 成绩
├── memory/                        # 视觉记忆（per-platform, per-app）
│   └── <platform>/apps/<app>/
│       ├── components.json        # component 注册表
│       ├── states.json            # UI 状态
│       ├── transitions.json       # 状态转移图
│       └── components/*.png       # 模板图
├── SKILL.md                       # LLM skill 定义
└── pyproject.toml
```

---

## 7. 常见问题

### 7.1 "claude command not found"

Claude Code CLI 没装。重新跑 `npm install -g @anthropic-ai/claude-code`。

### 7.2 VM 联不上

```
Waiting for VM at http://172.16.82.132:5000... (超时)
```

- 确认 VM 已启动（VMware Fusion 界面能看到）
- 在 VM 里跑 `ifconfig` 确认 IP，用 `--vm` 指定对的 IP
- 确认 VM 里 OSWorld 的 HTTP server 在跑（端口 5000）

### 7.3 VM 任务访问不了外网

装 Surge，监听 6152 端口。脚本会自动设 VM 代理。

### 7.4 evaluator 连不上 Chrome CDP

脚本启动 Chromium 时已经加了 `--remote-debugging-port=1337`。如果还报错，检查 VM 里 Chromium 是不是真的在跑 + 有没有被其他进程占端口。

### 7.5 transitions.json 损坏

框架现在有原子写 + `.bak` 备份自动恢复。真坏了手动删掉 `memory/<platform>/apps/<app>/transitions.json`，下次跑会自动重建。

### 7.6 agent 一直卡在 verify 循环

通常是前一步是 "general"（命令行）动作，verify 误判 GUI 没变。现在 prompt 里已经加了说明。如果还出问题，检查 `gui_harness/tasks/execute_task.py` 里 `verify_step` 的 docstring。

### 7.7 session 每步都新开

这是已知问题：Claude Code 的 `--continue` 在 stream-json 模式下行为待查。不影响正确性，只影响 cache 命中率。

### 7.8 想让 agent 强制走 GUI，不能用命令行

CLI 默认允许命令行 fallback。需要强制只走 GUI 时使用：

```bash
gui-agent --work-dir /tmp/gui-only --no-general "任务描述"
```

---

## 附：最简冒烟测试

装完后跑这个确认一切正常：

```bash
# 1. CLI 能启动
gui-agent --help

# 2. 本地截屏能工作
python -c "from gui_harness.perception.screenshot import take; print(take())"

# 3. VM 连得上（需要 VM 已启动）
curl http://172.16.82.132:5000/screenshot -o /tmp/vm.png && ls -la /tmp/vm.png

# 4. 跑一个最简单的 OSWorld 任务
python benchmarks/osworld/run_osworld_task.py 1 --domain os --max-steps 10
```

每步都通过 → 环境 OK。
