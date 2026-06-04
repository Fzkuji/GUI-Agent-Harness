# OSWorld VS Code Domain - GPT-5.5 Run Errors

> 23 tasks | **31.3%** (5/16 officially scored) | completed 2026-05-18

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 23 |
| Run so far | 23 |
| Officially scored | 16 |
| Exact pass (1.0) | 5 |
| Partial credit | 0 |
| Numeric fail (0.0) | 11 |
| Eval error / N/A | 5 |
| Execution failure before evaluator | 2 |
| Not reached | 0 |
| Official scored rate | 31.3% (5/16) |
| Strict exact-pass rate | 21.7% (5/23) |

**Test environment:** Ubuntu VM at `172.16.105.130`, 1920x1080, `openai-codex/gpt-5.5` via GUI Agent Harness

**Run directory:** `runs/vs_code_all_20260518_072658`

**Wrong-domain attempt:** `runs/vscode_all_20260518_072629` contains argument-error logs from using `--domain vscode`. The valid runner domain key is `vs_code`.

**Command pattern:**

```bash
.venv/bin/python benchmarks/osworld/run_osworld_task.py <task_index> \
  --domain vs_code \
  --vm 172.16.105.130 \
  --max-steps 15 \
  --provider openai-codex \
  --model gpt-5.5
```

## Detailed Results

| # | Task ID | Instruction | Score | Steps | Time | Notes |
|---|---------|-------------|-------|-------|------|-------|
| 1 | 0ed39f63 | Replace all occurrences of text with test | no eval | - | 17s | App-learning bootstrap failed in `_batch_label()` with `Agent session failed` |
| 2 | 53ad5833 | Open the project folder under /home/user | no eval | - | 18s | App-learning bootstrap failed in `_batch_label()` with `Agent session failed` |
| 3 | eabc805a | Install the Python extension | 0.0 FAIL | 15 | 176s | Screenshot cascade and invalid image error; evaluator saw wrong/missing extension state |
| 4 | 982d12a5 | Change color theme to Visual Studio Dark | 1.0 PASS | 8 | 110s | Clean evaluator pass |
| 5 | 4e60007a | Install autoDocstring extension | 0.0 FAIL | 15 | 88s | Extension install did not satisfy evaluator; only other extensions listed |
| 6 | e2b5e914 | Disable Python missing imports diagnostics | 0.0 FAIL | 15 | 18s | Screenshot read cascade after first actions |
| 7 | 9439a27b | Keep cursor focused on debug console | 0.0 FAIL | 10 | 156s | Runner SUCCESS but evaluator score 0.0; likely wrong setting key/value |
| 8 | ea98c5d7 | Remove ctrl+f shortcut for Tree view Find | 0.0 FAIL | 15 | 252s | Evaluator reported missing `keybindings.json` |
| 9 | 930fdb3b | Create ctrl+j shortcut from terminal to editor | 0.0 FAIL | 15 | 239s | Keybindings file was written but did not satisfy evaluator |
| 10 | 276cc624 | Set current user's code wrapping line length to 50 | 0.0 FAIL | 9 | 132s | Runner SUCCESS but evaluator score 0.0 |
| 11 | 9d425400 | Wrap editor tabs over multiple lines | 1.0 PASS | 5 | 68s | Clean evaluator pass |
| 12 | 5e2d93d8 | Save current project as workspace project | 1.0 PASS | 6 | 73s | Passed despite noisy evaluator shell stderr |
| 13 | 6ed0a554 | Add data1 and data2 folders to current workspace | 1.0 PASS | 12 | 144s | Passed |
| 14 | ec71221e | Increase indent of lines 2-10 by one tab | 0.0 FAIL | 15 | 192s | HuggingFace retry during setup; screenshot cascade/invalid image conclusion |
| 15 | 70745df8 | Enable autosave with 500ms delay | 0.0 FAIL | 15 | 230s | Invalid image conclusion; setting did not satisfy evaluator |
| 16 | 57242fad | Create /home/user/Desktop/test.py via VS Code | 1.0 PASS | 7 | 74s | Passed despite noisy evaluator shell stderr |
| 17 | c6bf789c | Hide all __pycache__ folders in Explorer | 0.0 FAIL | 9 | 101s | Runner SUCCESS but evaluator score 0.0; workspace/user settings mismatch likely |
| 18 | 0512bb38 | Install local VSIX /home/user/test.vsix | 0.0 FAIL | 15 | 164s | HuggingFace SSL retry recovered setup; screenshot cascade; evaluator listed only `undefined_publisher.eval` |
| 19 | 847a96b6 | Open two workspace files | N/A EVAL_ERROR | 15 | 212s | Evaluator marked infeasible/unscorable |
| 20 | 7aeae0e2 | Visualize all numpy arrays in current Python file | N/A EVAL_ERROR | 15 | 172s | Evaluator marked infeasible/unscorable; screenshot cascade |
| 21 | dcbe20e8 | Change VS Code background to photo in Downloads | N/A EVAL_ERROR | 15 | 167s | Evaluator marked infeasible/unscorable; screenshot cascade and invalid image conclusion |
| 22 | 7c4cc09e | Change display language to Arabic without extensions | N/A EVAL_ERROR | 15 | 182s | Evaluator marked infeasible/unscorable; screenshot cascade and invalid image conclusion |
| 23 | 971cbb5b | Configure VS Code startup behavior | N/A EVAL_ERROR | 15 | 193s | Evaluator marked infeasible/unscorable; screenshot cascade |

## Error Details

| # | Primary failure | Secondary symptoms | Evaluator result | Log |
|---|-----------------|--------------------|------------------|-----|
| 1 | App-learning bootstrap failed before task actions | `exec() failed after 2 attempts in _batch_label()` | No evaluator run | `task_1.log` |
| 2 | App-learning bootstrap failed before task actions | `exec() failed after 2 attempts in _batch_label()` | No evaluator run | `task_2.log` |
| 3 | Extension state mismatch | Screenshot read cascade; invalid image HTTP 400; VS Code EROFS log mkdir errors | Score 0.0 | `task_3.log` |
| 4 | No blocking error observed | None material | PASS 1.0 | `task_4.log` |
| 5 | Extension install mismatch | `Agent session failed`; VS Code EROFS log mkdir errors | Score 0.0 | `task_5.log` |
| 6 | Settings change did not satisfy evaluator | Screenshot read cascade | Score 0.0 | `task_6.log` |
| 7 | Setting key/value mismatch | Runner SUCCESS but official metric failed | Score 0.0 | `task_7.log` |
| 8 | Keybinding removal not persisted at expected path | Evaluator 404 for `/home/user/.config/Code/User/keybindings.json` | Score 0.0 | `task_8.log` |
| 9 | Keybinding semantics mismatch | Runner wrote a keybinding but official metric failed | Score 0.0 | `task_9.log` |
| 10 | Setting mismatch | Runner SUCCESS but official metric failed | Score 0.0 | `task_10.log` |
| 11 | No blocking error observed | None material | PASS 1.0 | `task_11.log` |
| 12 | No blocking error observed | Evaluator emitted harmless `ls` stderr | PASS 1.0 | `task_12.log` |
| 13 | No blocking error observed | None material | PASS 1.0 | `task_13.log` |
| 14 | Text edit did not satisfy metric | HuggingFace retry; screenshot read cascade; invalid image conclusion | Score 0.0 | `task_14.log` |
| 15 | Autosave setting mismatch | Invalid image conclusion | Score 0.0 | `task_15.log` |
| 16 | No blocking error observed | Evaluator emitted harmless `ls` stderr | PASS 1.0 | `task_16.log` |
| 17 | User/workspace settings mismatch likely | Runner SUCCESS but official metric failed; model session errors | Score 0.0 | `task_17.log` |
| 18 | VSIX install mismatch | HuggingFace SSL retry; repeated file dialog attempts; screenshot read cascade | Score 0.0 | `task_18.log` |
| 19 | Task not automatically scorable | Repeated file dialog target misses | N/A / infeasible | `task_19.log` |
| 20 | Task not automatically scorable | `Agent session failed`; screenshot stack cascade | N/A / infeasible | `task_20.log` |
| 21 | Task not automatically scorable | Screenshot stack cascade; invalid image HTTP 400 | N/A / infeasible | `task_21.log` |
| 22 | Task not automatically scorable | Screenshot stack cascade; invalid image HTTP 400 | N/A / infeasible | `task_22.log` |
| 23 | Task not automatically scorable | `Agent session failed`; screenshot stack cascade | N/A / infeasible | `task_23.log` |

## Error Categories

| Category | Affected tasks | Evidence | Notes |
|----------|----------------|----------|-------|
| Opaque model/session failure | 1-3, 5-10, 14, 17-18, 20-23 | `RuntimeError: Agent session failed` | Severe in VS Code. Tasks 1-2 failed before evaluator because base memory learning could not complete. |
| Invalid image passed to model | 3, 14-15, 18, 20-22 | OpenAI HTTP 400 invalid image | Same failure pattern as GIMP/Writer runs after screenshot artifacts become unusable. |
| Screenshot/read cascade | 3, 6, 14, 18, 20-23 | `WARNING Image Read Error /tmp/gui_agent_screen.png`; `need at least one array to stack` | Often consumed all remaining steps once triggered. |
| Runner success but evaluator fail | 7, 10, 17 | Runner prints SUCCESS while official score is 0.0 | Evaluator remains benchmark truth. |
| HuggingFace asset download instability | 14, 18 | SSL EOF / retry messages | Setup recovered on task 18 after retry. |
| VS Code read-only log noise | 3, 5, 18 | `EROFS: read-only file system, mkdir '/home/user/.config/Code/logs/...'` | Did not directly abort evaluation, but appeared in extension-related evaluator commands. |
| Infeasible / unscorable task | 19-23 | Evaluator returns N/A / infeasible | Exclude from official scored rate unless manually scoring. |
| Domain-key mismatch | wrong-domain run only | `ValueError: Domain 'vscode' not found` | Use `--domain vs_code`, while docs/results use the human-readable `vscode` filename convention. |

## Handoff Notes

- Final VS Code accounting: 5 exact PASS, 11 numeric FAIL, 5 evaluator N/A/infeasible, and 2 early execution failures before evaluator.
- Official scored total is 5/16 (31.3%). Strict exact-pass count over all attempted tasks is 5/23 (21.7%).
- Treat official evaluator score as benchmark truth. Tasks 7, 10, and 17 reported runner SUCCESS while scoring 0.0.
- Tasks 1-2 should be rerun only if explicitly doing a repair/rerun pass; they failed during app-learning bootstrap, not task execution.
- The same recurring model issues from GIMP/Writer appeared: `Agent session failed`, invalid image HTTP 400, screenshot stack cascades, and HuggingFace download instability.
- Next domain candidates with existing docs and no GPT-5.5 result doc: `libreoffice_calc` or `libreoffice_impress`.
