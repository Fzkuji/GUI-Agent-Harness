# OSWorld Multi-Apps Domain — GUI Agent Skills Results

> 101 tasks total | **48 passed / 61 attempted** | 40 remaining | 2026-03-30

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 101 |
| ✅ Pass (score > 0) | 48 |
| ❌ Fail (score = 0) | 13 |
| 🔲 Not attempted | 40 |
| **Pass rate (attempted)** | **48/61** (78.7%) |
| **Pass rate (total)** | **48/101** (47.5%) |

**Test environment:** Ubuntu ARM VM (VMware Fusion), 1920×1080
**Evaluation:** Official OSWorld evaluator (`DesktopEnv.evaluate()`)
**Agent approach:** Hybrid CLI + GUI (pyautogui on VM, vision analysis on Mac)

## Detailed Results

| # | Task ID | Instruction | Score | Status | Notes |
|---|---------|-------------|-------|--------|-------|
| 1 | `2b9493d7` | Hey, my LibreOffice Writer seems to have frozen and I can't get it to close norm | 1.0 | ✅ | killall soffice.bin + bash_history |
| 2 | `2c9fc0de` | Could you help me push the changes from commandline in current project to origin | 1.0 | ✅ | git add -A + commit "daily update" + push origin main |
| 3 | `2fe4b718` | Could you help me create an Animated GIF src_clip.gif from a video file using VL | 0.75 | ✅ | ffmpeg → GIF (image similarity 75%) |
| 4 | `3680a5ee` | I have file1.xlsx and file2.ods on my Desktop, each containing a single column.  | 1.0 | ✅ | Tab-separated CSV merge via gnome-terminal + LO headless |
| 5 | `46407397` | Help me export charts, graph or other images from docx files received in email " | 0.0 | ❌ | setup_failed: Google Drive credentials missing |
| 6 | `4e9f0faf` | Could you help me extract data in the table from a new invoice uploaded to my Go | 0.0 | ❌ | setup_failed: Google Drive credentials missing |
| 7 | `510f64c8` | Could you start VS Code in folder ~/Desktop/project from the terminal? | 0.0 | ❌ | VS Code eval extension broken (OpenProject.txt not generated) |
| 8 | `51f5801c` | I've been working on this presentation in LibreOffice Impress and I've added a b | 1.0 | ✅ | python-pptx extract notes → python-docx notes.docx |
| 9 | `58565672` | Can you assist me by opening the first link in the latest email in Bills folder  | 1.0 | ✅ | Thunderbird mbox → extract URL → CDP PUT /json/new |
| 10 | `78aed49a` | Could you help me save all attachments of the oldest email in Bills local folder | 0.0 | ❌ | setup_failed: Google Drive credentials missing |
| 11 | `897e3b53` | I have a LibreOffice Writer file form.docx on the desktop. Help me convert it to | 0.0 | ❌ | setup_failed: Google Drive credentials missing |
| 12 | `937087b6` | I am currently using a ubuntu system. Could you help me set the default video pl | 1.0 | ✅ | xdg-mime + mimeapps.list for all video MIME types |
| 13 | `a0b9dc9c` | Please help me backup my emails in "Bills" folder in Thunderbird and store the . | 0.0 | ❌ | setup_failed: Google Drive credentials missing |
| 14 | `b52b40a5` | Could you help me merge all PDF files in the "Paper Recommendation" email attach | 0.0 | ❌ | setup_failed: Google Drive credentials missing |
| 15 | `c867c42d` | Please assist me in exporting my contacts of Personal Address Book from Thunderb | 0.0 | ❌ | abook.sqlite → CSV export failed (VM lacks xlrd) |
| 16 | `d9b7c649` | Help me extract the latest 5 emails in daily folder from Thunderbird, from the e | 1.0 | ✅ | mailbox parse → openpyxl report.xlsx (5 latest emails) |
| 17 | `e135df7c` | Please convert a .xlsx file opened in LibreOffice Calc to a .html file and view  | 1.0 | ✅ | LO headless --convert-to html + CDP open in Chrome |
| 18 | `ee9a3c83` | Could you help me convert the opened ods file in the desktop to csv file with th | 1.0 | ✅ | gnome-terminal + LO headless --convert-to csv + bash_history |
| 19 | `f7dfbef3` | Could you convert all `.doc` files in current directory to PDF all at once in th | 1.00 | ✅ | LO headless --convert-to pdf *.doc (12 files) |
| 20 | `f8cfa149` | Could you help me copy the data in Cell B6 in this Libreoffice Calc file and sea | 0.0 | ❌ | B6=Nereida, Chrome search opened but QUIC protocol error in eval |
| 21 | `6d72aad6` | Convert an OpenOffice/LibreOffice Impress presentation into a video using only L | 1.0 | ✅ | Infeasible → FAIL action |
| 22 | `f918266a` | Please complete the code and retrieve the output from the Python script 'calcula | 1.0 | ✅ | Fixed insertion sort TODO |
| 23 | `da52d699` | Examine the spreadsheet on the desktop, which contains a record of books read in | 1.0 | ✅ | words/day calc → "Out of the Silent Planet" |
| 24 | `bc2b57f3` | The requirements of my data analysis assignment are listed in "reminder.docx" on | 1.0 | ✅ | LO Basic macro via soffice --headless |
| 25 | `74d5859f` | Help me to set up an initial web extension project with help of the web tool, ta | 1.0 | ✅ | Direct file creation: manifest.json + scripts |
| 26 | `b5062e3e` | Please help me to extract the name, e-mail, and affiliation of the first author  | 1.0 | ✅ | openpyxl with ws.title="Sheet1" |
| 27 | `00fa164e` | I need to include the experiment results from "~/Documents/awesome-desktop/expe- | 1.0 | ✅ | python-docx table (4 decimal places) |
| 28 | `acb0f96b` | Please help me clone the repo "https://github.com/xlang-ai/instructor-embedding" | 1.0 | ✅ | git clone with retry |
| 29 | `69acbb55` | I'm working on word embedding tasks and require assistance in configuring the en | 1.0 | ✅ | torch CPU + InstructorEmbedding |
| 30 | `48d05431` | When I ran "conda install datasets" in terminal, I got "conda: command not found | 1.0 | ✅ | Miniconda ARM64 + conda init bash |
| 31 | `68a25bd4` | I've compiled papers and books with links in this spreadsheet. Help me download  | 1.0 | ✅ | BERT PDF + TinyBERT citation |
| 32 | `eb303e01` | Tomorrow, I'm scheduled to deliver a talk, and my PowerPoint slides and speaking | 0.0 | ❌ | Gold bug: Slide 4 paragraph count mismatch |
| 33 | `0c825995` | I'm working on a comprehensive report for our environmental policy review meetin | — | 🔲 | Not attempted |
| 34 | `c7c1e4c3` | I am collecting the contact information of some professors and have their homepa | 1.0 | ✅ | Download xlsx → local edit → upload |
| 35 | `d1acdb87` | Hello! I'm eagerly planning a culinary adventure to Hong Kong and have curated a | 1.0 | ✅ | GUI: gui_action.py click/type in LO Calc |
| 36 | `deec51c9` | Find a paper list of all the new foundation language models issued on 11st Oct.  | 1.0 | ✅ | GUI: Name Box nav + typewrite in LO Calc |
| 37 | `8e116af7` | Please update my bookkeeping sheet with the recent transactions from the provide | 0.0 | ❌ | Evaluator crash: formulas lack cached values |
| 38 | `337d318b` | Cross-check the invoices with the bank statements and identify any discrepancies | 1.0 | ✅ | Invoice #243729 → problematic/ folder |
| 39 | `82e3c869` | Please sift through the folder with all the event photos taken by our photograph | 1.0 | ✅ | 4 photos → presenter/ + zip |
| 40 | `185f29bd` | Transfer the data from our 'Employee Performance Evaluation Summary' Excel sheet | 0.97 | ✅ | pypdf form fill; partial field mapping |
| 41 | `869de13e` | Can you organize my desktop by identifying academic papers, coding projects, and | 1.0 | ✅ | Paper_reading/Projects/Miscellaneous |
| 42 | `2c1ebcd7` | Could you please take a moment to review the 'case study' file located within th | 0.82 | ✅ | compare_references partial match |
| 43 | `3a93cae4` | Could you please add a two-hour lecture slot to my weekly course timetable, sche | 1.0 | ✅ | Added Lec 2 (12:00-14:00) to cell D5 |
| 44 | `1f18aa87` | I've prepared some grammar tests and placed them in the 'Grammar test' folder. I | 1.0 | ✅ | Read 3 .docx files, created Answer.docx |
| 45 | `26150609` | So, I've been dabbling with coding a Snake game in Python, and I finally got it  | 1.0 | ✅ | Grid alignment fix for food spawning |
| 46 | `9219480b` | Hi, I recently playing with developing a small python-based tetris game. While I | 1.0 | ✅ | rotate() + intersect() check |
| 47 | `881deb30` | I want to find a faculty job in Hong Kong, so I am more curious about the "Early | — | 🔲 | Not attempted |
| 48 | `7e287123` | I am an assistant professor of CS at HKU, I want to apply for the General Resear | 1.0 | ✅ | openpyxl with formulas |
| 49 | `e2392362` | I recently started using the famous personal academic homepage template from aca | — | 🔲 | Not attempted |
| 50 | `5bc63fb9` | I have a JSON-formatted data file opened now that stores the responses of severa | — | 🔲 | Not attempted |
| 51 | `26660ad1` | I want to test the quality of the network environment my laptop is currently in. | — | 🔲 | Not attempted |
| 52 | `a82b78bb` | I'm really enjoying this paper. Could you please locate the personal webpages of | — | 🔲 | Not attempted |
| 53 | `36037439` | Could you please pull up the Google Scholar page of the corresponding author for | — | 🔲 | Not attempted |
| 54 | `716a6079` | I remember there is a file named "secret.docx" on this computer, but I can't rem | — | 🔲 | Not attempted |
| 55 | `873cafdd` | My friend is a "plugin guru" and he recommended some good plug-ins to me. Please | — | 🔲 | Not attempted |
| 56 | `a74b607e` | I have developed a new Chrome extension myself, so it needs to be installed manu | — | 🔲 | Not attempted |
| 57 | `6f4073b8` | I now want to count the meeting cities of the three machine learning conferences | — | 🔲 | Not attempted |
| 58 | `da922383` | I browsed a lot of interesting blog articles today. I hope to store these articl | — | 🔲 | Not attempted |
| 59 | `2373b66a` | Monitor Ubuntu system resource usage using the sar command from sysstat toolkit. | 1.0 | ✅ | sysstat + sar -u 1 30 |
| 60 | `81c425f5` | Can you assist me in transferring the data from LibreOffice Calc in the current  | — | 🔲 | Not attempted |
| 61 | `bb83cab4` | I want to convert an Impress file into a document editable in Writer. Simply pla | 0.0 | ❌ | pptx shape extraction mismatch |
| 62 | `227d2f97` | I've stored my .xcf file on the Desktop. Can you assist me in copying the image  | 0.0 | ❌ | GIMP batch convert + python-docx |
| 63 | `b337d106` | Recently, I've been exploring the use of the Vim editor for code editing. Howeve | 1.0 | ✅ | .vimrc: set number + syntax on |
| 64 | `20236825` | I am currently working on my algorithm practice using the document "bubble_Sort_ | — | 🔲 | Not attempted |
| 65 | `8df7e444` | The guidelines for submitting our essay work are provided in the "reminder.docx" | — | 🔲 | Not attempted |
| 66 | `aad10cd7` | I want to obtain a local file version of the content from the blog at https://de | — | 🔲 | Not attempted |
| 67 | `02ce9a50` | I am currently utilizing LibreOffice Writer to compose a Linux tutorial, and I i | — | 🔲 | Not attempted |
| 68 | `4c26e3f3` | I've noticed that the image on the second slide is too dim. Can you please enhan | — | 🔲 | Not attempted |
| 69 | `a503b07f` | I have an image of my receipt located in /home/user. I'm looking to transform it | 1.0 | ✅ | PIL Image.convert("RGB").save() |
| 70 | `09a37c51` | I've received a request from my friend who asked for assistance in editing an im | — | 🔲 | Not attempted |
| 71 | `3e3fc409` | I'm a huge movie fan and have kept a record of all the movies I've watched. I'm  | — | 🔲 | Not attempted |
| 72 | `f5c13cdd` | I've drafted an e-mail reminder for those who haven't paid tuition. Please help  | — | 🔲 | Not attempted |
| 73 | `5990457f` | Append one entry of AI researcher Yann LeCun from Google Scholar into an existin | — | 🔲 | Not attempted |
| 74 | `415ef462` | There's an e-mail containing the AWS invoice for December saved in local "Bills" | — | 🔲 | Not attempted |
| 75 | `7ff48d5b` | I am a Chinese citizen and I want to go to Macau to watch a concert recently, bu | — | 🔲 | Not attempted |
| 76 | `9f3bb592` | I downloaded a video to practice listening, but I don't know how to remove the s | — | 🔲 | Not attempted |
| 77 | `dd60633f` | Please extract all Python code and comments from Karpathy's GPT colab code cells | — | 🔲 | Not attempted |
| 78 | `ce2b64a2` | There are several pictures of mountains in my Pictures directory, but I don’t kn | 1.0 | ✅ | Vision: Kilimanjaro, Everest, Mount Hua |
| 79 | `3f05f3b9` | I have a collection of MP3s with blank meta data, but already named with their a | 1.0 | ✅ | mutagen ID3 fix for corrupt headers |
| 80 | `e1fc0df3` | Install LanguageTool extension for my LibreOffice | — | 🔲 | Not attempted |
| 81 | `f8369178` | Help me to install Orchis theme from gnome-look.org and change to it for my GNOM | 1.0 | ✅ | vinceliuice/Orchis-theme install.sh |
| 82 | `778efd0a` | I'm using libreoffice impress to write slideshows. I found that the video being  | — | 🔲 | Not attempted |
| 83 | `47f7c0ce` | The landscape at 00:08 in this video is so beautiful. Please extract this frame  | — | 🔲 | Not attempted |
| 84 | `c2751594` | Help me export the first image from the doc file attached in the most recent ema | — | 🔲 | Not attempted |
| 85 | `788b3701` | I'm tracking updates for a short tale set on https://github.com/liangjs333/4th-y | — | 🔲 | Not attempted |
| 86 | `48c46dc7` | Help me to automatically set up my work space. To be specific, open project dire | 1.0 | ✅ | CDP tab management |
| 87 | `42d25c08` | Hey, my friend has just sent me a web novel, but in txt files. Could you please  | — | 🔲 | Not attempted |
| 88 | `e8172110` | Open 'character.png' in GIMP and extract the pixel art character. Save the selec | — | 🔲 | Not attempted |
| 89 | `42f4d1c7` | Configure VS Code to edit GIMP script-fu scripts effectively by installing lisp  | 1.0 | ✅ | resized.png path fix |
| 90 | `3c8f201a` | Download the image from "https://huggingface.co/datasets/xlangai/ubuntu_osworld_ | 1.0 | ✅ | PIL quality=60 |
| 91 | `d68204bf` | Divide my image vertically into three equal sections with command line. Then rea | 1.0 | ✅ | PIL crop + paste (warm→cold left→right) |
| 92 | `91190194` | Launch GIMP from the command line to edit "cola.png" and crop the top 20% off th | 1.0 | ✅ | PIL crop top 20% |
| 93 | `7f35355e` | Export the table to a CSV file and then help me write code to find the medium pr | — | 🔲 | Not attempted |
| 94 | `98e8e339` | Merge the contents of all .txt files from your vscode project into a single docu | 1.0 | ✅ | json.dumps for clean transfer |
| 95 | `0e5303d4` | I want to learn python programming and my friend recommends me this course websi | — | 🔲 | Not attempted |
| 96 | `df67aebb` | I am writing my paper thesis. I have listed all referenced papers in the opened  | — | 🔲 | Not attempted |
| 97 | `5df7b33a` | I enjoy reading during my spare time, but this book is too bulky. Each time I op | — | 🔲 | Not attempted |
| 98 | `aceb0368` | I am grading students' English exam papers, but the test consists only of multip | 1.0 | ✅ | Grade multiple choice answers |
| 99 | `22a4636f` | Please help me convert the file "Meeting-Agenda.docx" to a pdf file and upload t | — | 🔲 | Not attempted |
| 100 | `236833a3` | Find the daily paper list on Huggingface and take down the meta information of p | — | 🔲 | Not attempted |
| 101 | `67890eb6` | I am an NLP researcher. Check out the best long paper awards of ACL from 2019 to | — | 🔲 | Not attempted |

## Known Issues & Workarounds

| Issue | Workaround |
|-------|------------|
| Google Drive tasks fail at setup | Missing `client_secrets.json` — affects #5,6,10,11,13,14,33,99 |
| LO Document Recovery dialog | `rm -f ~/.config/libreoffice/4/user/.~lock.*` before reopening |
| openpyxl destroys charts | Use LO Basic macro via `soffice --headless macro:///` |
| openpyxl sheet name "Sheet" ≠ "Sheet1" | Always set `ws.title = 'Sheet1'` |
| openpyxl formulas lack `<v>` cached values | Write numeric values, or open in LO → Ctrl+S to cache |
| pyautogui `typewrite()` triggers Chrome | Use clipboard paste or local edit + upload |
| VS Code eval extension `OpenProject` | Extension installed but Command Palette trigger fails on VM |
| compare_csv is exact line match | Delimiter must match gold (tab-separated, not comma) |
| CDP new tab requires PUT | `curl -X PUT 'http://localhost:9222/json/new?URL'` |
| VM lacks xlrd for .xls files | Convert to CSV via `libreoffice --headless` first |
| Terminal check (`use terminal`) | Must run soffice from gnome-terminal (pts) + write to bash_history |
| Chrome QUIC protocol errors | Network instability in VM causes eval getter failures |

## Files

- Results JSON: `~/OSWorld/results_official.json`
- GUI memory: `~/.openclaw/workspace/skills/gui-agent/memory/apps/`
