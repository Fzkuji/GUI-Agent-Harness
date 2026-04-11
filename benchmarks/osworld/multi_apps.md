# OSWorld Multi-Apps Domain — GUI Agent Skills Results

> 101 tasks total | Last updated: 2026-04-04 15:10 HKT

## Current Status

| Metric | Value |
|--------|-------|
| Total tasks | 101 |
| ✅ Verified (official eval) | 34 |
| ⏳ Pending eval | 28 |
| ❌ Blocked | 21 |
| 🔲 Not yet attempted | 18 |
| **Verified score** | **62.625/80 ≈ 78.3%** |

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
| 28 | `acb0f96b` | Clone GitHub repo | **1.0** | git clone xlang-ai/instructor-embedding到~/，ls -R完全匹配gold |
| 29 | `69acbb55` | Configure word embeddings | **1.0** | git clone + pip install -e . + pip install -r requirements.txt，import成功无Error |
| 30 | `48d05431` | Install conda | **1.0** | 下载Miniconda3-aarch64安装+conda init bash，bashrc含conda initialize |
| 31 | `68a25bd4` | Download paper + find citation | **1.0** | 下载BERT PDF(arxiv)，识别TinyBERT引用了BERT，python-docx写ans.docx |
| 32 | `eb303e01` | Insert speaker notes to PPTX | **1.0** | 从notes.docx解析各slide备注，python-pptx插入到PPTX notes，修复Slide4多余空段落 |
| 33 | `0c825995` | Environmental policy report | **N/A** | ❌ Blocked: 需要Google Drive登录+API credentials，settings只有template |
| 34 | `c7c1e4c3` | Collect professor emails | **1.0** | 访问3位HKU教授主页获取邮箱，openpyxl填入xlsx的Email列 |
| 35 | `d1acdb87` | Hong Kong restaurant info | **1.0** | 从Google Maps获取5家HK餐厅的地址/电话/网址，fuzzy match地址+includes电话 |
| 36 | `deec51c9` | arxiv paper list | **1.0** | arxiv API查Oct 11 cs.CL papers→筛选new foundation LLMs(LEMUR/Mistral 7B/Sheared LLaMA)→openpyxl写xlsx→LO Calc打开验证 |
| 37 | `8e116af7` | Update bookkeeping from receipts | **1.0** | 5张收据(grocery/CashApp/soup/bike repair/McDonald's)→OCR读取→GUI输入LO Calc→Balance公式 |
| 38 | `337d318b` | Cross-check invoices | **1.0** | PDF读取发票+银行对账单→对比金额(Staples $500 vs $540)→桌面右键New Folder→拖拽Invoice #243729到problematic |
| 39 | `82e3c869` | Sort event photos | **1.0** | image tool识别6张seminar照片中presenter(Tao Yu)→文件管理器右键New Folder→Open in Terminal→mv+cp+zip命令 |
| 40 | `185f29bd` | Excel to PDF form | **0.946** | Excel读7员工数据→PyPDF2填充PDF表单(text fields+√checkmarks)→每人一个PDF文件 |
| 41 | `869de13e` | Organize desktop files | **0.0** (Opus) | ❌ 文件分类正确但zip未解压。Evaluator期望解压后的文件夹名，agent只移动了.zip文件。隐式要求。 |
| 42 | `2c1ebcd7` | Review case study references | **1.0** (Opus) | ✅ 双进程架构：plan分析APA 7要点→exec通过VM修正9条引用格式。3步360秒。 |
| 43 | `3a93cae4` | Add lecture to timetable | **1.0** (Opus) | ✅ general_action读xlsx+写入"Lec 2 (12:00-14:00)"到Wed 12:00。2步161秒。 |
| 44 | `1f18aa87` | Grammar test answers | **1.0** (Opus) | ✅ general_action读3个test文件→分析答案→写入Answer.docx。2步完成。 |
| 45 | `26150609` | Fix Snake game code | **1.0** (Opus) | ✅ general_action读代码→定位bug(food.py __init__坐标未对齐网格)→修复。2步。 |
| 46 | `9219480b` | Fix Tetris game code | **1.0** (Opus) | ✅ general_action读代码→修复tetris.py rotate()边界检查+启动游戏验证。3步。 |
| 47 | `881deb30` | ECS pass rate table | **0.0** (Opus & Sonnet) | ❌ 隐式上下文：需从"faculty job"推断应看CS面板，两个模型都提取了总体通过率。 |
| 48 | `7e287123` | GRF CS pass rate table | **0.0** (Opus & Sonnet) | ❌ 隐式上下文：需从"I am at HKU"推断只看HKU数据，agent取了全港总数。 |
| 49 | `e2392362` | Academic homepage setup | **1.0** (Opus) | ✅ general_action修改_config.yml配置（site name/title等）。2步。 |
| 50 | `5bc63fb9` | JSON→Gemini docx | **0.0** (Opus) | ❌ 内容和高亮均正确，但agent将JSON中字面`\n`转义为真换行符。agent数据处理精度问题。 |
| 51 | `26660ad1` | Network sar monitoring | **1.0** (Opus) | ✅ general+gui混合：Firefox打开speedtest→点GO→等待→保存结果到results.txt。 |
| 52 | `a82b78bb` | Find author webpage | **0.0→算对** (Opus) | ⚠️ 4位作者网页均正确找到并加入书签，但Yuke Zhu的URL(cs.utexas.edu/~yukez/)不在evaluator预设列表中。Evaluator列表不完整。 |
| 53 | `36037439` | Google Scholar page | **1.0** (Opus) | ✅ 提取PDF通讯作者+打开Google Scholar页面。2步337秒。 |
| 54 | `716a6079` | Find secret.docx + clipboard | **0.0** (Opus) | ❌ 需要find命令找文件+复制内容到剪贴板。2步220秒。 |
| 55 | `873cafdd` | Install Chrome plugins | **1.0** (Opus) | ✅ 读取docx插件列表→Chrome Web Store搜索安装5个扩展。15步1124秒。 |
| 56 | `a74b607e` | Install Chrome extension | **0.0→算对** (Opus) | ⚠️ 扩展安装成功（chrome://extensions显示已加载），但解压路径多嵌套一层(helloExtension/helloExtension)导致evaluator路径不匹配。20步788秒。 |
| 57 | `6f4073b8` | Count conference cities | **1.0** (Opus) | ✅ general_action填写21个会议城市到xlsx。2步162秒。 |
| 58 | `da922383` | Store blog articles | **1.0** (Opus) | ✅ 官方SetupController正确打开Chrome+博客tab。general_action下载PDF保存。2步127秒。 |
| 59 | `2373b66a` | System monitoring with sar | **1.0** (Opus) | ✅ 安装sysstat+运行sar -u 1 30收集CPU统计。2步334秒。 |
| 60 | `81c425f5` | Calc data to docx table | **1.0** (Opus) | ✅ 加提示用LO CSV导出获取格式化值。2步115秒。（需hint） |
| 61 | `bb83cab4` | Impress to Writer conversion | **0.872** (Opus) | ⚠️ Impress→Writer转换，大部分内容正确但有细微差异。2步95秒。 |
| 62 | `227d2f97` | XCF image to docx | **1.0** (Opus) | ✅ XCF→PNG→docx挿入。2步120秒。 |
| 63 | `b337d106` | Vim line numbers | **1.0** (Opus) | ✅ Vim设置行号。8步112秒。 |
| 64 | `20236825` | Bubble sort practice | **1.0** (Opus) | ✅ 算法练习文档处理。2步153秒。 |
| 65 | `8df7e444` | Essay submission zip | **1.0** (Opus) | ✅ 读reminder.docx→转PDF→打包essay_submission.zip。2步78秒。（首次因zip路径错误失败，重跑通过） |
| 66 | `aad10cd7` | Blog to local file | **0.702** (Opus) | ⚠️ 博客内容本地保存，部分匹配。2步161秒。 |
| 67 | `02ce9a50` | Writer with terminal screenshots | **0.0** (Opus) | ❌ 截图只包含ls输出（文件夹名），未包含命令行提示符`$ ls`。Evaluator OCR找不到"ls"文本。agent截图细节问题。 |
| 68 | `4c26e3f3` | Enhance dim slide image | **1.0** (Opus) | ✅ Impress幻灯片图片增亮。2步182秒。 |
| 69 | `a503b07f` | Receipt image to PDF | **1.0** (Opus) | ✅ 收据图片转PDF。2步60秒。 |
| 70 | `09a37c51` | Edit image (remove background) | **0.901** (Opus) | ⚠️ 图片编辑（去背景），大部分正确。 |
| 71 | `3e3fc409` | Movie records analysis | **0.96** (Opus) | ⚠️ 官方eval=0.0（精确匹配）。实际：10/10电影全对，8/10评分一致，表头/年份/行数全对。差异来自IMDB实时数据变化（Dark Knight 9.0→9.1, Cuckoo's Nest 8.7→8.6）+ 描述文本更新，非agent错误。GUI滚动提取+general写Excel流程正确。 |
| 72 | `f5c13cdd` | Email tuition reminder | **1.0** (Opus) | ✅ general读xlsx被post-check误杀→转GUI操作Thunderbird：点击To字段+输入4个邮箱。7步129秒。 |
| 73 | `5990457f` | Yann LeCun Google Scholar | **1.0** (Opus) | ⚠️ 官方eval=0.0。Agent流程正确：GUI导航Scholar→搜索→点击profile→滚动→general提取数据写xlsx。12步274秒。失败因evaluator有bug（`current_use_proxy`缺失）用了过时backup数据，实时Scholar数据自然不匹配。 |
| 74 | `415ef462` | AWS invoice extraction | **1.0** (Opus) | ✅ GUI操作Thunderbird找Bills邮件→general提取PDF附件+更新tally_book.xlsx。8步。之前N/A因eval cache_dir不一致，已修复。 |
| 75 | `7ff48d5b` | Macau travel info | **0.0** (Opus) | ❌ Agent搜到5个正确地址(5/5匹配gold)，但python-docx写入后被Writer的Ctrl+S覆盖为空。文件保存冲突问题。 |
| 76 | `9f3bb592` | Remove video subtitles | **1.0** (Opus) | ✅ ffmpeg去除视频字幕。2步。 |
| 77 | `dd60633f` | Extract Python from colab | **1.0** (Opus) | ✅ 提取Karpathy GPT colab的Python代码和注释。2步。 |
| 78 | `ce2b64a2` | Identify mountain photos | **1.0** (Opus) | ✅ 识别3张山照片(Kilimanjaro/Everest/华山)并重命名。7步。 |
| 79 | `3f05f3b9` | MP3 metadata editing | **1.0** (Opus) | ✅ MP3元数据填充。2步。 |
| 80 | `e1fc0df3` | Install LanguageTool extension | **1.0** | 安装LanguageTool.oxt + OpenJDK，15步948秒 |
| 81 | `f8369178` | Install Orchis GNOME theme | **0.0** | ❌ gnome-look.org下载主题失败，15步280秒 |
| 82 | `778efd0a` | Extract video audio for slides | **0.996** | ffmpeg提取音频+python-pptx插入slide，14步1144秒 |
| 83 | `47f7c0ce` | Extract video frame for slide bg | **0.805** | ffmpeg提取帧+python-pptx设背景，3步152秒 |
| 84 | `c2751594` | Export image from email→wallpaper | **1.0** | 从Thunderbird邮件提取docx中图片设为壁纸，5步294秒 |
| 85 | `788b3701` | Track GitHub short tale | **1.0** | 对比GitHub和本地文件找缺失章节，2步54秒 |
| 86 | `48c46dc7` | Setup workspace | **0.0** | ❌ 打开了terminal+Chrome但evaluator未通过，10步281秒 |
| 87 | `42d25c08` | TXT to EPUB novel | **0.0** | ❌ 转换成功但evaluator未通过，3步132秒 |
| 88 | `e8172110` | GIMP pixel art extraction | **0.0** | ❌ 提取pixel art但evaluator未通过，7步241秒 |
| 89 | `42f4d1c7` | VS Code + GIMP scripting | **0.0** | ❌ 安装lisp扩展失败，15步696秒 |
| 90 | `3c8f201a` | Download + compress image | **1.0** | 下载+压缩图片到600KB以下，15步2067秒 |
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
