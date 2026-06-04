# OSWorld LibreOffice Writer Domain - GPT-5.5 Run Errors

> 23 tasks | **31.8%** (6.998/22 officially scored) | completed 2026-05-18

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 23 |
| Run so far | 23 |
| Officially scored | 22 |
| Exact pass (1.0) | 6 |
| Partial credit | 0.998 |
| Numeric fail (0.0) | 15 |
| Eval error / N/A | 1 |
| Not reached | 0 |
| Official scored rate | 31.8% (6.998/22) |
| Strict exact-pass rate | 27.3% (6/22) |

**Test environment:** Ubuntu VM at `172.16.105.130`, 1920x1080, `openai-codex/gpt-5.5` via GUI Agent Harness

**Run directory:** `runs/libreoffice_writer_all_20260518_060920`

**Command pattern:**

```bash
.venv/bin/python benchmarks/osworld/run_osworld_task.py <task_index> \
  --domain libreoffice_writer \
  --vm 172.16.105.130 \
  --max-steps 15 \
  --provider openai-codex \
  --model gpt-5.5
```

## Detailed Results

| # | Task ID | Instruction | Score | Steps | Time | Notes |
|---|---------|-------------|-------|-------|------|-------|
| 1 | 0810415c | Make first two paragraphs double line spacing | 0.0 FAIL | 8 | 111s | Runner SUCCESS but evaluator score 0.0 |
| 2 | 0a0faba3 | First three words left-aligned, rest right-aligned | 0.0 FAIL | 15 | 180s | Screenshot read cascade; invalid image at conclusion |
| 3 | 0b17a146 | Change 2 in H2O to subscript | 0.0 FAIL | 10 | 117s | Runner SUCCESS but evaluator score 0.0; model session errors |
| 4 | 0e47de2a | Add page number at bottom left | 1.0 PASS | 9 | 103s | Clean evaluator pass |
| 5 | 0e763496 | Change all text to Times New Roman | 0.0 FAIL | 15 | 152s | Model errors; invalid image at conclusion |
| 6 | 3ef2b351 | Center-align heading | 1.0 PASS | 2 | 29s | Fast shortcut path passed |
| 7 | 4bcb1253 | Export current document as PDF | 0.998 PARTIAL | 6 | 48s | Exported PDF; evaluator found partial mismatch after checking alternate expected paths |
| 8 | 66399b0d | Insert empty 7x5 table | 0.0 FAIL | 15 | 175s | Reached table dialog but did not produce expected table |
| 9 | 6a33f9b9 | Remove yellow highlighting | 1.0 PASS | 15 | 116s | Passed despite multiple model/session errors |
| 10 | 6ada715d | Insert desktop screenshot 1.png at cursor | 0.0 FAIL | 5 | 171s | Runner SUCCESS but evaluator score 0.0; invalid image conclusion |
| 11 | 6f81754e | Edit train signaling record | 0.0 FAIL | 9 | 199s | Evaluator reported duplicate train IDs |
| 12 | 72b810ef | Strike through last paragraph | 0.0 FAIL | 7 | 208s | Runner SUCCESS but evaluator score 0.0 |
| 13 | 8472fece | Color word-list vowels/consonants | 0.0 FAIL | 15 | 372s | Terminal/script route failed; screenshot read cascade |
| 14 | 88fe4b2d | Split first paragraph into sentences | 0.0 FAIL | 15 | 433s | Text became corrupted; evaluator score 0.0 |
| 15 | 936321ce | Convert comma-separated text to table | 0.0 FAIL | 15 | 315s | Repeated menu attempts; conclusion model error |
| 16 | adf5e2c3 | Add Steinberg reference | 0.0 FAIL | 14 | 201s | Runner SUCCESS but evaluator score 0.0 |
| 17 | b21acd93 | Format paragraph indentation/spacing | 0.0 FAIL | 15 | 318s | Many early session failures; evaluator score 0.0 |
| 18 | d53ff5ee | Convert uppercase text to lowercase | 1.0 PASS | 6 | 81s | Clean Format > Text > lowercase path |
| 19 | e246f6d8 | Make italic text easier to discern | 0.0 FAIL | 15 | 230s | Find/replace formatting path failed to satisfy evaluator |
| 20 | e528b65e | Capitalize every word | 1.0 PASS | 8 | 69s | Passed after early model/session failures |
| 21 | ecc2413d | Insert blank page after current one | 1.0 PASS | 3 | 36s | Passed; setup needed HuggingFace retries |
| 22 | f178a4a9 | Make Times New Roman the default font | 0.0 FAIL | 10 | 117s | Changed document text, but evaluator checked default registry config |
| 23 | bb8ccc78 | Share document for real-time team editing | N/A EVAL_ERROR | 15 | 213s | Evaluator marked infeasible/unscorable |

## Error Details

| # | Primary failure | Secondary symptoms | Evaluator result | Log |
|---|-----------------|--------------------|------------------|-----|
| 1 | Formatting shortcut did not satisfy metric | Runner still printed SUCCESS | Score 0.0 | `task_1.log` |
| 2 | Screenshot became unreadable after Find/Replace flow | HTTP 400 invalid image; HuggingFace retry | Score 0.0 | `task_2.log` |
| 3 | Subscript operation did not satisfy metric | Repeated `Agent session failed`; HuggingFace retries | Score 0.0 | `task_3.log` |
| 4 | No blocking error observed | None material | PASS 1.0 | `task_4.log` |
| 5 | Font selection did not satisfy metric | Multiple model errors; HTTP 400 invalid image | Score 0.0 | `task_5.log` |
| 6 | No blocking error observed | Non-material file-check noise | PASS 1.0 | `task_6.log` |
| 7 | Export path/name/content nearly matched but not exact | Model errors; evaluator 404s on alternate expected locations | PARTIAL 0.998 | `task_7.log` |
| 8 | Table dialog not completed correctly | Early `verify_step()` session failures | Score 0.0 | `task_8.log` |
| 9 | No final failure | Many `Agent session failed` verification errors; HuggingFace retry | PASS 1.0 | `task_9.log` |
| 10 | Insert-image action did not satisfy metric | HTTP 400 invalid image at conclusion | Score 0.0 | `task_10.log` |
| 11 | Semantic edit incorrect | Evaluator: duplicate train IDs | Score 0.0 | `task_11.log` |
| 12 | Strikethrough target/edit mismatch | Model planning and verification errors | Score 0.0 | `task_12.log` |
| 13 | Script/terminal route failed to complete cleanly | `Agent session failed`; screenshot stack cascade | Score 0.0 | `task_13.log` |
| 14 | Text corruption during sentence splitting | Many model errors; undo attempts did not recover | Score 0.0 | `task_14.log` |
| 15 | Convert-to-table menu flow did not complete | Conclusion model error | Score 0.0 | `task_15.log` |
| 16 | Reference insertion content/location mismatch | Runner SUCCESS but official metric failed | Score 0.0 | `task_16.log` |
| 17 | Formatting operations did not satisfy metric | Early repeated model errors | Score 0.0 | `task_17.log` |
| 18 | No blocking error observed | None material | PASS 1.0 | `task_18.log` |
| 19 | Find/replace formatting did not apply required transformation | Target lookup model error | Score 0.0 | `task_19.log` |
| 20 | No final failure | Early model errors recovered | PASS 1.0 | `task_20.log` |
| 21 | No final failure | HuggingFace download retries during setup | PASS 1.0 | `task_21.log` |
| 22 | Wrong target: document font changed, default font registry not changed | Runner SUCCESS but evaluator inspected `registrymodifications.xcu` | Score 0.0 | `task_22.log` |
| 23 | Task not automatically scorable | HuggingFace retries; remote/share UI exploration | N/A / infeasible | `task_23.log` |

## Error Categories

| Category | Affected tasks | Evidence | Notes |
|----------|----------------|----------|-------|
| Opaque model/session failure | 2, 3, 5, 7-9, 11-17, 19-20, 22-23 | `RuntimeError: Agent session failed` | Frequent and often recoverable, but it wastes steps and sometimes pushes the agent into bad UI state. |
| Invalid image passed to model | 2, 5, 10 | OpenAI HTTP 400 invalid image | Same failure pattern as GIMP/VLC/Thunderbird runs after screenshot artifacts become unusable. |
| Screenshot/read cascade | 2, 13 | `WARNING Image Read Error /tmp/gui_agent_screen.png`; `need at least one array to stack` | Less frequent than GIMP but still present. |
| Runner success but evaluator fail | 1, 3, 10, 12, 16, 22 | Runner prints SUCCESS while official score is 0.0 | Evaluator remains benchmark truth. |
| HuggingFace asset download instability | 2, 3, 5, 7, 9, 11, 21, 23 | SSL EOF / retry messages | Setup generally recovered; task 23 required curl fallback after repeated failures. |
| Semantic/document-edit mismatch | 11, 14, 16, 17, 19, 22 | Evaluator-specific mismatch messages or 0.0 scores after completed actions | Failures often came from using visible GUI shortcuts that did not match the exact underlying document property expected. |
| Infeasible / unscorable task | 23 | Evaluator returns N/A / infeasible | Exclude from official scored rate unless manually scoring. |

## Handoff Notes

- Final Writer accounting: 6 exact PASS, 1 partial 0.998, 15 numeric FAIL, 1 evaluator N/A/infeasible.
- Official scored total is 6.998/22 (31.8%). Strict exact-pass count is 6/22 (27.3%).
- Treat official evaluator score as benchmark truth. Several tasks reported runner SUCCESS while scoring 0.0.
- The same recurring model issues from GIMP/VLC/Thunderbird appeared: `Agent session failed`, invalid image HTTP 400, screenshot stack cascades, and HuggingFace download instability.
- Task 22 is a useful example of UI-vs-config mismatch: the agent changed selected document text to Times New Roman, but the evaluator checked LibreOffice default font configuration.
- Next domain candidates with existing docs and no GPT-5.5 result doc: `libreoffice_calc`, `libreoffice_impress`, or `vscode`. Calc/Impress are larger; VS Code is 23 tasks.

