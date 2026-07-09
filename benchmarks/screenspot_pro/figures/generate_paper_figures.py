#!/usr/bin/env python3
"""生成两张论文用 draw.io 图(diagrams.net 可直接打开编辑):
  runs/figures/fig_comparison.drawio  — 与其他方法的精度对比(分组柱状图)
  runs/figures/fig_pipeline.drawio    — best 策略(iterative-zoom)实现细节流程图

对比数据来源(2026-06 公开文献,见脚本末注释)。我方数字可在跑完后改 OURS 字典重生成。
用法: python generate_paper_figures.py
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
OUT = REPO / "runs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
EX = OUT / "example"


def b64img(path):
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def img_cell(cid, path, x, y, w, h):
    data = b64img(path)
    style = (f"shape=image;html=1;verticalAlign=top;imageAspect=0;aspect=fixed;"
             f"image=data:image/png,{data};strokeColor=#c5cee0;")
    return (f'<mxCell id="{cid}" value="" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')

# ─────────────────────────────────────────────────────────────────────────
# 数据(精度 %)。其他方法为公开文献报告值;Ours = 本工作(GPT-5.5 + iterative zoom)。
# ─────────────────────────────────────────────────────────────────────────
SSPRO = [  # ScreenSpot-Pro (full, 1581)
    ("UGround-7B", 16.5, False),
    ("OS-Atlas-7B", 18.9, False),
    ("UGround-72B", 34.5, False),
    ("UI-TARS-72B", 38.1, False),
    ("Qwen2.5-VL-72B", 43.6, False),
    ("Qwen2.5-VL-72B-Inst", 53.3, False),
    ("RegionFocus", 61.6, False),
    ("UI-Venus-72B", 61.9, False),
    ("Ours (GPT-5.5+zoom)", 88.7, True),
]
UIVISION = [  # UI-Vision (full, 5479)
    ("Qwen2.5-VL", 0.9, False),
    ("UI-TARS-7B", 17.6, False),
    ("UI-TARS-72B", 25.5, False),
    ("Ours single-shot", 68.6, False),
    ("Ours (GPT-5.5+zoom)", 76.0, True),  # 全量跑完后改为最终数
]

BLUE = "#2d6cdf"
GREY = "#9aa7bd"
DARK = "#1f2a44"
LIGHT = "#eef3fb"


def cell(cid, value, style, x, y, w, h, parent="1", vertex="1"):
    return (f'<mxCell id="{cid}" value="{escape(str(value))}" style="{style}" '
            f'vertex="{vertex}" parent="{parent}">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def edge(cid, src, tgt, style="", value="", parent="1"):
    return (f'<mxCell id="{cid}" value="{escape(value)}" '
            f'style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;'
            f'strokeColor=#44506b;strokeWidth=1.6;{style}" edge="1" parent="{parent}" '
            f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>')


def wrap(inner, w, h):
    return ('<mxfile host="app.diagrams.net"><diagram name="figure" id="fig">'
            f'<mxGraphModel dx="{w}" dy="{h}" grid="0" gridSize="10" guides="1" '
            'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="{w}" pageHeight="{h}" math="0" shadow="0">'
            '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f'{inner}</root></mxGraphModel></diagram></mxfile>')


def slug(s):
    import re
    return re.sub(r"[^A-Za-z0-9]+", "_", str(s)).strip("_")[:24]


def bar_panel(title, data, x0, y0, panel_w, panel_h):
    """一个分组柱状面板。返回 xml 片段。"""
    tg = slug(title)
    out = []
    pad_l, pad_b, pad_t = 46, 70, 40
    plot_w = panel_w - pad_l - 20
    plot_h = panel_h - pad_b - pad_t
    n = len(data)
    gap = 14
    bw = (plot_w - gap * (n - 1)) / n
    base_y = y0 + pad_t + plot_h
    # 面板标题
    out.append(cell(f"t_{tg}", title,
                    f"text;html=1;fontSize=16;fontStyle=1;fontColor={DARK};align=center;",
                    x0, y0 + 6, panel_w, 24))
    # y 轴刻度线 0/25/50/75/100
    for v in (0, 25, 50, 75, 100):
        yy = base_y - v / 100.0 * plot_h
        out.append(cell(f"g_{tg}_{v}", "",
                        f"line;html=1;strokeColor=#dfe5ef;",
                        x0 + pad_l, yy, plot_w, 1))
        out.append(cell(f"gl_{tg}_{v}", v,
                        "text;html=1;fontSize=10;fontColor=#7a melt8;align=right;".replace(" melt8", "8a9a"),
                        x0 + 4, yy - 8, pad_l - 8, 16))
    # 柱
    for i, (name, acc, ours) in enumerate(data):
        bx = x0 + pad_l + i * (bw + gap)
        bh = acc / 100.0 * plot_h
        by = base_y - bh
        color = BLUE if ours else GREY
        stroke = "#1c4fb0" if ours else "#7f8ba3"
        fs = "fontStyle=1;" if ours else ""
        out.append(cell(f"b_{tg}_{i}", "",
                        f"rounded=1;arcSize=8;html=1;fillColor={color};strokeColor={stroke};",
                        bx, by, bw, bh))
        # 数值标签
        out.append(cell(f"v_{tg}_{i}", f"{acc:.1f}",
                        f"text;html=1;fontSize=11;{fs}fontColor={DARK};align=center;",
                        bx - 4, by - 18, bw + 8, 16))
        # 方法名(竖排在底部)
        out.append(cell(f"n_{tg}_{i}", name,
                        f"text;html=1;fontSize=10;{fs}fontColor={'#1c4fb0' if ours else '#5a6680'};"
                        f"align=center;verticalAlign=top;horizontal=0;",
                        bx - 12, base_y + 6, bw + 24, pad_b - 10))
    # 坐标轴线
    out.append(cell(f"ax_{tg}", "", f"line;html=1;strokeColor={DARK};",
                    x0 + pad_l, base_y, plot_w, 1))
    return "".join(out)


def make_comparison():
    W, H = 1180, 560
    inner = []
    inner.append(cell("title", "GUI Element Grounding Accuracy: Ours vs. Published Methods",
                      f"text;html=1;fontSize=19;fontStyle=1;fontColor={DARK};align=center;",
                      0, 14, W, 30))
    inner.append(bar_panel("ScreenSpot-Pro (1,581, 4K professional apps)", SSPRO, 20, 60, 720, 460))
    inner.append(bar_panel("UI-Vision (5,479)", UIVISION, 760, 60, 400, 460))
    # 图例
    inner.append(cell("lg1", "", f"rounded=1;html=1;fillColor={BLUE};strokeColor=#1c4fb0;", 470, 524, 18, 14))
    inner.append(cell("lg1t", "Ours (GPT-5.5 + iterative zoom)",
                      f"text;html=1;fontSize=11;fontColor={DARK};align=left;", 492, 522, 230, 18))
    inner.append(cell("lg2", "", f"rounded=1;html=1;fillColor={GREY};strokeColor=#7f8ba3;", 720, 524, 18, 14))
    inner.append(cell("lg2t", "Published single-model / test-time-scaling methods",
                      f"text;html=1;fontSize=11;fontColor={DARK};align=left;", 742, 522, 330, 18))
    (OUT / "fig_comparison.drawio").write_text(wrap("".join(inner), W, H), encoding="utf-8")
    print(f"written {OUT/'fig_comparison.drawio'}")


# ─────────────────────────────────────────────────────────────────────────
# Pipeline 细节图
# ─────────────────────────────────────────────────────────────────────────
def box(cid, title, sub, x, y, w, h, fill, stroke, tfs=13):
    v = f"<b>{escape(title)}</b>"
    if sub:
        v += f"<br/><span style='font-size:10px;color:#43506b'>{escape(sub)}</span>"
    style = (f"rounded=1;arcSize=10;html=1;whiteSpace=wrap;fillColor={fill};"
             f"strokeColor={stroke};fontSize={tfs};fontColor={DARK};align=center;"
             "verticalAlign=middle;spacing=6;")
    # draw.io 把 HTML 标签以转义实体存储(html=1 时显示再渲染)
    return (f'<mxCell id="{cid}" value="{escape(v)}" style="{style}" vertex="1" parent="1">'
            f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')


def example_strip(y0):
    """读取 runs/figures/example/ 渲染的逐轮裁剪图,横排嵌入 + 轮次标注。"""
    meta = json.loads((EX / "meta.json").read_text(encoding="utf-8"))
    out = []
    out.append(cell("ex_title",
                    f"Worked example — instruction: “{meta['instruction']}”  "
                    f"(4K screen, target ≈ {meta['gt'][2]-meta['gt'][0]}×{meta['gt'][3]-meta['gt'][1]} px)",
                    f"text;html=1;fontSize=13;fontStyle=1;fontColor={DARK};align=left;", 60, y0, 1120, 22))
    caps = ["Full screen → locate the app window",
            "Round 1 → ribbon / color group",
            "Round 2 → Theme-Colours palette",
            "Final → click black swatch  ✓ (green = ground truth)"]
    PH = 168  # 显示高度
    x = 60
    n = meta["n_panels"]
    for i in range(n):
        pw = meta["panel_w"][i]
        dispw = int(pw * PH / 240)
        dispw = min(dispw, 270)  # 太宽的全屏图压一下
        out.append(img_cell(f"ex{i}", EX / f"round{i}.png", x, y0 + 30, dispw, PH))
        out.append(cell(f"exc{i}", caps[i] if i < len(caps) else f"round {i}",
                        "text;html=1;fontSize=10;fontColor=#43506b;align=center;whiteSpace=wrap;",
                        x - 6, y0 + 30 + PH + 4, dispw + 12, 34))
        if i < n - 1:
            out.append(cell(f"exa{i}", "→",
                            "text;html=1;fontSize=22;fontColor=#9aa7bd;align=center;",
                            x + dispw - 2, y0 + 30 + PH // 2 - 14, 26, 28))
        x += dispw + 26
    return "".join(out), x


def make_pipeline():
    W, H = 1240, 1010
    LLM = "#ffe6c7"      # LLM 调用(暖橙)
    LOC = "#d6efdd"      # 本地无 LLM(绿)
    GATE = "#fcd9de"     # 门控/兜底(红)
    IO = "#d8e6ff"       # 输入输出(蓝)
    e = []
    e.append(cell("titlebar", "", "rounded=0;html=1;fillColor=#1f2a44;strokeColor=none;", 0, 0, W, 52))
    e.append(cell("title", "Detection-guided Iterative-Zoom Grounding Pipeline",
                  "text;html=1;fontSize=20;fontStyle=1;fontColor=#ffffff;align=center;", 0, 12, W, 30))
    # 图例
    leg = [("LLM call (VLM)", LLM, "#e69138"), ("Local, no LLM", LOC, "#3aa657"),
           ("Gate / fallback", GATE, "#cc4d5e"), ("Input / Output", IO, "#3b6fd4")]
    lx = 60
    for i, (t, f, s) in enumerate(leg):
        e.append(cell(f"lg{i}", "", f"rounded=1;html=1;fillColor={f};strokeColor={s};", lx, 66, 16, 14))
        e.append(cell(f"lgt{i}", t, "text;html=1;fontSize=10;align=left;", lx + 20, 64, 150, 18))
        lx += 200

    # 节点
    e.append(box("inp", "Screenshot + Instruction", "e.g. 4K screen + “open layer settings”", 60, 92, 240, 56, IO, "#3b6fd4"))
    e.append(box("p1", "Phase 1 · Perception", "GPA-GUI-Detector (YOLO) + OCR → candidate elements (box+label)", 60, 180, 240, 64, LOC, "#3aa657"))
    e.append(box("rank", "Candidate ranking", "sort by relevance to instruction  (candidate_sort=relevance ★)", 60, 280, 240, 64, LOC, "#3aa657"))

    # 迭代缩放循环容器
    e.append(cell("loopbg", "Iterative Zoom  ·  up to N rounds (8→5 by data)",
                  "rounded=1;html=1;dashed=1;strokeColor=#9aa7bd;fillColor=#f7f9fd;"
                  "align=left;verticalAlign=top;fontSize=12;fontStyle=2;fontColor=#5a6680;"
                  "spacingLeft=10;spacingTop=6;",
                  360, 120, 540, 360))
    e.append(box("render", "Render current crop", "preserve scaling: upscale small targets (min short side 512)", 392, 156, 220, 56, LOC, "#3aa657"))
    e.append(box("crop", "Crop-decision  (VLM)", "see crop + candidate list → propose next smaller bbox, or “final”", 392, 244, 220, 64, LLM, "#e69138"))
    e.append(box("gate", "Commit-gate  (VLM)", "target still inside proposed crop?  reject → widen & retry (≤6)", 392, 340, 220, 64, LLM, "#e69138"))
    e.append(box("upd", "Update crop box", "shrink toward target; stop at min size or “final”", 648, 244, 220, 56, LOC, "#3aa657"))
    e.append(box("stage", "Staged guidance", "window → region → control group (anti over-crop)", 648, 156, 220, 56, LOC, "#3aa657"))

    # final 阶段
    e.append(box("frender", "Final crop (upscaled 8×)", "re-detect candidates inside final crop", 360, 520, 250, 56, LOC, "#3aa657"))
    e.append(box("fclick", "Final-click  (VLM)", "exact (x,y) or candidate_id on upscaled crop", 360, 612, 250, 60, LLM, "#e69138"))
    e.append(box("recheck", "Final-recheck  (VLM)", "compare vs wider view; replace if wrong", 660, 612, 240, 60, LLM, "#e69138"))
    e.append(box("kb", "keep_best fallback", "all gates fail → click centre of deepest crop\n(never abstain); final_recrop capped 3", 660, 520, 240, 64, GATE, "#cc4d5e"))
    e.append(box("out", "Click (x, y)", "", 960, 612, 200, 60, IO, "#3b6fd4"))

    # cache 注解
    e.append(cell("cache", "Prompt-cache: fixed rules hoisted to a cacheable prefix → only crop/candidates/round change per call",
                  "text;html=1;fontSize=10;fontStyle=2;fontColor=#5a6680;align=left;", 960, 156, 220, 120))

    # 边
    e.append(edge("e1", "inp", "p1"))
    e.append(edge("e2", "p1", "rank"))
    e.append(edge("e3", "rank", "render", "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"))
    e.append(edge("e4", "render", "crop"))
    e.append(edge("e5", "crop", "gate"))
    e.append(edge("e6", "gate", "upd", "value=accept;", "accept"))
    e.append(edge("e7", "upd", "render", "exitX=0.5;exitY=0;entryX=1;entryY=0.5;dashed=1;", "next round"))
    e.append(edge("e6b", "gate", "crop", "exitX=0;exitY=0.5;entryX=0;entryY=1;dashed=1;strokeColor=#cc4d5e;", "reject→widen"))
    e.append(edge("e8", "stage", "crop", "dashed=1;strokeColor=#9aa7bd;"))
    e.append(edge("e9", "crop", "frender", "exitX=0.5;exitY=1;entryX=0.3;entryY=0;value=final;", "“final”"))
    e.append(edge("e10", "frender", "fclick"))
    e.append(edge("e11", "fclick", "recheck"))
    e.append(edge("e12", "recheck", "out"))
    e.append(edge("e13", "kb", "out", "dashed=1;strokeColor=#cc4d5e;", "fallback"))
    e.append(edge("e14", "gate", "kb", "dashed=1;strokeColor=#cc4d5e;exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "exhausted"))

    # 分隔线 + 真实例子(逐轮裁剪)
    e.append(cell("divider", "", "line;html=1;strokeColor=#c5cee0;strokeWidth=1.5;", 40, 712, W - 80, 1))
    strip, _ = example_strip(732)
    e.append(strip)

    (OUT / "fig_pipeline.drawio").write_text(wrap("".join(e), W, H), encoding="utf-8")
    print(f"written {OUT/'fig_pipeline.drawio'}")


def make_paradigm():
    """范式对比图:四种 GUI grounding 方法论并排,凸显我方定位(非性能数字)。"""
    W, H = 1280, 720
    LLM = "#fde7cf"; LOC = "#dcefe0"; GATE = "#fadadd"; IO = "#dfe9ff"; OURS = "#dbe7ff"
    e = []
    e.append(cell("title", "Paradigms for GUI Element Grounding",
                  f"text;html=1;fontSize=20;fontStyle=1;fontColor={DARK};align=center;", 0, 12, W, 30))

    def node(cid, label, x, y, w, h, fill, stroke):
        return box(cid, label, "", x, y, w, h, fill, stroke, tfs=12)

    def lane(idx, name, methods, y, build, limitation, ours=False):
        rows = []
        band = OURS if ours else "#f6f8fc"
        bstroke = "#2d6cdf" if ours else "#e3e8f2"
        rows.append(cell(f"band{idx}", "",
                         f"rounded=1;html=1;fillColor={band};strokeColor={bstroke};"
                         + ("strokeWidth=2.5;" if ours else "strokeWidth=1;"),
                         24, y, W - 48, 132))
        tag = " ★ Ours" if ours else ""
        rows.append(cell(f"ln{idx}", f"<b>{escape(name)}</b>{tag}<br/>"
                         f"<span style='font-size:10px;color:#5a6680'>{escape(methods)}</span>",
                         "text;html=1;fontSize=13;align=left;verticalAlign=middle;"
                         f"fontColor={'#1c4fb0' if ours else DARK};spacingLeft=10;",
                         36, y + 12, 200, 108))
        rows.append(build(idx, 250, y + 26))
        rows.append(cell(f"lim{idx}", ("<b>Unifies all three:</b> " if ours else "<b>Limitation:</b> ") + limitation,
                         "text;html=1;fontSize=10;align=left;verticalAlign=middle;whiteSpace=wrap;"
                         f"fontColor={'#1c4fb0' if ours else '#8a3a44'};spacingLeft=8;",
                         W - 250, y + 16, 222, 100))
        return "".join(rows)

    def flow(*nodes_and_arrows):
        return "".join(nodes_and_arrows)

    # 1) Direct grounding
    def build1(i, x, y):
        return flow(
            node(f"a{i}1", "Full 4K image\n+ instruction", x, y, 110, 64, IO, "#3b6fd4"),
            node(f"a{i}2", "VLM", x + 150, y + 8, 70, 48, LLM, "#e69138"),
            node(f"a{i}3", "(x, y)", x + 260, y + 8, 70, 48, IO, "#3b6fd4"),
            edge(f"ea{i}1", f"a{i}1", f"a{i}2"), edge(f"ea{i}2", f"a{i}2", f"a{i}3"))
    e.append(lane(1, "Direct coordinate regression", "UGround · UI-TARS · Qwen2.5-VL · OS-Atlas",
                  60, build1, "image is down-sampled to the model's input size; tiny targets in high-res pro UIs become unreadable."))

    # 2) Detect then select
    def build2(i, x, y):
        return flow(
            node(f"b{i}1", "Image", x, y + 8, 70, 48, IO, "#3b6fd4"),
            node(f"b{i}2", "Detector\n→ candidate boxes", x + 110, y, 120, 64, LOC, "#3aa657"),
            node(f"b{i}3", "VLM\nselect one", x + 270, y + 8, 90, 48, LLM, "#e69138"),
            node(f"b{i}4", "(x, y)", x + 400, y + 8, 64, 48, IO, "#3b6fd4"),
            edge(f"eb{i}1", f"b{i}1", f"b{i}2"), edge(f"eb{i}2", f"b{i}2", f"b{i}3"),
            edge(f"eb{i}3", f"b{i}3", f"b{i}4"))
    e.append(lane(2, "Detect → select", "two-stage detector + chooser",
                  204, build2, "accuracy is capped by detector recall: if the element is never boxed, it can never be chosen."))

    # 3) Fixed-step zoom (one or two crops)
    def build3(i, x, y):
        return flow(
            node(f"c{i}1", "Image", x, y + 8, 60, 48, IO, "#3b6fd4"),
            node(f"c{i}2", "VLM\nzoom ×1", x + 95, y + 8, 70, 48, LLM, "#e69138"),
            node(f"c{i}3", "VLM\nzoom ×2", x + 195, y + 8, 70, 48, LLM, "#e69138"),
            node(f"c{i}5", "(x, y)", x + 295, y + 8, 60, 48, IO, "#3b6fd4"),
            edge(f"ec{i}1", f"c{i}1", f"c{i}2"), edge(f"ec{i}2", f"c{i}2", f"c{i}3"),
            edge(f"ec{i}4", f"c{i}3", f"c{i}5"),
            cell(f"c{i}note", "fixed depth (1–2 crops), no verify",
                 "text;html=1;fontSize=9;fontStyle=2;fontColor=#8a3a44;align=center;", x + 60, y + 60, 230, 16))
    e.append(lane(3, "Fixed-step zoom", "RegionFocus · GUI-Spotlight · Visual test-time scaling",
                  348, build3, "a fixed one- or two-step crop chosen blindly by the VLM; if the target is cropped out, there is no further round to recover it."))

    # 4) Ours
    def build4(i, x, y):
        s = []
        s.append(node(f"d{i}1", "Image", x, y + 20, 56, 44, IO, "#3b6fd4"))
        s.append(node(f"d{i}det", "Detector + OCR\ncandidates", x, y - 36, 110, 44, LOC, "#3aa657"))
        s.append(node(f"d{i}2", "VLM crop\n+ rank cand.", x + 110, y + 12, 96, 56, LLM, "#e69138"))
        s.append(node(f"d{i}3", "Commit-gate\nverify", x + 235, y + 12, 86, 56, GATE, "#cc4d5e"))
        s.append(node(f"d{i}4", "Final click\n+ recheck", x + 350, y + 12, 86, 56, LLM, "#e69138"))
        s.append(node(f"d{i}5", "(x, y)", x + 460, y + 18, 56, 44, IO, "#3b6fd4"))
        s.append(edge(f"ed{i}1", f"d{i}1", f"d{i}2"))
        s.append(edge(f"ed{i}det", f"d{i}det", f"d{i}2", "dashed=1;strokeColor=#3aa657;", "evidence"))
        s.append(edge(f"ed{i}2", f"d{i}2", f"d{i}3"))
        s.append(edge(f"ed{i}3", f"d{i}3", f"d{i}4", "", "accept"))
        s.append(edge(f"ed{i}r", f"d{i}3", f"d{i}2", "dashed=1;strokeColor=#cc4d5e;exitX=0.5;exitY=1;entryX=0.5;entryY=1;", "reject→widen"))
        s.append(edge(f"ed{i}4", f"d{i}4", f"d{i}5"))
        return "".join(s)
    e.append(lane(4, "Iterative zoom + verification", "this work (GPT-5.5 + best config)",
                  516, build4,
                  "truly iterative: adaptive number of rounds; detection evidence guides every crop; a commit-gate rejects crops that drop the target; keep_best never abstains.",
                  ours=True))

    (OUT / "fig_paradigm.drawio").write_text(wrap("".join(e), W, H), encoding="utf-8")
    print(f"written {OUT/'fig_paradigm.drawio'}")


if __name__ == "__main__":
    make_paradigm()       # 范式对比(主)
    make_comparison()     # 性能柱状图(备用)
    make_pipeline()       # 实现细节
    print("\n打开方式: diagrams.net (draw.io) → File → Open → 选择 .drawio 文件")

# ── 对比数据来源 ──
# ScreenSpot-Pro: UGround/OS-Atlas/UI-TARS/Qwen2.5-VL 报告值;RegionFocus 61.6、UI-Venus-72B 61.9。
# UI-Vision: Qwen2.5-VL 0.9、UI-TARS-7B 17.6、UI-TARS-72B 25.5(公开最高)。
# Ours: ScreenSpot-Pro 88.7(本机全量,GPT-5.5+zoom);UI-Vision 全量跑完后更新(切片 78.3 / 修正口径 80)。
