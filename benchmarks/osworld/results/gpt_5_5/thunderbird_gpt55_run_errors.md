# OSWorld Thunderbird Domain - GPT-5.5 Run Errors

> 15 tasks | **46.2%** (6/13 officially scored) | completed 2026-05-18

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 15 |
| Run so far | 15 |
| Officially scored | 13 |
| Pass (1.0) | 6 |
| Numeric fail (0.0) | 7 |
| Eval error / N/A | 2 |
| Not reached | 0 |
| Official scored pass rate | 46.2% (6/13) |
| Full-domain pass rate | 40.0% (6/15) |

**Test environment:** Ubuntu VM at `172.16.105.130`, 1920x1080, `openai-codex/gpt-5.5` via GUI Agent Harness

**Run directory:** `runs/thunderbird_all_20260518_0442`

**Command pattern:**

```bash
.venv/bin/python benchmarks/osworld/run_osworld_task.py <task_index> \
  --domain thunderbird \
  --vm 172.16.105.130 \
  --max-steps 15 \
  --provider openai-codex \
  --model gpt-5.5
```

## Detailed Results

| # | Task ID | Instruction | Score | Steps | Time | Notes |
|---|---------|-------------|-------|-------|------|-------|
| 1 | dfac9ee8 | Remove account `anonym-x2024@outlook.com` | N/A EVAL_ERROR | 15 | 181s | Runner hit immediate model failure then screenshot-read cascade; evaluator setup failed uploading `firefox_decrypt.py` to read-only VM Desktop |
| 2 | 15c3b339 | Access Outlook account `anonym-x2024@outlook.com` | 0.0 FAIL | 15 | 131s | Same immediate model failure and screenshot-read cascade; evaluator accessibility tree did not find account |
| 3 | 7b1e1ff9 | Open Thunderbird profile management tabpage | 0.0 FAIL | 15 | 556s | Reached Troubleshooting Information but did not open expected About Profiles tab; repeated model session errors |
| 4 | 9bc3cc16 | Back up inbox email files to `~/emails.bak` | 0.0 FAIL | 15 | 156s | Started save/export flow and created folder name, but screenshot cascade prevented completion; evaluator found `/home/user/emails.bak` missing |
| 5 | 3f28fe4f | Set plain text account signature | 1.0 PASS | 7 | 67s | Reached Account Settings signature field and entered two-line signature; evaluator confirmed prefs |
| 6 | 5203d847 | Create local folder `Promotions` and filter matching inbox email subjects | 0.0 FAIL | 15 | 200s | Created local folder and opened filter editor, but did not finish filter rules/actions before step budget; evaluator found only a 25-byte `msgFilterRules.dat` |
| 7 | dd84e895 | Add a star to every email in local `Bills` folder | 0.0 FAIL | 15 | 167s | Starred at least one row, but mis-targeted later star clicks and switched focus to GIMP; screenshot-read cascade stopped the run before all messages were starred |
| 8 | 9b7bc335 | Forward every future email received by `anonym-x2024@outlook.com` | 1.0 PASS | 15 | 226s | Created `Forward all mail` filter, matched all messages, selected forward action, entered `anonym-x2024@gmail.com`, and saved it |
| 9 | d38192b0 | Attach `~/aws-bill.pdf` to the existing AWS bill email draft | 1.0 PASS | 8 | 82s | Opened attachment picker, selected `aws-bill.pdf`, and left the draft open; evaluator helper confirmed the attachment |
| 10 | a10b69e1 | Create local folders `COMPANY` and `UNIVERSITY` | 1.0 PASS | 9 | 108s | Created both folders under Local Folders; evaluator `ls -R` found both folder files and `.msf` indexes |
| 11 | 3f49d2cc | Enable unified folder view for multiple accounts | 1.0 PASS | 6 | 79s | Navigated app menu to View > Folders > Unified Folders; evaluator confirmed `xulstore.json` state |
| 12 | f201fbc3 | Disable quote block style for replies | 0.0 FAIL | 9 | 300s | Runner marked success but evaluator failed; advanced preference row showed corrupted value text after clicks instead of expected quote setting |
| 13 | 10a730d5 | Enable full dark mode in Thunderbird | 1.0 PASS | 7 | 109s | Navigated Add-ons Manager > Themes and enabled the Dark theme; evaluator confirmed prefs |
| 14 | a1af9f1c | Do not configure an incoming mail server due security considerations | N/A EVAL_ERROR | 15 | 53s | Evaluator marked task infeasible; runner hit model failure and screenshot-read cascade after dismissing/canceling dialogs |
| 15 | 08c73485 | Apply incoming filters to subfolders | 0.0 FAIL | 15 | 318s | Opened Config Editor and searched `mail.server.default.applyIncomingFilters`, but failed to reliably create/set the Boolean preference before step budget |

## Error Details

| # | Primary failure | Secondary symptoms | Evaluator result | Log |
|---|-----------------|--------------------|------------------|-----|
| 1 | `plan_next_action()` returned `Agent session failed` on step 1 | Screenshot read cascade on steps 2-15; conclusion got HTTP 400 invalid image | Evaluator setup failed: upload to `/home/user/Desktop/firefox_decrypt.py` returned read-only filesystem; score N/A | `task_1.log` |
| 2 | `plan_next_action()` returned `Agent session failed` on step 1 | Screenshot read cascade on steps 2-15; conclusion had one `Agent session failed` and one HTTP 400 invalid image | Evaluator checked accessibility tree and did not find `anonym-x2024@outlook.com`; score 0.0 | `task_2.log` |
| 3 | About Profiles tab was not opened | Heavy HuggingFace setup retries; repeated `verify_step()` / `plan_next_action()` model errors after opening Troubleshooting Information | Evaluator did not find `page-tab[name="About Profiles"]`; score 0.0 | `task_3.log` |
| 4 | Expected backup directory was missing | One verifier model error; screenshot read cascade on steps 12-15; conclusion got HTTP 400 invalid image | `ls -R /home/user/emails.bak` failed; score 0.0 | `task_4.log` |
| 5 | Early model/session verifier failures | Recovered and typed `Anonym\nXYZ Lab` into the account signature field | PASS; downloaded prefs file matched expected signature | `task_5.log` |
| 6 | Filter creation incomplete | Created `Promotions` local folder and entered filter name; final `plan_next_action()` failed with repeated `Agent session failed` | Evaluator downloaded 25-byte `msgFilterRules.dat`; score 0.0 | `task_6.log` |
| 7 | Not all Bills messages were starred | Mis-targeted star coordinates clicked outside Thunderbird and focused GIMP; steps 9-15 hit screenshot-read cascade; conclusion got HTTP 400 invalid image | Evaluator downloaded `global-messages-db.sqlite`; score 0.0 | `task_7.log` |
| 8 | Early model/session failures but task recovered | First three steps failed with `Agent session failed`; later steps built the filter successfully within step budget | PASS; downloaded 143-byte `msgFilterRules.dat` matched expected forwarding rule | `task_8.log` |
| 9 | Early verifier failures but task recovered | Attachment picker flow succeeded after three verifier `Agent session failed` errors | PASS; evaluator installed helper and reported `Attachment added!` for `aws-bill.pdf` | `task_9.log` |
| 10 | None significant | Created `COMPANY` and `UNIVERSITY` folders via Local Folders context menu | PASS; evaluator `ls -R` found both folders | `task_10.log` |
| 11 | Minor verifier failure but task recovered | One verifier `Agent session failed`; setup had HuggingFace SSL retries before recovering | PASS; downloaded `xulstore.json` confirmed unified folder state | `task_11.log` |
| 12 | Runner success but evaluator fail | Opened Config Editor and searched `mail.quoteasblock`, but clicked/editing the value left row text looking like `ErU9`; conclusion failed with `Agent session failed` | Evaluator downloaded `thunder-prefs.js`; score 0.0 | `task_12.log` |
| 13 | None significant | Opened Add-ons Manager, selected Themes, and enabled Dark theme | PASS; evaluator downloaded `thunder-prefs.js` and scored 1.0 | `task_13.log` |
| 14 | Evaluator infeasible and runner cascade | After Cancel/dismiss actions, step 2 hit `Agent session failed`; steps 5-15 hit screenshot-read cascade; conclusion got HTTP 400 invalid image | Official evaluator returned infeasible / score N/A | `task_14.log` |
| 15 | Preference creation incomplete | Recovered from early model failures and reached Config Editor, but locating/clicking the plus button for `mail.server.default.applyIncomingFilters` had repeated component-label/session failures | Evaluator downloaded `thunder-prefs.js`; score 0.0 | `task_15.log` |

## Error Categories

| Category | Affected tasks | Evidence | Notes |
|----------|----------------|----------|-------|
| Opaque model/session failure | 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15 | `RuntimeError: Agent session failed` | Triggered immediate execution collapse on tasks 1-2 and slowed later tasks; some tasks recovered before final scoring. |
| Screenshot/read cascade | 1, 2, 4, 7, 14 | `WARNING Image Read Error /tmp/gui_agent_screen.png`; `ValueError: need at least one array to stack` | Started after model/GUI failure or bad window focus. |
| Invalid image passed to model | 1, 2, 4, 7, 14 | OpenAI HTTP 400: image data is not a valid image | Appeared during conclusion after screenshot read failures. |
| GUI target drift / wrong window focus | 7 | Star-click targets landed outside Thunderbird and focused GIMP | Caused task 7 to lose the active app before the screenshot cascade. |
| Output missing | 4 | Evaluator could not find `/home/user/emails.bak` | Export/backup flow did not complete. |
| Incomplete app configuration | 6 | Evaluator found only a minimal `msgFilterRules.dat` | Local folder was created but message filter rules were not completed. |
| Runner success after early failures | 5, 8, 9, 11 | Official evaluator returned 1.0 despite early model/session errors | Shows early `Agent session failed` is not always fatal when later steps recover. |
| Runner success but evaluator fail | 12 | Runner printed `Task 12: SUCCESS`, official score was 0.0 | Record official evaluator score as benchmark truth. |
| Advanced preference mis-edit | 12 | `mail.quoteasblock` row value text became `ErU9` before final toggle | Config Editor interaction did not produce expected setting. |
| Advanced preference creation incomplete | 15 | `mail.server.default.applyIncomingFilters` plus-button targeting failed after Phase 3 fallback | Config Editor interaction did not create/set expected Boolean preference. |
| Evaluator setup failure | 1 | Upload failed with status 500: read-only filesystem at `/home/user/Desktop/firefox_decrypt.py` | Separate from runner failure; official score is N/A. |
| Infeasible / evaluator N/A | 14 | Evaluator printed `infeasible (task cannot be scored automatically)` | Official score is N/A. |
| HuggingFace asset download instability | 1, 3, 7, 11, 15 | SSL EOF retries while downloading task assets | Downloads recovered after retries/curl fallback where applicable. |
| Missing proxy config warning | 1-15 | `evaluation_examples/settings/proxy/dataimpulse.json` not found | Non-blocking so far. |

## Handoff Notes

- Thunderbird GPT-5.5 run is complete: 6 pass, 7 numeric fail, 2 N/A/infeasible.
- Official `test_all.json` lists 15 Thunderbird tasks; the older `benchmarks/osworld/thunderbird.md` says 24 and is stale.
- Treat official evaluator score as benchmark truth. Task 1 has no score because evaluator setup failed after runner failure; task 14 is official infeasible/N/A.
- Watch for VM filesystem state. Task 1 evaluator could not upload to `/home/user/Desktop/firefox_decrypt.py` due to a read-only filesystem.
