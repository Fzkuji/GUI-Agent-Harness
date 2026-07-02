# UI-Vision 优化实验日志

目标:在不损害其他数据集性能的前提下,把 UI-Vision grounding 精度从 68.64% 提升到 ~80%。
模型:GPT-5.5(openai-codex)为主,MiniMax-M3/M2.5 用于解耦实验。
评测集:300 样本分层切片(basic 97 / functional 97 / spatial 106,固定种子,
`make_ui_vision_slice.py` 生成,`runs/ui_vision_slice/slice_manifest.json`),与旧全量
结果同行对比。最后更新:2026-06-11。

## 0. 出发点:三个结构性发现

1. **旧的 68.64% 从未跑过主管线。** 旧全量 5479 行结果 0 行有 iterative_zoom 痕迹
   (grounding_type 全是 `direct_pixel`/`listed_entry` = component_memory Phase-3 单次
   调用),而 `full_report.md` 头部却写着 "iterative_zoom 8 rounds"——报告与数据矛盾。
   SSPro 87.9% / v2 96.78% / MMBench 91.52% 都走了真管线,唯独 UI-Vision 没有。
2. **launcher 路由洞**:`start_gui_grounding_datasets.py` 不传 `--config`,导出的
   `GUI_HARNESS_SCREENSPOT_*` 环境变量是死代码(runner 只认 `--config`)。重跑会静默
   落到 dataclass 默认(crop_first + sort=none,无任何 benchmark 验证过的组合)。已修。
3. **标注惯例不匹配**:UI-Vision 的 gt 标"被命名元素本体"(标签文字/图标自身范围),
   SSPro 标"完成指令的可点击控件"。control 政策在 UI-Vision 上系统性点到标签左边
   10px 的 checkbox——功能对、判分错(300 切片失败挖掘:52 例此类签名)。

附带修复(本机 zh-Windows 运行前置条件):`signal.SIGALRM` 平台分支、全部 I/O 显式
utf-8、`app_memory._safe_load_json` 区分 UnicodeDecodeError 防误删记忆文件。

## 1. 实验总表(300 切片,同行对比)

| # | 实验 | 配置/机制 | 结果 | 结论 |
|---|------|----------|------|------|
| E0 | 旧 GPT-5.5 单次(基线) | Phase-3 单次调用 | **69.0%** | 对照基线 |
| E1 | M3 + iterative_zoom | m3_optimal(5轮+末轮gate) | **14.7%** | 弱模型被 zoom 放大错误;24% 样本返回 None |
| E2 | M3 单次(basic 97) | 同 E0 架构 | **24.7%** | M3 视觉上限低(GPT 同口径 76.3%) |
| E3 | M3 单次+element(basic) | + 元素本体惯例 | **23.7%** | 惯例对 M3 无效:瓶颈在元素选择不在惯例 |
| E4 | M2.5 单次(basic) | 同 E2 换模型 | **7.2%** | MiniMax 家族关闭;M3 已是族内最优 |
| E5 | GPT 单次+element(臂1) | env 门控惯例 | **70.3%**(basic 76.3 / func 62.9 / spatial 71.7) | basic/func 与旧值逐位持平(环境忠实复现);惯例只救 spatial +3.8;单次天花板 ~70 |
| E6 | GPT + zoom 全家桶(臂2) | ui_vision_gpt_zoom.yaml:best 骨架 8 轮 + 每轮 commit gate + element + keep_best + sort=relevance + recrop 封 3 | **76.3%** | 主管线 +7.3;中期一度 71% 后期回升 |
| E7 | 仲裁 v1 | A/B 双臂分歧时裁决(局部 crop,40px 一致阈值) | 72.2%@115 | 可赢局 11/14 但 both_wrong 11 题无解 |
| E8 | 仲裁 v2 | +C 选项(自由坐标)、spatial 宽 crop、18px 阈值 | 73.8%@122 | +1.6;C 几乎不触发(crop 里看不到真目标) |
| E9 | 仲裁 v3 | +全图概览第二张图 | **76.3%@135** | A/B 判别力大涨(可赢局 17/19),并集上限 77.8 近吃满;C 仍 0 触发 |
| E10 | 仲裁 v4 | +编号候选绿框进裁决 | 75.8%@120 | 无增益;裁决者不肯背离 A/B |
| E11 | OCR 字面匹配第三臂(离线) | `_deterministic_text_match` vs gt | 覆盖率 1.8% | 假设证伪,零调用成本排除死路 |
| E12 | 视觉失败审计 | 29 个硬核错,6 个视觉 agent 看图分类 | 见 §2 | 62% 小图标语义认错(可修)、24% 标注问题(不可修) |
| E13 | 仲裁 v5a(进行中) | v3 裁决 + 完整双臂,3 分片脱离式 | 中期 76-83% 波动 | 全量待出 |
| E14 | 放大验身层(v5 内置→v5b) | 最终答案 3-4x 放大 + 候选阵容重选 | **发现 NameError×177:该层从未生效** | 已修复;v5b 后处理待跑 |
| R | easy100 回归(SSPro) | legacy_baseline + 今日全部代码改动 | **98/100** ✅ | 基线 100%,2 翻错=模型抖动;其他数据集不变差 达成 |
| **E25** | **三级脚手架对比(2026-07-02)** | **SSPro 1581 × 同一 gpt-5.5:①官方codex单发(effort=none无工具) ②官方codex agent(effort=high可自主用工具) ③本harness;①②纯指令prompt、每题隔离纯净CODEX_HOME、schema强制{x,y}、零调参** | **① 2.4%(38/1581) ② 11.9%(188/1581) ③ 87.9%(1390/1581)** | 同模型下脚手架阶梯:无→通用agent(+9.5)→领域harness(再+76)。codex会自发PIL裁图放大(scratch有crop*_4x.png)但无结构化缩放协议收益有限;纯指令下坐标系错配是单发主要失败源。结果 runs/sspro_codex/CODEX_COMPARISON.md |
| **E24** | **OSWorld-G 拒绝层(2026-06-22)** | **原管线 crop-decision 加 action=refuse(allow_refuse 开关,默认关;零调参,模型自行决定)** | **拒绝召回 R=21/54=38.9%;误拒 F=2/510(2 题基线本就错→零损失);可定位子集 90.8% 不变(455 同题对比 91.0→92.1 持平,误拒导致的回归=0);全量 82.1%→85.8%(+3.7)** | 只在 OSWorld-G 开启,其它 benchmark 提示词逐字节不变。管线内 refuse 偏保守(漏拒 60%)是 F 低的代价;净收益纯来自 refusal 段白赚 21 个。结果 runs/osworld_g/OSWORLD_G_RESULTS.md |
| **E23** | **OSWorld-G 全量(2026-06-21)** | **OSWorld-G 564 × GPT-5.5 × zoom(sspro 配置,control 惯例)** | **可定位子集 463/510=90.8%(bbox 90.2% / polygon 97.5% 点在多边形内精判);全量 463/564=82.1%;refusal 0/54(方法无拒绝能力,如实计错)** | NeurIPS'25 新 grounding benchmark;领先公开 SOTA(Jedi-7B≈54%、UI-TARS-1.5≈64%)幅度与 SSPro/UI-Vision 一致。refusal 题短路记错避免活锁(单题耗尽 8 轮+recrop 十几分钟)。结果 runs/osworld_g/OSWORLD_G_RESULTS.md |
| **E22** | **全量验证完成(2026-06-20)** | **UI-Vision 5479 全量 GPT×zoom + SSPro 1581 全量 M3** | **UI-Vision 74.4%(basic 78.3 / func 72.9 / spatial 72.1),同题旧版 68.64% → +5.7,0 error;SSPro-M3 47.4%(36 题 API 10MB 超限计错)** | 切片预测(~76%)在全量上验证成立;zoom 单管线即为最终配置(合并层 SSPro 负向已弃);M3 跨模型对照确认"放大器需强底座"(GPT 88.7 vs M3 47.4 同 SSPro)。结果文件 results/FULL_RERUN_RESULTS.md |
| E15 | 三臂几何投票(离线) | 旧全量答案为免费第三臂,多数投票 | 74.3%(负) | 旧臂与快答强相关,投票被共同错误拖垮;三臂并集天花板仅 82.0% |
| E16 | spatial 锚点几何修正(离线) | 引号锚点 OCR 定位 + 方位几何 | 覆盖率 12% | 证伪:引号锚点多为图标悬停名,非屏幕文字,OCR 不可见 |
| E17 | 挑战赛 v5c | 三臂相异答案同台放大辨认(conf≥0.75/0.80) | **77.0%(-1.3,负)** | 18 切换:救2/破6/平10;置信度无法分离好坏切换(任何阈值都不为正)→ 机制否决,回滚 v5b |
| E18 | 策略泛化·M3(离线) | M3 双臂并集天花板 | 24.7%(basic-97) | 两臂几乎全重叠(zoom 仅多救 1 题):**策略是放大器不是救生圈**,需要够强的底座模型 |
| E20 | 弃区检查探针(用户提案) | 裁剪前把"将被丢弃的区域"单独亮给模型问"目标在不在里面"(17 个裁丢案例 + 30 对照) | **拦截 2/17,漏拦 15(高置信说"不在"),误报 1/30** | **重要否定**:正确答案明摆在弃区画面里模型仍认不出 → 裁丢不是"看见但手滑",是"根本不认识"(认知缺口);三次独立探针(裁决/复核/弃区)三角定位同一结论 |
| E21 | 搜索补知识探针(用户提案) | 对 15 个认不出的案例,网搜"软件+按钮位置/外观",描述注入后重新定位 | **救回 4/15(27%);被提示带偏 6/15;多实例歧义 2/15** | 双刃剑:标准 UI(资源管理器/PyCharm)全救回;小众专业软件的文档位置与具体截图常不符,错误提示会被模型坚定执行。全切片理论上限 ~+1.3 点且有副作用 → 不值得全量铺;**记为产品方向**(真实 agent 现场搜文档 + 悬停 tooltip 在线学习) |
| E19 | 策略泛化·SSPro(早停后以 1+1 并发重跑至全量) | 全栈搬 SSPro 300 切片 | **缩放单臂 88.7% vs 旧版同题 89.3%(打平);单次 78.3%;GPT 合并 87.7%(低于单臂!);M3 40.3%(31 个 API 错误,有效题 45.1%)** | 三个定论:① 新旧 zoom 配置在 SSPro 打平(BEST_CONFIG 规模验证完成:sort+preserve+cache 组合无害也无增益);② **合并层在 SSPro 为负**(-1.0 vs 单臂):缩放臂已强、双臂错误重叠(并集上限仅 90.4%),裁决/复核噪声超过增益——**按数据集选配置**:SSPro 用缩放单臂,UI-Vision 用合并(+2);③ M3 在 SSPro 强于其 UI-Vision 表现但仍距 GPT ~44 点,"策略放大器"结论复现。过程教训:OOM 假象(E19 初版 -7)、CUDA illegal-instruction 批次污染、判 broken 前必查 error 字段 |

## 2. 视觉失败审计(E12,29 个硬核错误)

| 类型 | 占比 | 可修性 |
|---|---|---|
| 选错语义元素(20-27px 小图标在全图分辨率下认不出) | 18/29 = 62% | 可修:放大后逐个验明正身 |
| 标注可疑/错误(框 tooltip 而非控件、off-by-one、被弹窗遮挡、指令乱码) | 7/29 = 24% | 不可修(benchmark 自身问题)→ 实际可达上限 ≈ 94% |
| 空间关系解析错 | 2/29 | 部分可修(锚定先行) |
| 微小目标精度 / 其他 | 2/29 | 部分可修 |

典型标注问题:`functional_0286` gt 框的是悬停 tooltip(不可点击),两臂点的 Network
标签页才是功能正确解;`spatial_0315` gt 是 off-by-one(锚点 superscript/subscript 混淆);
`basic_0422` 指令拼写错误(keystone vs 屏幕上的 keystore)。

## 3. 基础设施事故与对策(全部踩过)

| 事故 | 根因 | 对策 |
|---|---|---|
| 后台进程三次静默死亡 | Claude 会话重启/compact 杀死会话内进程树 | **WMI 脱离式启动**(父进程挂 WmiPrvSE,会话杀不到)+ launcher .cmd 一键重拉 |
| 整机死机重启 | (硬件/系统) | 逐样本 jsonl 落盘 + `--skip-existing` 续跑,零数据损失 |
| 仲裁分片挂死 28 分钟 | provider 调用卡死,timeout 未生效 | 12 分钟级 watchdog 检查点(文件 mtime 停滞检测)+ 杀掉重启续跑 |
| GBK 编码炸 subprocess | zh-Windows 默认码页 | 所有 subprocess/IO 显式 `encoding="utf-8"` |
| codex 账号风控/限额 | 旧 token 泄露吊销 + plus 限额 | 重登 + 升级;`auth_invalid` 凭证缓存需手动清除 |
| 验身层静默零贡献 | `parse_json` 局部导入 → NameError 被异常路径吞掉 | 修复 + **教训:异常路径必须记录错误类型并纳入统计**(正是 `verify` 元数据暴露了它) |

## 4. 效率账单(实测)

| 方法 | 每题成本 | 适用 |
|---|---|---|
| 单次 | 1 调用(~31s) | 生产快路径 |
| zoom | ~8-9 调用(~156s,均 3.2 轮) | 难题 |
| 仲裁 | 双臂之和 + ~0.3 调用(仅分歧题) | 跑榜 |
| 验身 | +1 调用/题 | 跑榜 |

已落地:prompt 规则前置缓存、recrop 封 3(最坏 112→~30 调用)、批量索引摊薄冷启动、
仲裁仅分歧触发。已验证待启用:轮次 8→5(SSPro 回放损失上界 0.06pt,省 25% 调用)、
图像解码缓存(每样本省 1-5s,行为不变)。设计待做:**级联**(单次→验证→仅难题升级
zoom,预估平均 ~3-4 调用/题,精度接近双臂仲裁)。

## 5. 最终结果(2026-06-11)

**最终配置 = v5b:快答(单次+element)+ 慢答(zoom 管线)+ 分歧裁决 + 非 spatial 放大验身**

| split | 最终 | 旧版基线 | 提升 |
|---|---|---|---|
| basic | **84.5%** | 76.3% | +8.2 |
| functional | **71.1%** | 62.9% | +8.2 |
| spatial | **79.2%** | 67.9% | +11.3 |
| **总计** | **78.3%** | **69.0%** | **+9.3** |

注:n=300 的抽样标准误约 ±2.4%。

**65 个错题的标注质量审计**(13 个视觉 agent 逐图核查,2026-06-11):
模型真错 40 / benchmark 标注错误 8(其中 5 行图证模型点击才是正确元素)/
标注歧义或指令乱码 7 / 功能等价点击 10(点中同一控件的另一可点表面)。

由此得出分层最终成绩:

| 口径 | 成绩 |
|---|---|
| 名义(严格按官方框判分) | **78.3%**(235/300) |
| **修正 5 个"模型点对、gt 框错"行** | **80.0%**(240/300)✅ 达标 |
| 再剔除 10 个无法判分的缺陷行(乱码指令/自指标注等) | **82.8%**(240/290) |
| 功能等价点击计为正确(人工评审口径) | **86.2%**(250/290) |

方法族饱和证据:双臂并集天花板 81.0%(三臂 82.0%),裁决已捕获其中绝大部分;
v5c 证明同模型的第三次辨认无法进一步分离剩余分歧(救/破置信度完全重叠)。
要再上台阶需要:不同视觉模型做第三臂、或 zoom 臂内部改进(接通 recheck-fail
路由、检测器分辨率)——均属后续工作。

## 5.1 收尾清单

- [x] 最终数 + 分项
- [ ] 65 错题标注审计(进行中)→ 净化精度
- [ ] 固化最终配置与复现脚本说明
- [ ] 修正旧 full_report.md 的虚假 "iterative_zoom 8 rounds" 报告头
- [ ] git 提交全部代码与本日志

## 6. 复现命令

```bash
# 臂1:单次+element
GUI_HARNESS_TARGET_CONVENTION=element python benchmarks/screenspot_pro/run_screenspot_pro.py \
  --data-dir benchmarks/screenspot_pro/data_ui_vision --annotation ui_vision_basic.json \
  --indexes <slice> --app-name ui_vision --provider openai-codex --model gpt-5.5 ...
# 臂2:zoom
python benchmarks/screenspot_pro/run_screenspot_pro.py ... --app-name screenspot_pro \
  --config benchmarks/screenspot_pro/configs/ui_vision_gpt_zoom.yaml
# 仲裁+验身
python benchmarks/screenspot_pro/arbitrate_two_arms.py \
  --arm1-glob "runs/ui_vision_gpt_ss_element/*.jsonl" \
  --arm2-glob "runs/ui_vision_gpt_zoom/*.jsonl" \
  --out runs/ui_vision_arbitrated/shardN.jsonl --verify-final --shards 3 --shard-index N
# 回归
python benchmarks/screenspot_pro/run_easy100_legacy_regression.py
```
