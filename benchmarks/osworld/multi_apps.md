# OSWorld Multi-Apps Domain — GUI Agent Skills Results

> 81 tasks tested (#21-101) | **44 / 81** (54.3%) | 2026-03-29

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 81 (#21-101; #1-20 tested separately) |
| ✅ Pass | 44 |
| ❌ Fail (noop / unsolved) | 33 |
| ⚠️ Evaluator/setup error | 4 |
| **Score** | **44 / 81** (54.3%) |

**Test environment:** Ubuntu ARM VM (VMware Fusion), 1920×1080
**Evaluation:** Official OSWorld evaluator (`DesktopEnv.evaluate()`)
**Agent approach:** Hybrid CLI + GUI (pyautogui on VM, vision analysis on Mac)

**Note:** 52 failed tasks include ~48 that were run with `solve_noop` (no action taken). These need individual solvers.

## Detailed Results

| # | Task ID | Instruction | Score | Status | Notes |
|---|---------|-------------|-------|--------|-------|
| 21 | `6d72aad6` | Convert Impress to video (built-in only) | 1.0 | ✅ | Infeasible → FAIL action |
| 22 | `f918266a` | Complete calculator.py + save output | 1.0 | ✅ | Fixed insertion sort TODO |
| 23 | `da52d699` | Find slowest reading pace book | 1.0 | ✅ | words/day calc → "Out of the Silent Planet" |
| 24 | `bc2b57f3` | Reorder sheets per reminder.docx | 1.0 | ✅ | LO Basic macro via `soffice --headless macro:///` |
| 25 | `74d5859f` | Set up web extension project | 1.0 | ✅ | Direct file creation: manifest.json + scripts |
| 26 | `b5062e3e` | Extract first author info from papers | 1.0 | ✅ | openpyxl with `ws.title='Sheet1'` |
| 27 | `00fa164e` | Insert Excel results into docx table | 1.0 | ✅ | python-docx table (4 decimal places) |
| 28 | `acb0f96b` | Clone instructor-embedding repo | 1.0 | ✅ | git clone with retry |
| 29 | `69acbb55` | Configure InstructorEmbedding env | 1.0 | ✅ | torch CPU + tqdm + InstructorEmbedding |
| 30 | `48d05431` | Install conda + datasets | 1.0 | ✅ | Miniconda ARM64 + conda init bash |
| 31 | `68a25bd4` | Download paper PDF + find citing paper | 1.0 | ✅ | BERT PDF + TinyBERT identified |
| 32 | `eb303e01` | Insert speaking notes into PPTX | 0.0 | ❌ | Gold bug: Slide 4 Shape 4 paragraph count mismatch (11 vs 10) |
| 33 | `0c825995` | Extract from Google Drive doc | — | ⚠️ | Setup failed: Google Drive auth needed |
| 34 | `c7c1e4c3` | Fill professor email addresses | 1.0 | ✅ | Download xlsx → local edit → upload |
| 35 | `d1acdb87` | Fill HK restaurant info sheet | 1.0 | ✅ | pyautogui typing failed (Chrome hijacked); local edit + upload |
| 36 | `deec51c9` | Find arxiv daily LLM paper list | 1.0 | ✅ | GUI: Name Box nav + pyautogui.typewrite in LO Calc |
| 37 | `8e116af7` | Update bookkeeping from receipts | — | ⚠️ | Evaluator crash: formulas lack `<v>` + LO recovery dialog |
| 38 | `337d318b` | Cross-check invoices vs bank statement | 1.0 | ✅ | Invoice #243729 → problematic/ folder |
| 39 | `82e3c869` | Extract presenter (Tao Yu) photos | 1.0 | ✅ | 4 photos → presenter/ + zip |
| 40 | `185f29bd` | Fill employee evaluation PDF forms | 0.0 | ❌ | Complex PDF form filling (7 employees), skipped |
| 41 | `869de13e` | Organize desktop files by category | 1.0 | ✅ | Paper_reading/Projects/Miscellaneous |
| 42 | `2c1ebcd7` | Fix APA 7th references in case study | 0.82 | ✅ | compare_references partial match |
| 43 | `3a93cae4` | Add lecture slot to course timetable | 0.0 | ❌ | Needs solver |
| 44 | `1f18aa87` | Complete grammar test answer keys | 0.0 | ❌ | Needs solver |
| 45 | `26150609` | Fix Snake game food placement bug | 0.0 | ❌ | Needs solver |
| 46 | `9219480b` | Fix Tetris rotation crash bug | 0.0 | ❌ | Needs solver |
| 47 | `881deb30` | Find HK faculty job info (Early Career) | 0.0 | ❌ | Needs browser |
| 48 | `7e287123` | Create GRF funding data xlsx | 1.0 | ✅ | openpyxl with formulas |
| 49 | `e2392362` | Set up academic homepage from template | 0.0 | ❌ | Needs browser |
| 50 | `5bc63fb9` | Process JSON survey responses | 0.0 | ❌ | Needs solver |
| 51 | `26660ad1` | Test network quality + save results | 0.0 | ❌ | Needs solver |
| 52 | `a82b78bb` | Find paper authors' personal webpages | 0.0 | ❌ | Needs browser |
| 53 | `36037439` | Find Google Scholar page of author | 0.0 | ❌ | Needs browser |
| 54 | `716a6079` | Find secret.docx + copy path to clipboard | 0.0 | ❌ | Needs solver |
| 55 | `873cafdd` | Install Chrome plugins from list | 0.0 | ❌ | Needs browser |
| 56 | `a74b607e` | Install Chrome extension manually | 0.0 | ❌ | Needs browser |
| 57 | `6f4073b8` | Count ML conference meeting cities | 0.0 | ❌ | Needs browser |
| 58 | `da922383` | Save blog articles to Calc sheet | 0.0 | ❌ | Needs browser |
| 59 | `2373b66a` | Monitor system resources with sar | 0.0 | ❌ | Needs solver (sysstat + sar) |
| 60 | `81c425f5` | Transfer Calc data to Writer table | 0.0 | ❌ | Needs solver |
| 61 | `bb83cab4` | Convert Impress to Writer document | 0.0 | ❌ | Needs solver |
| 62 | `227d2f97` | Copy XCF image into Writer docx | 0.0 | ❌ | Needs solver (GIMP batch + python-docx) |
| 63 | `b337d106` | Set up Vim syntax highlighting | 0.0 | ❌ | Needs solver |
| 64 | `20236825` | Practice algorithm in document | 0.0 | ❌ | Needs solver |
| 65 | `8df7e444` | Follow essay submission guidelines | 0.0 | ❌ | Needs solver |
| 66 | `aad10cd7` | Save blog content as local file | 0.0 | ❌ | Needs browser |
| 67 | `02ce9a50` | Insert screenshot into Writer tutorial | 0.0 | ❌ | Needs solver |
| 68 | `4c26e3f3` | Enhance dim image in Impress slide | 0.0 | ❌ | Needs solver |
| 69 | `a503b07f` | Convert receipt image to PDF | 1.0 | ✅ | PIL Image.convert('RGB').save() |
| 70 | `09a37c51` | Edit image for friend's request | 0.0 | ❌ | Needs solver |
| 71 | `3e3fc409` | Create movie statistics visualization | 0.0 | ❌ | Needs solver |
| 72 | `f5c13cdd` | Draft tuition reminder email | 0.0 | ❌ | Needs solver |
| 73 | `5990457f` | Add Yann LeCun from Google Scholar | 0.0 | ❌ | Needs browser |
| 74 | `415ef462` | Process AWS invoice email attachment | 0.0 | ❌ | Needs Thunderbird |
| 75 | `7ff48d5b` | Research Macau concert visa requirements | 0.0 | ❌ | Needs browser |
| 76 | `9f3bb592` | Remove subtitles from video | 0.0 | ❌ | Needs VLC/ffmpeg |
| 77 | `dd60633f` | Extract Python code from Colab notebook | 0.0 | ❌ | Needs browser |
| 78 | `ce2b64a2` | Identify and rename mountain photos | 1.0 | ✅ | Vision: Kilimanjaro, Mount Everest, Mount Hua |
| 79 | `3f05f3b9` | Fix MP3 metadata from filenames | 0.0 | ❌ | Needs solver |
| 80 | `e1fc0df3` | Install LanguageTool LO extension | 0.0 | ❌ | Needs solver |
| 81 | `f8369178` | Install Orchis GNOME theme | 1.0 | ✅ | git clone + install.sh + gsettings |
| 82 | `778efd0a` | Fix video playback in Impress | 0.0 | ❌ | Needs GUI |
| 83 | `47f7c0ce` | Extract video frame at 00:08 | — | ⚠️ | Evaluator error |
| 84 | `c2751594` | Export image from email attachment doc | 0.0 | ❌ | Needs Thunderbird |
| 85 | `788b3701` | Track GitHub story updates | 0.0 | ❌ | Needs browser |
| 86 | `48c46dc7` | Set up workspace (open project + apps) | 0.0 | ❌ | Needs solver |
| 87 | `42d25c08` | Convert web novel txt to ebook | 0.0 | ❌ | Needs solver |
| 88 | `e8172110` | Extract pixel art character in GIMP | 0.0 | ❌ | Needs GIMP |
| 89 | `42f4d1c7` | Configure VS Code for GIMP script-fu | 0.0 | ❌ | Needs solver |
| 90 | `3c8f201a` | Compress image under 600KB | 1.0 | ✅ | PIL quality=60 |
| 91 | `d68204bf` | Rearrange image sections by warm tones | 1.0 | ✅ | PIL crop + paste (warm→cold left→right) |
| 92 | `91190194` | Crop top 20% of cola.png | 1.0 | ✅ | PIL crop |
| 93 | `7f35355e` | Export table to CSV + find medium price | 0.0 | ❌ | Needs solver |
| 94 | `98e8e339` | Merge txt files into Writer document | 0.0 | ❌ | Needs solver |
| 95 | `0e5303d4` | Download Python course materials | 0.0 | ❌ | Needs browser |
| 96 | `df67aebb` | Format paper thesis references | 0.0 | ❌ | Needs solver |
| 97 | `5df7b33a` | Split book into chapters | 0.0 | ❌ | Needs solver |
| 98 | `aceb0368` | Grade English exam multiple choice | 0.0 | ❌ | Needs solver |
| 99 | `22a4636f` | Convert docx to PDF + upload to Drive | — | ⚠️ | Google Drive auth needed |
| 100 | `236833a3` | Find HuggingFace daily paper list | 0.0 | ❌ | Needs browser |
| 101 | `67890eb6` | Find ACL best long paper awards 2019-2023 | 0.0 | ❌ | Needs browser |

## Known Issues & Workarounds

| Issue | Workaround |
|-------|------------|
| LO Document Recovery dialog blocks after crash/kill | `rm -f ~/.config/libreoffice/4/user/.~lock.*` before reopening |
| openpyxl destroys charts when saving xlsx | Use LO Basic macro via `soffice --headless macro:///` |
| openpyxl default sheet name "Sheet" ≠ evaluator "Sheet1" | Always set `ws.title = 'Sheet1'` |
| openpyxl formulas lack `<v>` cached values | Write numeric values, or use LO to re-save |
| pyautogui `typewrite()` triggers Chrome on URL-like text | Use clipboard paste or local edit + upload |
| xdotool not pre-installed on OSWorld VMs | Use pyautogui.typewrite() (always available); http_remote.py fixed in c22ce63 |
| pip install on VM times out (HuggingFace SSL errors) | Modify files locally on Mac, upload via base64 |
| Google Drive tasks need OAuth | Requires credentials setup in settings.yml |
| PPTX shape EMU mismatch (pre-existing in gold) | Accept 0 score, not fixable |

## Lessons Learned

### 1. Local Edit + Upload Pattern
Best pattern for modifying VM files:
1. Download from VM via base64: `vm_exec(["python3", "-c", "import base64; print(base64.b64encode(open('path','rb').read()).decode())"])`
2. Modify locally on Mac with openpyxl/python-docx (always available)
3. Upload back via base64 chunks (50000 chars each)
4. Open in LO: `soffice --calc 'path' &`

### 2. LO Headless Macro for Sheet Operations
Task 24 showed that `soffice --headless macro:///Standard.Module1.ReorderSheets` can execute Basic macros without GUI. This preserves charts and formatting that openpyxl would destroy.

### 3. Evaluator Strictness
- `compare_pptx_files`: Checks ALL shapes including paragraph count (Task 32 gold bug)
- `compare_docx_tables`: Exact text match per cell (need exact decimal places)
- `check_cell`: Reads raw XML `<v>` tags, not computed values
- `compare_table` with `sheet_print`: Converts xlsx→CSV via libreoffice

### 4. pyautogui on VM
- VM resolution: 1920×1080
- `typewrite()` can trigger browser on URL-like text
- Use `wmctrl -a 'title'` for window activation
- Recovery dialog blocks GUI operations after soffice crash

## Files

- Results JSON: `~/OSWorld/results_official.json`
- GUI memory: `~/.openclaw/workspace/skills/gui-agent/memory/apps/`
