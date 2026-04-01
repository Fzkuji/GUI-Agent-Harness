# OSWorld Multi-Apps Domain — GUI Agent Skills Results

> 101 tasks total | Last updated: 2026-04-01 22:42 HKT

## Current Status

| Metric | Value |
|--------|-------|
| Total tasks | 101 |
| ✅ Verified (official eval) | 21 |
| ⏳ Pending eval | 42 |
| ❌ Blocked | 20 |
| 🔲 Not yet attempted | 18 |
| **Verified score** | **15.443/21 = 73.5%** |

> Scores are ONLY from OSWorld official evaluator (`desktop_env/evaluators/`).

## Detailed Results

| # | Task ID | Instruction (truncated) | Score | Notes |
|---|---------|------------------------|-------|-------|
| 1 | `2b9493d7` | Force quit LibreOffice Writer | **1.0** | Terminal输入killall -9 soffice.bin |
| 2 | `2c9fc0de` | Push git changes | **1.0** | Terminal执行git add/commit/push到origin main |
| 3 | `2fe4b718` | Create animated GIF from video | **0.845** | ffmpeg截取视频转GIF，帧率/尺寸与gold略有差异 |
| 4 | `3680a5ee` | Merge xlsx/ods columns to CSV | **1.0** | openpyxl+odfpy读取两列，csv.writer合并，LO Calc从terminal打开 |
| 5 | `46407397` | Export charts from docx | | |
| 6 | `4e9f0faf` | Extract invoice table | | |
| 7 | `510f64c8` | Start VS Code from terminal | **0.0** | VS Code已打开project，但eval extension未激活(activationEvents为空) |
| 8 | `51f5801c` | Extract Impress notes to docx | **1.0** | python-pptx提取notes + python-docx保存，ignore_blanks |
| 9 | `58565672` | Open email link in Chrome | **N/A** | 需要外网访问amazon.com，VM网络503 |
| 10 | `78aed49a` | Save email attachments | | |
| 11 | `897e3b53` | Convert docx form | | |
| 12 | `937087b6` | Set VLC as default player | **0.0** | 部分video类型未覆盖，evaluator检查所有MIME type |
| 13 | `a0b9dc9c` | Backup emails | | |
| 14 | `b52b40a5` | Merge PDFs | | |
| 15 | `c867c42d` | Export TB contacts to CSV/XLSX | **0.0** | 导出30条但gold有60条，sqlite缺少vCard解析的字段 |
| 16 | `d9b7c649` | Extract 5 emails to report.xlsx | **1.0** | mbox解析+openpyxl导出 |
| 17 | `e135df7c` | Convert xlsx to HTML, view in Chrome | **1.0** | libreoffice --headless转换+CDP打开tab |
| 18 | `ee9a3c83` | Convert ODS to CSV via terminal | **1.0** | libreoffice --headless --convert-to csv |
| 19 | `f7dfbef3` | Convert .doc files to PDF | **0.998** | libreoffice --headless --convert-to pdf *.doc |
| 20 | `f8cfa149` | Copy cell B6, search in Chrome | **0.0** | Google搜索URL正确但evaluator Playwright导航可能超时 |
| 21 | `6d72aad6` | Convert Impress to video | **1.0** | infeasible任务，正确回复FAIL |
| 22 | `f918266a` | Complete Python calculator code | **1.0** | 补充insertionSort缺失行+运行保存log.txt |
| 23 | `da52d699` | Find slowest reading pace book | **1.0** | 答案: Out of the Silent Planet |
| 24 | `bc2b57f3` | Reorder spreadsheet sheets | **1.0** | 读reminder.docx获取顺序，openpyxl重排10个sheet |
| 25 | `74d5859f` | Web extension project setup | **0.6** | 操作正确，manifest/index.html/style.css满分；background_script.js和script.js的gold文件被Google Drive病毒扫描HTML替换(数据集bug) |
| 26 | `b5062e3e` | Extract author info from PDFs | **1.0** | pdftotext提取4篇论文首作者name/email/affiliation，openpyxl写xlsx按名字排序 |
| 27 | `00fa164e` | Insert GPT-4 results table | **1.0** | 从xlsx提取GPT-4行数据(4位小数)，python-docx插入表格到docx的Main Results节 |
| 28 | `acb0f96b` | Clone GitHub repo | | |
| 29 | `69acbb55` | Configure word embeddings | | |
| 30 | `48d05431` | Install conda | | |
| 31 | `68a25bd4` | Download paper + find citation | | |
| 32 | `eb303e01` | Insert speaker notes to PPTX | | |
| 33 | `0c825995` | Environmental policy report | | |
| 34 | `c7c1e4c3` | Collect professor emails | | |
| 35 | `d1acdb87` | Hong Kong restaurant info | | |
| 36 | `deec51c9` | arxiv paper list | | |
| 37 | `8e116af7` | Update bookkeeping from receipts | | |
| 38 | `337d318b` | Cross-check invoices | | |
| 39 | `82e3c869` | Sort event photos | | |
| 40 | `185f29bd` | Excel to PDF form | | |
| 41 | `869de13e` | Organize desktop files | | |
| 42 | `2c1ebcd7` | Review case study references | | |
| 43 | `3a93cae4` | Add lecture to timetable | | |
| 44 | `1f18aa87` | Grammar test answers | | |
| 45 | `26150609` | Fix Snake game code | | |
| 46 | `9219480b` | Fix Tetris game code | | |
| 47 | `881deb30` | Faculty job info (web) | | |
| 48 | `7e287123` | GRF funding info (web) | | |
| 49 | `e2392362` | Academic homepage setup | | |
| 50 | `5bc63fb9` | JSON→Gemini docx | | |
| 51 | `26660ad1` | Network sar monitoring | | |
| 52 | `a82b78bb` | Find author webpage | | |
| 53 | `36037439` | Google Scholar page | | |
| 54 | `716a6079` | Find secret.docx + clipboard | | |
| 55 | `873cafdd` | Install Chrome plugins | | |
| 56 | `a74b607e` | Install Chrome extension | | |
| 57 | `6f4073b8` | Count conference cities | | |
| 58 | `da922383` | Store blog articles | | |
| 59 | `2373b66a` | System monitoring with sar | | |
| 60 | `81c425f5` | Calc data to docx table | | |
| 61 | `bb83cab4` | Impress to Writer conversion | | |
| 62 | `227d2f97` | XCF image to docx | | |
| 63 | `b337d106` | Vim line numbers | | |
| 64 | `20236825` | Bubble sort practice | | |
| 65 | `8df7e444` | Essay submission zip | | |
| 66 | `aad10cd7` | Blog to local file | | |
| 67 | `02ce9a50` | Writer with terminal screenshots | | |
| 68 | `4c26e3f3` | Enhance dim slide image | | |
| 69 | `a503b07f` | Receipt image to PDF | | |
| 70 | `09a37c51` | Edit image (remove background) | | |
| 71 | `3e3fc409` | Movie records analysis | | |
| 72 | `f5c13cdd` | Email tuition reminder | | |
| 73 | `5990457f` | Yann LeCun Google Scholar | | |
| 74 | `415ef462` | AWS invoice extraction | | |
| 75 | `7ff48d5b` | Macau travel info | | |
| 76 | `9f3bb592` | Remove video subtitles | | |
| 77 | `dd60633f` | Extract Python from colab | | |
| 78 | `ce2b64a2` | Identify mountain photos | | |
| 79 | `3f05f3b9` | MP3 metadata editing | | |
| 80 | `e1fc0df3` | Install LanguageTool extension | | |
| 81 | `f8369178` | Install Orchis GNOME theme | | |
| 82 | `778efd0a` | Extract video audio for slides | | |
| 83 | `47f7c0ce` | Extract video frame for slide bg | | |
| 84 | `c2751594` | Export image from email→wallpaper | | |
| 85 | `788b3701` | Track GitHub short tale | | |
| 86 | `48c46dc7` | Setup workspace | | |
| 87 | `42d25c08` | TXT to EPUB novel | | |
| 88 | `e8172110` | GIMP pixel art extraction | | |
| 89 | `42f4d1c7` | VS Code + GIMP scripting | | |
| 90 | `3c8f201a` | Download + compress image | | |
| 91 | `d68204bf` | Divide image into sections | | |
| 92 | `91190194` | GIMP crop top 20% | | |
| 93 | `7f35355e` | CSV + find median price | | |
| 94 | `98e8e339` | Merge txt files to docx | | |
| 95 | `0e5303d4` | Clone Python course repo | | |
| 96 | `df67aebb` | Paper bibliography | | |
| 97 | `5df7b33a` | Split bulky book | | |
| 98 | `aceb0368` | Grade English exam | | |
| 99 | `22a4636f` | Convert docx to PDF + upload | | |
| 100 | `236833a3` | HuggingFace daily paper list | | |
| 101 | `67890eb6` | ACL best paper awards | | |

## Legend
- **Bold score** = Verified by official OSWorld evaluator
- Empty = Not yet evaluated
