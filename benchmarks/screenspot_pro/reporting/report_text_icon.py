#!/usr/bin/env python3
"""ScreenSpot-Pro standard text/icon x subset breakdown for all our results.

Emits the canonical SSPro table (each subset split into Text / Icon columns,
plus Average Text / Icon / Overall). Groups come from the official annotation
mapping; ui_type ('text'|'icon') from each result row. Writes Markdown to
results/TEXT_ICON_BREAKDOWN.md.
"""
from __future__ import annotations
import json, glob
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
REPO = HERE.parents[1]
ORDER = ["CAD", "Dev", "Creative", "Scientific", "Office", "OS"]
APP2G = {
    "android_studio_macos": "Dev", "pycharm_macos": "Dev", "quartus_windows": "Dev",
    "vmware_macos": "Dev", "vscode_macos": "Dev",
    "blender_windows": "Creative", "davinci_macos": "Creative", "fruitloops_windows": "Creative",
    "illustrator_windows": "Creative", "photoshop_windows": "Creative", "premiere_windows": "Creative",
    "unreal_engine_windows": "Creative",
    "autocad_windows": "CAD", "inventor_windows": "CAD", "solidworks_windows": "CAD", "vivado_windows": "CAD",
    "eviews_windows": "Scientific", "matlab_macos": "Scientific", "origin_windows": "Scientific",
    "stata_windows": "Scientific",
    "excel_macos": "Office", "powerpoint_windows": "Office", "word_macos": "Office",
    "linux_common_linux": "OS", "macos_common_macos": "OS", "windows_common_windows": "OS",
}


def load(pats):
    d = {}
    for pat in pats:
        for p in glob.glob(str(REPO / pat)):
            for l in open(p, encoding="utf-8"):
                if not l.strip():
                    continue
                try:
                    r = json.loads(l)
                except Exception:
                    continue
                if r.get("sample_id"):
                    d[r["sample_id"]] = r
    return d


def breakdown(d):
    """Return {group: {'text':(c,n),'icon':(c,n)}} + overall text/icon."""
    g = {k: {"text": [0, 0], "icon": [0, 0]} for k in ORDER}
    for sid, r in d.items():
        grp = APP2G.get(sid.rsplit("_", 1)[0])
        ut = r.get("ui_type")
        if grp is None or ut not in ("text", "icon"):
            continue
        cell = g[grp][ut]
        cell[1] += 1
        cell[0] += r.get("correctness") == "correct"
    return g


def pct(c, n):
    return f"{100*c/n:.1f}" if n else "--"


RESULTS = [
    ("GPT-5.5 · harness", 1581, ["benchmarks/screenspot_pro/results/gpt_5_5/results.jsonl"]),
    ("GPT-5.5 · single-shot", 1581, ["runs/sspro_singleshot/results_s*.jsonl", "runs/sspro_singleshot/results.jsonl"]),
    ("Claude 4.7 · harness", 1581, ["benchmarks/screenspot_pro/results/claude_opus_4_7/results.jsonl"]),
    ("Claude 4.7 · single-shot", 1581, ["runs/sspro_native/claude-opus-4-7/results.jsonl"]),
    ("MiniMax-M3 · harness", 1581, ["runs/sspro_stack/m3_zoom/*.jsonl"]),
    ("MiniMax-M3 · single-shot", 1581, ["runs/sspro_native/MiniMax-M3/results.jsonl"]),
]


def main():
    lines = []
    lines.append("# ScreenSpot-Pro — Text / Icon breakdown by subset\n")
    lines.append("Each subset split into **Text** and **Icon** click targets (SSPro's standard\n"
                 "format). Groups from the official annotation mapping; `ui_type` per result row.\n"
                 "Scale column notes full-1581 vs 300-slice.\n")
    # header
    head = "| Model | Scale |"
    sub = "|---|---|"
    for g in ORDER:
        head += f" {g} T | {g} I |"
        sub += "---|---|"
    head += " Avg T | Avg I | **Avg** |"
    sub += "---|---|---|"
    lines.append(head)
    lines.append(sub)

    for name, scale, pats in RESULTS:
        d = load(pats)
        g = breakdown(d)
        tt = sum(g[k]["text"][0] for k in ORDER); tn = sum(g[k]["text"][1] for k in ORDER)
        it = sum(g[k]["icon"][0] for k in ORDER); ino = sum(g[k]["icon"][1] for k in ORDER)
        row = f"| {name} | {scale} |"
        for k in ORDER:
            ct, nt = g[k]["text"]; ci, ni = g[k]["icon"]
            row += f" {pct(ct,nt)} | {pct(ci,ni)} |"
        overall = pct(tt+it, tn+ino)
        row += f" {pct(tt,tn)} | {pct(it,ino)} | **{overall}** |"
        lines.append(row)

    # also emit the stark text-vs-icon gap summary
    lines.append("\n## Text vs Icon gap (overall)\n")
    lines.append("| Model | Text | Icon | Gap (T−I) |")
    lines.append("|---|---|---|---|")
    for name, scale, pats in RESULTS:
        d = load(pats)
        g = breakdown(d)
        tt = sum(g[k]["text"][0] for k in ORDER); tn = sum(g[k]["text"][1] for k in ORDER)
        it = sum(g[k]["icon"][0] for k in ORDER); ino = sum(g[k]["icon"][1] for k in ORDER)
        t = 100*tt/tn if tn else 0; i = 100*it/ino if ino else 0
        lines.append(f"| {name} | {t:.1f} | {i:.1f} | **{t-i:+.1f}** |")

    lines.append("\n## Key findings\n")
    lines.append(
        "- **Icon is universally harder than text** — every model, every pipeline. "
        "Icons carry no OCR-readable label, so grounding must be purely visual.\n"
        "- **The text/icon gap tracks visual grounding strength.** GPT harness is the "
        "most balanced (icon 77.8); M3 has the widest gap by far (harness text 66.8 vs "
        "icon **15.9**, +50.9) — M3 can localize text but is nearly blind to icons.\n"
        "- **Harness lifts icons much more than text**, because zoom is what makes a "
        "small icon legible: e.g. Claude icon 38.9 (single) → 68.9 (harness), +30.0; "
        "GPT icon 63.4 → 77.8. But M3's icon barely moves (9.4 → 15.9): magnification "
        "alone can't fix a model that doesn't visually parse icons — its ceiling is low.\n"
        "- **Claude single-shot icon is only 38.9%** — the CC-protocol 2000px downscale "
        "blurs small icons; harness zoom recovers most of it (→68.9). This is the same "
        "resolution-bottleneck story as the ablation's −adaptive column.\n"
        "- Caveat: per-subset text/icon cells have small n (e.g. OS ~25 each); the "
        "overall Text/Icon columns are the robust numbers.\n")

    out = HERE / "results" / "TEXT_ICON_BREAKDOWN.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n-> wrote {out}")


if __name__ == "__main__":
    main()
