# OSWorld VLC Domain - GPT-5.5 Run Errors

> 17 tasks | **56.3%** (7.876/14 officially scored) | 2026-05-18

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 17 |
| Run so far | 17 |
| Officially scored | 14 |
| Pass (1.0) | 7 |
| Numeric fail (0.0) | 6 |
| Partial | 1 |
| Eval hang / no score | 1 |
| Eval error / N/A | 2 |
| Not reached | 0 |
| Official scored pass rate | 56.3% (7.876/14) |
| Full-domain pass count | 46.3% (7.876/17) |

**Test environment:** Ubuntu VM at `172.16.105.130`, 1920x1080, `openai-codex/gpt-5.5` via GUI Agent Harness

**Run directory:** `runs/vlc_all_20260518_0310`

**Command pattern:**

```bash
.venv/bin/python benchmarks/osworld/run_osworld_task.py <task_index> \
  --domain vlc \
  --vm 172.16.105.130 \
  --max-steps 15 \
  --provider openai-codex \
  --model gpt-5.5
```

## Detailed Results

| # | Task ID | Instruction | Score | Steps | Time | Notes |
|---|---------|-------------|-------|-------|------|-------|
| 1 | 59f21cfb | Play desktop music video in VLC | 1.0 PASS | 6 | 72s | Passed after several early `Agent session failed` planning/verification errors |
| 2 | 8ba5ae7a | Set VLC recordings folder to Desktop | 1.0 PASS | 8 | 150s | Clean GUI path through Preferences > Input/Codecs |
| 3 | 8f080098 | Convert music video song to MP3 | 0.0 FAIL | 15 | 284s | Loaded source video but got stuck around the profile dropdown; evaluator could not find `Baby Justin Bieber.mp3` |
| 4 | bba3381f | Start streaming Apple HLS URL in VLC | 1.0 PASS | 10 | 152s | Recovered from a model/session target lookup failure; evaluator saw VLC playing `master.m3u8` |
| 5 | fba2c100 | Save current video scene as `interstellar.png` on Desktop | 0.876 PARTIAL | 15 | 162s | Output file existed and downloaded; evaluator gave partial image match score after snapshot/rename/drag flow |
| 6 | efcf0d81 | Make current video frame the desktop background | no score / EVAL_HANG | 15 | 191s | Runner hit screenshot read cascade; evaluator hung after `Got wallpaper successfully` and was terminated after >7 min |
| 7 | 8d9fd4e2 | Enable fullscreen mode in VLC | 1.0 PASS | 3 | 32s | Recovered from first-step `Agent session failed`; evaluator verified fullscreen size |
| 8 | aa4b5023 | Flip video right-way-up and save output | 0.0 FAIL | 8 | 141s | Runner printed SUCCESS, but evaluator could not find expected `/home/user/1984_Apple_Macintosh_Commercial.mp4` |
| 9 | 386dbd0e | Change Play/Pause hotkey while reading PDF | 0.0 FAIL | 15 | 280s | Hotkey preference flow did not satisfy `vlcrc` evaluator; repeated verification model errors |
| 10 | 9195653c | Increase VLC maximum volume above normal | 0.0 FAIL | 15 | 282s | Screenshot read cascade after opening Preferences; `vlcrc` evaluator scored 0.0 |
| 11 | d06f0d4d | Change volume slider color to black-ish | 0.0 FAIL | 15 | 232s | Runner printed SUCCESS after editing advanced Qt volume color field, but `vlcrc` evaluator scored 0.0 |
| 12 | a5bbbcd5 | Enable Minimal Interface in window mode | 1.0 PASS | 11 | 120s | Recovered from early verifier errors; evaluator confirmed minimal-interface setting |
| 13 | 5ac2891a | Stop VLC auto-closing at video end | 1.0 PASS | 8 | 76s | Enabled “Pause on the last frame of a video”; evaluator confirmed `vlcrc` |
| 14 | f3977615 | Allow multiple VLC instances | 1.0 PASS | 5 | 72s | Disabled “use only one instance when started from file manager”; evaluator confirmed `vlcrc` |
| 15 | 215dfd39 | Disable cone icon in splash screen | 0.0 FAIL | 15 | 338s | Searched advanced settings and scrolled Qt options, but did not reach/set the expected splash cone option |
| 16 | cb130f0d | Automatically adjust video brightness/contrast | N/A EVAL_ERROR | 15 | 389s | Evaluator marked infeasible; runner adjusted image controls but could not be automatically scored |
| 17 | 7882ed6e | Play latest purchased Stranger Things season from Google Play Movies | N/A EVAL_ERROR | 15 | 487s | Evaluator marked infeasible; runner tried VLC network stream and web search flow; many model session errors |

## Error Details

| # | Primary failure | Secondary symptoms | Evaluator result | Log |
|---|-----------------|--------------------|------------------|-----|
| 1 | Multiple `plan_next_action()` / `verify_step()` model errors | Recovered by known component match and double-clicked desktop video | PASS; VLC status playing | `task_1.log` |
| 2 | No blocking error observed | Missing proxy config warning only | PASS; `vlcrc` recording path verified | `task_2.log` |
| 3 | Failed to select the MP3 conversion profile and start export | Repeated clicks on/near profile field; no output file created | Missing `/home/user/Desktop/Baby Justin Bieber.mp3`; score 0.0 | `task_3.log` |
| 4 | `find_target_in_known()` returned `Agent session failed` once | First URL open attempt showed an error dialog, then retry succeeded | PASS; VLC status playing and URL filename matched | `task_4.log` |
| 5 | Snapshot was created, renamed, and moved, but content did not fully match reference | Four early `verify_step()` model errors; exhausted 15 steps | Partial score 0.876; file saved as `cache/eval_fba2c100/interstellar.png` | `task_5.log` |
| 6 | Evaluator hang after retrieving wallpaper | Screenshot read cascade on steps 9-15; conclusion got HTTP 400 invalid image | No official score printed; terminated hung evaluator/run | `task_6.log` |
| 7 | `plan_next_action()` returned `Agent session failed` on step 1 | Recovered by clicking known fullscreen toggle | PASS; screen/window sizes matched fullscreen | `task_7.log` |
| 8 | Expected output video was missing | Runner used a terminal/ffmpeg route and ended with runner SUCCESS | Missing `/home/user/1984_Apple_Macintosh_Commercial.mp4`; score 0.0 | `task_8.log` |
| 9 | Hotkey change did not match evaluator expectation | HuggingFace SSL retries during setup; repeated `verify_step()` model errors on steps 9-13 | `vlcrc` downloaded and checked; score 0.0 | `task_9.log` |
| 10 | Preference change did not match evaluator expectation | `plan_next_action()` model errors; screenshot read cascade on steps 5-15; conclusion got HTTP 400 invalid image | `vlcrc` downloaded and checked; score 0.0 | `task_10.log` |
| 11 | Advanced Qt volume color edit did not match evaluator expectation | Runner typed `0;0;0` into the volume slider color field and ended SUCCESS | `vlcrc` downloaded and checked; score 0.0 | `task_11.log` |
| 12 | Early `verify_step()` model errors | Recovered through Preferences and View > Minimal Interface flow | PASS; `vlcrc` downloaded and checked | `task_12.log` |
| 13 | Early `verify_step()` model errors | Recovered by enabling “Pause on the last frame of a video” and saving | PASS; `vlcrc` downloaded and checked | `task_13.log` |
| 14 | No blocking error observed | Standard Preferences flow | PASS; `vlcrc` downloaded and checked | `task_14.log` |
| 15 | Did not find or set the expected splash cone option | Spent steps 10-15 scrolling in advanced Qt settings | `vlcrc` downloaded and checked; score 0.0 | `task_15.log` |
| 16 | Automatic evaluator marked task infeasible | Multiple model/session errors while adjusting VLC brightness/contrast controls | Score N/A; runner failed | `task_16.log` |
| 17 | Automatic evaluator marked task infeasible | Repeated `plan_next_action()` / `verify_step()` model errors; attempted network stream and Google search path | Score N/A; runner failed | `task_17.log` |

## Error Categories

| Category | Affected tasks | Evidence | Notes |
|----------|----------------|----------|-------|
| Opaque model/session failure | 1, 4, 5, 6, 7, 9, 10, 12, 13, 16, 17 | `RuntimeError: Agent session failed` | Not always fatal; tasks 6 and 10 cascaded into unreadable screenshots. |
| Output missing | 3, 8 | Evaluator could not retrieve expected output file | Task 3 missed MP3 export; task 8 missed expected MP4 path. |
| Partial content mismatch | 5 | Evaluator scored saved snapshot at 0.876 | File placement/name were correct, but image match was imperfect. |
| Evaluator hang | 6 | Evaluator printed `Got wallpaper successfully` and then stopped producing output for >7 min | Terminated to avoid blocking the continuous run. |
| Invalid image passed to model | 6, 10 | OpenAI HTTP 400: image data is not a valid image | Appeared during conclusion after screenshot read failures. |
| Screenshot/read cascade | 6, 10 | `WARNING Image Read Error /tmp/gui_agent_screen.png`; `ValueError: need at least one array to stack` | Repeated after GUI navigation failures. |
| Runner success but evaluator fail | 8, 11 | Runner prints SUCCESS while official evaluator returns 0.0 | Treat evaluator as source of truth. |
| Profile/dropdown interaction failure | 3 | Repeated attempts to click the VLC Convert profile field | Likely needs stronger VLC-specific memory or direct profile-selection strategy. |
| Preference mismatch | 9, 10, 11, 15 | `vlcrc` evaluator returned score 0.0 after preference edit flows | The visible flow changed something or got stuck, but not the exact expected settings. |
| Infeasible / unscorable tasks | 16, 17 | Evaluator returns N/A / infeasible | Exclude from official scored pass rate unless manually scored. |
| HuggingFace asset download instability | 9 | SSL EOF retries during setup | Setup recovered. |
| Missing proxy config warning | 1-17 | `evaluation_examples/settings/proxy/dataimpulse.json` not found | Non-blocking for current VLC tasks. |

## Handoff Notes

- VLC complete: 7 PASS, 6 numeric FAIL, 1 partial score, 1 evaluator hang/no score, and 2 evaluator N/A/infeasible.
- Official scored pass rate is 7.876/14; full-domain non-pass accounting is 7.876/17.
- Treat official evaluator score as benchmark truth. Task 3 conclusion sounded partially successful, but official score is 0.0 because the MP3 file was missing.
- Task 8 also printed runner SUCCESS, but official score is 0.0 because the expected MP4 file was missing.
- Task 11 printed runner SUCCESS, but official score is 0.0 because the expected `vlcrc` setting was not present.
- Task 5 is not a pass despite correct filename/location because the official score is 0.876.
- Task 6 has no numeric score because the evaluator hung after retrieving wallpaper; keep it separate from numeric fail until rerun or evaluator diagnosis.
- Decide whether task 6 should be rerun or kept as evaluator-hang/no-score in downstream reporting.
- Decide whether infeasible/unscorable tasks 16-17 should be manually scored, excluded, or counted as non-pass in downstream reporting.
- VLC task count in official `test_all.json` is 17; the older `benchmarks/osworld/vlc.md` says 15 and should not be used as the task count for this GPT-5.5 run.
