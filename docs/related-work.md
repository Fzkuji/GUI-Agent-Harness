# Related Work — GUI Agent Visual Memory

整理与 gui-agent 视觉记忆设计相关的论文和方法。

---

## 核心相关：组件视觉 + 语义记忆

### MAGNET — Memory-Driven Knowledge Evolution for Adaptive GUI Agents
- **Paper**: [arXiv:2601.19199](https://arxiv.org/abs/2601.19199) (2026.01)
- **Authors**: Libo Sun, Jiwen Zhang, Siyuan Wang, Zhongyu Wei (复旦大学)
- **核心思路**: 双层记忆应对 UI 版本变化
  - **Stationary Memory**: 存储 `(UI element patch, functional semantics)` 对，将多样的视觉特征映射到稳定的功能语义，用于跨版本 action grounding
  - **Procedural Memory**: 存储任务意图的 workflow 模板，在 workflow 变化时迁移
  - **Dynamic Memory Evolution**: 持续优化，优先保留高频访问的知识
- **Benchmark**: AndroidWorld (online), AITW/MoTIF/AitZ (offline)
- **与我们的关系**: ⭐⭐⭐ **最接近的工作**
  - 都是"裁剪 UI 组件图像 + 关联功能语义"
  - 区别 1: 他们解决 appearance drift（跨版本），我们解决 recognition accuracy（同版本内学习）
  - 区别 2: 他们需要 fine-tune pipeline，我们纯 prompt-based
  - 区别 3: 他们面向 mobile，我们面向 desktop (macOS/Linux)

### MGA — Memory-Driven GUI Agent for Observation-Centric Interaction
- **Paper**: arXiv (2025.10), Submitted to WWW2025
- **Authors**: Weihua Cheng, Ersheng Ni et al.
- **核心思路**: 翻转"先决策后观察"为"先观察后决策"，用记忆减少 error propagation
- **与我们的关系**: ⭐⭐ 思路方向类似（observation-first），但未明确做组件级视觉记忆

---

## 连续向量记忆

### Auto-scaling Continuous Memory for GUI Agent
- **Paper**: [arXiv:2510.09038](https://arxiv.org/abs/2510.09038) (2025.10)
- **Authors**: Wenyi Wu, Kun Zhou, Ruoxin Yuan et al.
- **核心思路**:
  - 用 VLM 自身作为 encoder，将 GUI 轨迹编码为固定长度 continuous embeddings
  - 插入 backbone input layer，减少 context length
  - 比 text memory 好：text memory 在长 prompt 下性能下降，continuous memory 单调提升
  - Auto-scaling data flywheel: 自动发现环境 → 合成任务 → 收集轨迹 → 验证（100k+ 轨迹，~$4000）
  - Qwen-2.5-VL-7B + memory ≈ GPT-4o / Claude-4
- **与我们的关系**: ⭐⭐
  - 都是"从交互中学习"，但方法完全不同
  - 他们: embedding space, fine-tune LoRA (Q-Former, 1.2% params)
  - 我们: 结构化文本 + 图像片段，纯 prompt-based，可解释

---

## KV Cache / Context 效率

### GUI-KV — KV Cache with Spatio-Temporal Awareness
- **Paper**: arXiv (2025.10)
- **Authors**: Kung-Hsiang Huang, Haoyi Qiu et al. (Salesforce)
- **核心思路**: 利用 GUI 的时空特性压缩 KV cache，提升长任务效率
- **与我们的关系**: ⭐ 间接相关，解决长任务 context 问题

### Efficient Long-Horizon GUI Agents via Training-Free KV Cache Compression
- **Paper**: arXiv (2026.02)
- **Authors**: Bowen Zhou, Zhou Xu et al.
- **核心思路**: 无需训练的 KV cache 压缩
- **与我们的关系**: ⭐ 间接相关

---

## 规划与回溯

### PAL-UI — Planning with Active Look-back for Vision-Based GUI Agents
- **Paper**: arXiv (2025.09-10)
- **Authors**: Zikang Liu, Junyi Li, Wayne Xin Zhao et al.
- **核心思路**: 主动回看历史截图来辅助规划
- **与我们的关系**: ⭐⭐ 也利用历史视觉信息，但以规划为目的而非记忆

---

## 主动推荐

### PIRA-Bench — From Reactive GUI Agents to Proactive Intent Recommendation
- **Paper**: arXiv (2026.03)
- **Authors**: Yuxiang Chai, Shunye Tang et al.
- **核心思路**: 不只是被动执行，还主动推荐用户可能的意图
- **与我们的关系**: ⭐ 方向互补

---

## 我们的定位

| 维度 | 我们 (gui-memory) | MAGNET | Auto-scaling CM |
|------|-------------------|--------|-----------------|
| 记忆形式 | 结构化文本 + 裁剪图像 | element patch + semantics | continuous embeddings |
| 训练需求 | 无 (prompt-based) | automated pipeline | LoRA fine-tune |
| 跨 session | ✅ (文件持久化) | ✅ (memory store) | ✅ (embedding store) |
| 可解释性 | ✅ 高 (人可读) | 中 | ❌ 低 (embedding) |
| 平台 | macOS / Linux desktop | Android mobile | Web + Android |
| 核心场景 | 学习 app → 加速后续操作 | 适应 UI 版本更新 | 泛化到新环境 |
| 组件级视觉存储 | ✅ crop + label | ✅ patch + semantics | ❌ 轨迹级 |

**独特卖点**: 纯 prompt-based + 可解释 + 组件级视觉记忆 + desktop 平台，无需额外训练。

---

*Last updated: 2026-03-30*
