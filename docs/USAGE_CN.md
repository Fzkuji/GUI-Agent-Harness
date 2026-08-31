# GUI Agent Harness 使用说明

本文按当前代码接口写，优先以 `python -m gui_harness` 为准；安装 entry point 后也可以把命令里的 `python -m gui_harness` 换成 `gui-agent`。

## 当前验证结果

在本机仓库目录 `/Users/fzkuji/Documents/GUI Agent/GUI-Agent-Harness` 已验证：

- `python -m gui_harness --help` 可正常显示 CLI 参数。
- `gui_harness.openprogram_compat.create_runtime(provider="auto")` 可创建 runtime，当前自动选择的是 `OpenAICodexRuntime`，并支持 `set_workdir()`。
- 直接调用 `gui_harness.planning.observe.observe()` 可完成一次本地屏幕观察，返回 `app_name`、`visible_text`、`interactive_elements`、`page_description`、`screenshot_path` 等字段。验证任务只观察屏幕，没有执行点击、输入、滚动或打开应用。
- VM 地址 `http://172.16.82.132:5000` 已验证可用：`/screenshot` 返回 `200 image/png`，`/execute` 可以在 Ubuntu guest 内执行命令。
- 已实际运行一次 VM GUI 操作：点击 Ubuntu 左上角 `Activities` 按钮，并在第二步确认 Activities overview 可见。

## 命令行入口

最稳定的调用方式：

```bash
cd "/Users/fzkuji/Documents/GUI Agent/GUI-Agent-Harness"
python -m gui_harness \
  --work-dir /private/tmp/gui-agent-work \
  --provider auto \
  --app desktop \
  --max-steps 10 \
  "描述你要完成的 GUI 任务"
```

已安装 editable entry point 后，也可以使用：

```bash
gui-agent \
  --work-dir /private/tmp/gui-agent-work \
  --provider auto \
  --app desktop \
  --max-steps 10 \
  "描述你要完成的 GUI 任务"
```

`--work-dir` 是必填参数。它是 LLM runtime 写文件、执行命令时使用的工作目录。建议用专门目录，例如 `/private/tmp/gui-agent-work` 或项目内的 `runs/manual/<task-name>`。

## 常用参数

```text
TASK                  自然语言任务描述
--work-dir PATH       必填。runtime 的工作目录
--vm URL              远程 VM HTTP API，例如 http://172.16.82.132:5000
--provider NAME       指定 provider：auto、claude-code、anthropic、openai 等
--model NAME          指定模型名
--max-steps N         最大行动步数，默认 150
--app NAME            组件记忆的 app 名，默认 desktop
--no-general          禁用命令行 general action，只允许 GUI 动作
```

`--no-general` 适合需要严格通过 GUI 完成的任务，例如 OSWorld/GIMP 这类评测。未加 `--no-general` 时，planner 可以选择 `general` action，让 runtime 通过命令行或文件操作完成一部分子任务。

## 可以操作的软件类型

本地桌面模式适合操作当前屏幕上可见的软件，例如：

- 浏览器：Chrome、Firefox、Safari。
- 编辑器：TextEdit、VS Code、终端。
- 图像软件：GIMP、Preview。
- 办公软件：LibreOffice Writer、Calc、Impress。
- 系统设置窗口、文件管理器、安装器。

VM 模式适合操作 OSWorld Ubuntu VM 内的软件，例如 Chrome、GIMP、LibreOffice、VLC、Thunderbird、VS Code 和系统设置。

## 本地软件操作示例

先确保目标软件已经打开，或者任务里明确要求打开软件。macOS 本地操作需要给 Terminal/iTerm 辅助功能权限。

只观察当前屏幕，不改变界面：

```bash
python -m gui_harness \
  --work-dir /private/tmp/gui-agent-observe \
  --provider auto \
  --app desktop \
  --max-steps 1 \
  --no-general \
  "只观察当前屏幕并说明看到的内容。不要点击、输入、滚动或打开应用。"
```

操作浏览器：

```bash
python -m gui_harness \
  --work-dir /private/tmp/gui-agent-browser \
  --provider auto \
  --app chrome \
  --max-steps 12 \
  "打开 Chrome，访问 https://example.com，并确认页面标题可见。"
```

操作 GIMP，并强制只用 GUI 动作：

```bash
python -m gui_harness \
  --work-dir /private/tmp/gui-agent-gimp \
  --provider auto \
  --app gimp \
  --max-steps 20 \
  --no-general \
  "在当前 GIMP 窗口中打开 Filters 菜单，并选择 Blur 相关功能。"
```

操作文件或系统设置时，如果允许命令行辅助，不加 `--no-general`；如果需要真实 GUI 交互，加 `--no-general`。

## VM/OSWorld 模式

VM 模式调用：

```bash
python -m gui_harness \
  --work-dir /private/tmp/gui-agent-vm \
  --vm http://<VM_IP>:5000 \
  --provider auto \
  --app desktop \
  --max-steps 15 \
  "在 VM 里打开 Chrome 并访问 GitHub。"
```

如果是 OSWorld benchmark，优先使用仓库自带 runner，而不是手写 VM setup：

```bash
python benchmarks/osworld/run_osworld_task.py 88 --domain multi_apps --max-steps 15
python benchmarks/osworld/run_osworld_task.py 4 --domain gimp --max-steps 20
```

runner 会负责恢复 VM 快照、执行 OSWorld setup、设置分辨率、运行 agent 和调用 evaluator。

## Python 内部调用

完整 loop 调用：

```python
import os
from gui_harness.openprogram_compat import create_runtime
from gui_harness.main import gui_agent

work_dir = "/private/tmp/gui-agent-python"
os.makedirs(work_dir, exist_ok=True)

runtime = create_runtime(provider="auto")
runtime.set_workdir(work_dir)

result = gui_agent(
    task="打开 Chrome 并访问 https://example.com",
    max_steps=10,
    app_name="chrome",
    runtime=runtime,
    allow_general=True,
)
print(result["success"], result["summary"])
```

只做观察，不执行动作：

```python
import os
from gui_harness.openprogram_compat import create_runtime
from gui_harness.planning.observe import observe

work_dir = "/private/tmp/gui-agent-observe"
os.makedirs(work_dir, exist_ok=True)

runtime = create_runtime(provider="auto")
runtime.set_workdir(work_dir)

result = observe(
    task="Describe the current screen without changing anything.",
    app_name="desktop",
    runtime=runtime,
)
print(result["page_description"])
```

## 内部执行流程

一次 `gui_agent()` 运行会重复以下步骤：

1. `observe`：截图、OCR、GPA-GUI-Detector 检测、模板匹配、识别当前 UI 状态。
2. `verify_step`：如果已有上一步动作，检查动作结果。
3. `plan_next_action`：LLM 根据截图、文本、组件、验证结果选择下一步。
4. `_dispatch`：执行动作。
5. `build_step_feedback`：把动作结果整理给下一轮。
6. `conclusion`：任务结束后生成结果摘要。

可执行动作包括：

- `click`
- `double_click`
- `right_click`
- `drag`
- `type`
- `press`
- `hotkey`
- `scroll`
- `general`
- `done`

点击类动作不会让 LLM 直接编坐标，而是先调用 `locate_target()`，再通过 OCR、模板匹配和检测结果定位目标。

## 记忆文件

组件记忆默认保存在：

```text
gui_harness/memory/apps/<app_name>/
```

主要文件：

- `meta.json`：app 级元信息。
- `components.json`：组件标签和模板文件路径。
- `states.json`：UI 状态图。
- `transitions.json`：成功动作产生的状态转移。
- `components/*.png`：组件截图模板。
- `workflows/workflow_*.json`：任务运行记录。

`--app` 会影响这些文件的命名空间。操作 Chrome 就用 `--app chrome`，操作 GIMP 就用 `--app gimp`，只看桌面就用 `--app desktop`。

## 运行前检查

本地桌面任务：

```bash
python -m gui_harness --help
python - <<'PY'
from gui_harness.openprogram_compat import create_runtime
rt = create_runtime(provider="auto")
print(type(rt).__name__, hasattr(rt, "set_workdir"))
PY
```

VM 任务：

```bash
curl --noproxy '*' -sS -o /tmp/vm-screen.png \
  -w '%{http_code} %{content_type} %{size_download}\n' \
  --max-time 5 \
  http://<VM_IP>:5000/screenshot

curl --noproxy '*' -sS -X POST http://<VM_IP>:5000/execute \
  -H 'Content-Type: application/json' \
  -d '{"command":"echo vm_execute_ok && hostname && date","shell":true}' \
  | python -m json.tool
```

如果 VM screenshot 不是 `200 image/png`，先确认 VMware VM 已启动、guest IP 是否变化、OSWorld server 是否在 5000 端口运行。宿主机有代理时，访问 VM 内网地址要保留 `--noproxy '*'`。
