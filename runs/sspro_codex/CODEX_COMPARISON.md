# ScreenSpot-Pro 三级脚手架对比(同一 GPT-5.5)

同一模型(gpt-5.5)、同一 benchmark(ScreenSpot-Pro 全量 1,581,point-in-bbox 判分)、
三种脚手架。①② 用官方 Codex CLI v0.142.5,**每题一次性隔离 CODEX_HOME**(只含登录凭证,
无 memory/skills/MCP,零跨样本记忆),**prompt 仅为 SSPro 原始指令**(不给尺寸/坐标系/
工具提示),输出经 `--output-schema` 强制为 `{x,y}`。零调参。

## 总结果

| 条件 | 配置 | 正确率 |
|---|---|---|
| ① 纯 API 单发 | codex exec,reasoning=none,read-only 沙箱,无工具 | **2.4%** (38/1581) |
| ② Codex 框架(agent) | codex exec,reasoning=high,workspace-write 沙箱,可自主用工具 | **11.9%** (188/1581) |
| ③ 本 harness(迭代缩放) | GPA 检测 + 候选排序 + 迭代缩放 + 提交门 | **87.9%** (1390/1581) |

## 分组对比(ss / agent / harness)

| Group | ① 单发 | ② codex 框架 | ③ harness |
|---|---|---|---|
| CAD | 2% | 23% | 86% |
| Creative | 1% | 9% | 85% |
| Dev | 3% | 10% | 87% |
| OS | 1% | 8% | 90% |
| Office | 3% | 10% | 96% |
| Scientific | 5% | 12% | 85% |

## 结论

1. **脚手架阶梯**:无脚手架 2.4% → 通用 agent 框架 11.9%(+9.5)→ 领域 harness 87.9%
   (再 +76.0)。同一模型,差距全部来自脚手架。
2. **codex 框架确有自发能力**:scratch 残留显示它会自己写 PIL 裁图/放大(`crop0_4x.png`
   等),无人提示——方向与本 harness 相同,但无结构化的多轮缩放协议、候选证据与提交门,
   收益有限(仅 +9.5)。
3. **纯指令输入下坐标系是主要失败源之一**:不告知原图尺寸时,模型常按缩略画布输出坐标。
   这是三条同规则下的公平结果——本 harness 在管线内部自行管理坐标系,这本身即脚手架价值
   的一部分。
4. 运行注:agent 模式早期曾以全权沙箱运行,会对 "click X" 类指令真实操作系统鼠标,已改为
   workspace-write/read-only 沙箱;两模式最终结果均在沙箱模式下补齐,无 error 行。
