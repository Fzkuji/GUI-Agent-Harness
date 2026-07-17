# ScreenSpot-Pro — Text / Icon breakdown by subset

Each subset split into **Text** and **Icon** click targets (SSPro's standard
format). Groups from the official annotation mapping; `ui_type` per result row.
Scale column notes full-1581 vs 300-slice.

| Model | Scale | CAD T | CAD I | Dev T | Dev I | Creative T | Creative I | Scientific T | Scientific I | Office T | Office I | OS T | OS I | Avg T | Avg I | **Avg** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT-5.5 · harness | 1581 | 90.9 | 71.9 | 95.5 | 78.6 | 92.9 | 74.8 | 93.8 | 72.7 | 98.3 | 88.7 | 94.4 | 85.4 | 94.2 | 77.8 | **87.9** |
| GPT-5.5 · single-shot | 1581 | 84.3 | 70.3 | 72.7 | 53.1 | 80.8 | 66.4 | 91.7 | 60.9 | 89.8 | 81.1 | 65.4 | 62.9 | 81.8 | 63.4 | **74.8** |
| Claude 4.7 · harness | 1581 | 85.3 | 68.8 | 94.2 | 69.0 | 89.9 | 69.2 | 91.0 | 61.8 | 95.5 | 88.7 | 87.9 | 65.2 | 90.6 | 68.9 | **82.3** |
| Claude 4.7 · single-shot | 1581 | 36.5 | 20.3 | 84.4 | 45.5 | 77.3 | 35.7 | 81.9 | 43.6 | 75.1 | 47.2 | 61.7 | 36.0 | 68.8 | 38.9 | **57.4** |
| MiniMax-M3 · harness | 1581 | 57.4 | 9.4 | 71.4 | 11.0 | 64.6 | 13.3 | 68.1 | 21.8 | 76.3 | 22.6 | 64.5 | 21.3 | 66.8 | 15.9 | **47.4** |
| MiniMax-M3 · single-shot | 1581 | 19.8 | 7.8 | 42.2 | 6.2 | 36.4 | 8.4 | 54.2 | 15.5 | 44.1 | 17.0 | 27.1 | 5.6 | 36.9 | 9.4 | **26.4** |

## Text vs Icon gap (overall)

| Model | Text | Icon | Gap (T−I) |
|---|---|---|---|
| GPT-5.5 · harness | 94.2 | 77.8 | **+16.4** |
| GPT-5.5 · single-shot | 81.8 | 63.4 | **+18.4** |
| Claude 4.7 · harness | 90.6 | 68.9 | **+21.7** |
| Claude 4.7 · single-shot | 68.8 | 38.9 | **+29.9** |
| MiniMax-M3 · harness | 66.8 | 15.9 | **+50.9** |
| MiniMax-M3 · single-shot | 36.9 | 9.4 | **+27.5** |

## Key findings

- **Icon is universally harder than text** — every model, every pipeline. Icons carry no OCR-readable label, so grounding must be purely visual.
- **The text/icon gap tracks visual grounding strength.** GPT harness is the most balanced (icon 77.8); M3 has the widest gap by far (harness text 66.8 vs icon **15.9**, +50.9) — M3 can localize text but is nearly blind to icons.
- **Harness lifts icons much more than text**, because zoom is what makes a small icon legible: e.g. Claude icon 38.9 (single) → 68.9 (harness), +30.0; GPT icon 63.4 → 77.8. But M3's icon barely moves (9.4 → 15.9): magnification alone can't fix a model that doesn't visually parse icons — its ceiling is low.
- **Claude single-shot icon is only 38.9%** — the CC-protocol 2000px downscale blurs small icons; harness zoom recovers most of it (→68.9). This is the same resolution-bottleneck story as the ablation's −adaptive column.
- Caveat: per-subset text/icon cells have small n (e.g. OS ~25 each); the overall Text/Icon columns are the robust numbers.

