# ScreenSpot Iterative Zoom Pipeline State

Last updated: 2026-05-31 19:35 HKT

Operating rule from Fz: keep going. If the foreground session is interrupted, resume from this state or let the watchdog cron continue. Do not stop at intermediate reports.
Progress reporting: cron `ca594d68-9dd3-4e0e-8641-05092866bc86` is now every 10 minutes and must send a Discord-visible progress update each run, even when the experiment is still active. Each report must include progress, counts, active/last samples, and all current wrong cases. It should only generate/send visualizations for newly appeared wrong cases that have not already been visualized.

Current method:
- `GUI_HARNESS_SCREENSPOT_LOCATOR_MODE=iterative_zoom`
- Main path is pure instruction by default. `--meta-brief` is off, and metadata
  context is now an explicit ablation flag rather than default behavior.
- Up to 5 crop rounds, then final upsampled crop for click selection.
- Current prompt policy is restricted to generic GUI grounding behavior:
  iterative narrowing, target identity, actionable controls over passive
  labels/status text, and review preserving direct editable controls. Narrow
  app/subset/sample-oriented rules have been removed.

Current evidence:
- Smoke no-meta: 4/4 correct.
- All-annotation index-0 sweep before target-lock/review: 21/26 correct, 4 wrong, 1 wrong_format.
- Earlier small hardcase regressions are not sufficient evidence. Treat them as
  debugging traces only, not optimization targets.
- Best completed broad check so far: 26 annotation index0 run with target-lock +
  final review = 24/26 correct (92.3%).

Concurrent run:
- At 17:27 HKT, an older ScreenSpot crop-first by-subset sweep is still running in screen `screenspot_by_subset_meta_soft_gate_cropfirst_conda_20260530_2107` on `origin_windows`. It has 764 completed rows: 590 correct / 92 wrong / 82 wrong_format = 77.2%. `origin_windows` is 55 rows: 31 correct / 20 wrong / 4 wrong_format. Current log row is `origin_windows_55 / create a 2D filled contour plot with color mapping`. Per watchdog rule, do not start another experiment while this run is active; inspect progress only.

Active experiment:
- User redirected away from single-sample debugging; launched a generic
  stratified run despite the older crop-first run still being active.
- `screen`: `iter_zoom_generic_stratified_pure_k3_20260531_1735`
- Script: `runs/screenspot_pro/run_iter_zoom_generic_stratified_20260531_1735.sh pure 3`
- Plan: 26 annotations x 3 deterministic quantile indexes (0/mid/last) = 78 planned rows.
- Log: `runs/screenspot_pro/iter_zoom_generic_stratified_pure_k3_20260531_1735.log`
- Output: `runs/screenspot_pro/iter_zoom_generic_stratified_pure_k3_20260531_1735/results.jsonl`
- 17:40 HKT progress: 13/78 complete, 13 unique samples, 10 correct / 3 wrong / 0 wrong_format = 76.9%. Last completed sample: `eviews_windows_0` correct. Current active annotation in log: `eviews_windows`.
- 17:45 HKT progress: 16/78 complete, 13 correct / 3 wrong / 0 wrong_format = 81.25%. Current active sample: `excel_macos_32: remove background fill for line 118`. Current wrong cases visualized under `runs/screenspot_pro/iter_zoom_generic_stratified_pure_k3_20260531_1735/wrong_visualizations/` and posted to Discord.
- 17:55 HKT progress: 31/78 complete, 31 unique samples, 24 correct / 5 wrong / 2 wrong_format = 77.4%. Current active sample: `macos_common_macos_32: call out the finder in the back`. Last completed sample: `macos_common_macos_0` correct.
- 17:55 HKT wrong cases: `android_studio_macos_40` crop_lost_gt_at=round_2_next_box; `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_1_next_box; `illustrator_windows_15` crop_lost_gt_at=null; `inventor_windows_0` wrong_format crop_lost_gt_at=null; `inventor_windows_34` wrong_format crop_lost_gt_at=null.
- 17:55 HKT Discord report posted to channel `1506997305923080212`: text message `1510582683007189134`, followed by seven wrong-case visualization images.
- 18:05 HKT progress: 41/78 complete, 41 unique samples, 32 correct / 7 wrong / 2 wrong_format = 78.0%. Current active sample: `photoshop_windows_50: select the eyedropper tool`. Last completed sample: `photoshop_windows_25` wrong.
- 18:05 HKT wrong cases: `android_studio_macos_40` crop_lost_gt_at=round_2_next_box; `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_1_next_box; `illustrator_windows_15` crop_lost_gt_at=null; `inventor_windows_0` wrong_format crop_lost_gt_at=null; `inventor_windows_34` wrong_format crop_lost_gt_at=null; `origin_windows_61` crop_lost_gt_at=round_1_next_box; `photoshop_windows_25` crop_lost_gt_at=round_1_next_box.
- 18:05 HKT Discord report posted to channel `1506997305923080212`: text message `1510585150856101958`, followed by nine wrong-case visualization images. Crop-loss count: 6/9 current failures.
- 18:15 HKT progress: 50/78 complete, 50 unique samples, 39 correct / 9 wrong / 2 wrong_format = 78.0%. Current active sample: `pycharm_macos_77: debug this code`. Last completed sample: `pycharm_macos_38` correct.
- 18:15 HKT wrong cases: `android_studio_macos_40` crop_lost_gt_at=round_2_next_box; `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_1_next_box; `illustrator_windows_15` crop_lost_gt_at=null; `inventor_windows_0` wrong_format crop_lost_gt_at=null; `inventor_windows_34` wrong_format crop_lost_gt_at=null; `origin_windows_61` crop_lost_gt_at=round_1_next_box; `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; `photoshop_windows_50` crop_lost_gt_at=round_1_next_box; `pycharm_macos_0` crop_lost_gt_at=null.
- 18:15 HKT Discord report posted to channel `1506997305923080212`: text message `1510587674539462707`, followed by eleven wrong-case visualization images. Crop-loss count: 7/11 current failures.
- Progress helper: `runs/screenspot_pro/report_iter_zoom_progress.py` writes `progress_summary.json` and annotated wrong-case screenshots. Red marker = prediction, green box = ground truth.

Guarded crop update:
- User required that clicking only happen after an explicitly verified crop.
- Code now enables a crop commit gate by default for iterative zoom:
  `GUI_HARNESS_SCREENSPOT_ITERATIVE_CROP_COMMIT_GATE=1` and
  `GUI_HARNESS_SCREENSPOT_ITERATIVE_CROP_RETRIES=3`.
- Each proposed crop is rendered with a magenta box and reviewed before commit.
  If target/context is uncertain, the crop is rejected and retried from the
  wider parent crop. If no crop is committed, the method returns no click.
- Baseline generic run `iter_zoom_generic_stratified_pure_k3_20260531_1735`
  was stopped to avoid mixing configurations.
- New active screen: `iter_zoom_guarded_stratified_pure_k3_20260531_1818`.
- New output: `runs/screenspot_pro/iter_zoom_guarded_stratified_pure_k3_20260531_1818/results.jsonl`.
- New log: `runs/screenspot_pro/iter_zoom_guarded_stratified_pure_k3_20260531_1818.log`.
- 18:19 HKT: guarded run active on `android_studio_macos_0`; no completed rows
  yet, first crop transitions have passed commit gate and logged.

Staged crop update:
- User required at least one crop before click and a logical staged crop path:
  screen/window/app region -> app section/panel/page -> local control group -> final upsampled click.
- Added staged guidance to crop and commit-gate prompts.
- Added early-stage minimum-area constraints to avoid one-shot tiny crops:
  stage1 >= 20% of parent crop area, stage2 >= 8% of parent crop area.
- Stopped `iter_zoom_guarded_stratified_pure_k3_20260531_1818` to avoid mixed results.
- New active screen: `iter_zoom_staged_guarded_stratified_pure_k3_20260531_1826`.
- New script: `runs/screenspot_pro/run_iter_zoom_staged_guarded_stratified_20260531_1826.sh pure 3`.
- New output: `runs/screenspot_pro/iter_zoom_staged_guarded_stratified_pure_k3_20260531_1826/results.jsonl`.
- New log: `runs/screenspot_pro/iter_zoom_staged_guarded_stratified_pure_k3_20260531_1826.log`.
- 18:25 HKT watchdog note: cron prompt still named `iter_zoom_guarded_stratified_pure_k3_20260531_1818`, but that screen is no longer active and the state shows it was intentionally stopped to avoid mixed results. The live guarded/staged screen is `iter_zoom_staged_guarded_stratified_pure_k3_20260531_1826`, currently in `android_studio_macos_0` with 0 completed rows at process inspection time.
- 18:25 HKT requested-run report for stopped `1818`: 3/78 complete, 2 correct / 1 wrong / 0 wrong_format = 66.7%; active sample from the old helper/log `autocad_windows_0 / Hand-draw cloud line`; last completed `android_studio_macos_79` correct. Wrong case: `android_studio_macos_40` crop_lost_gt_at=round_1_next_box. Discord report posted to channel `1506997305923080212`: text message `1510590409397502012`, followed by one wrong-case visualization image `1510590474384048219`.

Component-guided crop update:
- User pointed out OCR/component candidates should be used as crop evidence.
- Crop proposal prompt now explicitly treats candidate labels/boxes/centers as
  grounding anchors for staged crop decisions.
- Commit gate now receives two candidate lists: candidates inside the proposed
  crop and candidates still visible outside it. It should reject crops when
  target-related candidates remain outside or the inside evidence is inconsistent.
- Stopped staged-only run to avoid mixing configurations.
- New active screen: `iter_zoom_component_staged_guarded_stratified_pure_k3_20260531_1832`.
- New script: `runs/screenspot_pro/run_iter_zoom_component_staged_guarded_stratified_20260531_1832.sh pure 3`.
- New output: `runs/screenspot_pro/iter_zoom_component_staged_guarded_stratified_pure_k3_20260531_1832/results.jsonl`.
- New log: `runs/screenspot_pro/iter_zoom_component_staged_guarded_stratified_pure_k3_20260531_1832.log`.
- 18:35 HKT progress: 1/78 complete, 1 unique sample, 1 correct / 0 wrong / 0 wrong_format = 100.0%. Current active sample: `android_studio_macos_40: expand TODO items in android studio`. Last completed sample: `android_studio_macos_0` correct. No current wrong cases and no wrong-case visualizations. Discord report posted to channel `1506997305923080212`: text message `1510592698824917154`.
- 18:45 HKT progress: 6/78 complete, 6 unique samples, 4 correct / 2 wrong / 0 wrong_format = 66.7%. Current active sample: `blender_windows_0: Change position along Y axis using text input`. Last completed sample: `autocad_windows_33` wrong.
- 18:45 HKT wrong cases: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box. Both current failures lost GT during the first crop transition. Discord report posted to channel `1506997305923080212`: text message `1510595216925786265`, followed by two wrong-case visualization images `1510595270310625290` and `1510595275742253176`.
- 18:55 HKT progress: 12/78 complete, 12 unique samples, 10 correct / 2 wrong / 0 wrong_format = 83.3%. Current active sample: `eviews_windows_0: reset to Eviews defaults`. Last completed sample: `davinci_macos_43` correct.
- 18:55 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box. Both current failures lost GT during the first crop transition. Discord report posted to channel `1506997305923080212`: text message `1510597750109114489`, followed by two wrong-case visualization images `1510597808363798538` and `1510597813296431144`.
- 19:05 HKT progress: 19/78 complete, 19 unique samples, 16 correct / 3 wrong / 0 wrong_format = 84.2%. Current active sample: `fruitloops_windows_28: add new folder`. Last completed sample: `fruitloops_windows_0` wrong.
- 19:05 HKT wrong cases: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box. All current failures lost GT during crop refinement. Discord report posted to channel `1506997305923080212`: text message `1510600265391407154`, followed by three wrong-case visualization images `1510600319510253699`, `1510600325785059379`, and `1510600337910665337`.
- 19:15 HKT progress: 25/78 complete, 25 unique samples, 22 correct / 3 wrong / 0 wrong_format = 88.0%. Current active sample: `inventor_windows_34: macros`. Last completed sample: `inventor_windows_0` correct.
- 19:15 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box. All current failures lost GT during crop refinement. Discord report posted to channel `1506997305923080212`: text message `1510602794682548397`, followed by three wrong-case visualization images `1510602848239485061`, `1510602852945629195`, and `1510602861934018620`.
- 19:25 HKT progress: 30/78 complete, 30 unique samples, 27 correct / 3 wrong / 0 wrong_format = 90.0%. Current active sample: `macos_common_macos_0: cancel extraction`. Last completed sample: `linux_common_linux_49` correct.
- 19:25 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box. All current failures lost GT during crop refinement. Discord report posted to channel `1506997305923080212`: text message `1510605279748948149`, followed by three wrong-case visualization images `1510605334660776087`, `1510605340427944036`, and `1510605344915722262`.
- 19:35 HKT progress: 35/78 complete, 35 unique samples, 32 correct / 3 wrong / 0 wrong_format = 91.4%. Current active sample: `matlab_macos_92: insert colorbar`. Last completed sample: `matlab_macos_46` correct.
- 19:35 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box. All current failures lost GT during crop refinement. Discord report posted to channel `1506997305923080212`: text message `1510607799141535774`, followed by three wrong-case visualization images `1510607856590651494`, `1510607864480141423`, and `1510607873158152273`.
- 19:45 HKT progress: 37/78 complete, 37 unique samples, 33 correct / 4 wrong / 0 wrong_format = 89.2%. Current active sample: `origin_windows_30: plot a box plot`. Last completed sample: `origin_windows_0` wrong.
- 19:45 HKT wrong cases: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; `origin_windows_0` crop_lost_gt_at=round_1_next_box. All current failures lost GT during crop refinement. Discord report posted to channel `1506997305923080212`: text message `1510610639620538432`, followed by four wrong-case visualization images `1510610649326030938`, `1510610660285747220`, `1510610684101263450`, and `1510610693748035774`.
- 19:55 HKT progress: 43/78 complete, 43 unique samples, 36 correct / 6 wrong / 1 wrong_format = 83.7%. Current active sample: `powerpoint_windows_40: Hide the slide`. Last completed sample: `powerpoint_windows_0` correct. Active screen/process confirmed; no duplicate run started.
- 19:55 HKT wrong cases: seen `autocad_windows_16` crop_lost_gt_at=round_1_next_box; seen `autocad_windows_33` crop_lost_gt_at=round_1_next_box; seen `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; seen `origin_windows_0` crop_lost_gt_at=round_1_next_box; NEW `origin_windows_30` crop_lost_gt_at=round_3_next_box; NEW `origin_windows_61` wrong_format crop_lost_gt_at=null; NEW `photoshop_windows_25` crop_lost_gt_at=round_1_next_box. Discord report posted to channel `1506997305923080212`: text message `1510612855580528740`, followed only by three new wrong-case visualization images `1510612859833290906`, `1510612865210388610`, and `1510612874203107389`.
- 20:05 HKT progress: 49/78 complete, 49 unique samples, 40 correct / 8 wrong / 1 wrong_format = 81.6%. Current active sample: `pycharm_macos_38: select the third error`. Last completed sample: `pycharm_macos_0` wrong. Active screen/process confirmed; no duplicate run started.
- 20:05 HKT wrong cases: seen `autocad_windows_16` crop_lost_gt_at=round_1_next_box; seen `autocad_windows_33` crop_lost_gt_at=round_1_next_box; seen `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; seen `origin_windows_0` crop_lost_gt_at=round_1_next_box; seen `origin_windows_30` crop_lost_gt_at=round_3_next_box; seen `origin_windows_61` wrong_format crop_lost_gt_at=null; seen `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; NEW `premiere_windows_51` crop_lost_gt_at=null; NEW `pycharm_macos_0` crop_lost_gt_at=null. Discord report posted to channel `1506997305923080212`: text message `1510615387434389537`, followed only by two new wrong-case visualization images `1510615394111721482` and `1510615401845887166`.
- 20:15 HKT progress: 56/78 complete, 56 unique samples, 47 correct / 8 wrong / 1 wrong_format = 83.9%. Current active sample: `solidworks_windows_76: Sensor`. Last completed sample: `solidworks_windows_38` correct. Active screen/process confirmed; no duplicate run started.
- 20:15 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; `origin_windows_0` crop_lost_gt_at=round_1_next_box; `origin_windows_30` crop_lost_gt_at=round_3_next_box; `origin_windows_61` wrong_format crop_lost_gt_at=null; `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; `premiere_windows_51` crop_lost_gt_at=null; `pycharm_macos_0` crop_lost_gt_at=null. Discord report posted to channel `1506997305923080212`: text message `1510617859162898442`. No new wrong-case images this interval.
- 20:25 HKT progress: 62/78 complete, 62 unique samples, 53 correct / 8 wrong / 1 wrong_format = 85.5%. Current active sample: `unreal_engine_windows_34: Renders the scene with lights only, no textures`. Last completed sample: `unreal_engine_windows_17` correct. Active screen/process confirmed; no duplicate run started.
- 20:25 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; `origin_windows_0` crop_lost_gt_at=round_1_next_box; `origin_windows_30` crop_lost_gt_at=round_3_next_box; `origin_windows_61` wrong_format crop_lost_gt_at=null; `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; `premiere_windows_51` crop_lost_gt_at=null; `pycharm_macos_0` crop_lost_gt_at=null. Discord report posted to channel `1506997305923080212`: text message `1510620374755315902`. No new wrong-case images this interval.
- 20:35 HKT progress: 68/78 complete, 68 unique samples, 57 correct / 10 wrong / 1 wrong_format = 83.8%. Current active sample: `vmware_macos_40: shut down the VM inside it`. Last completed sample: `vmware_macos_20` correct. Active screen/process confirmed; no duplicate run started.
- 20:35 HKT wrong cases: seen `autocad_windows_16` crop_lost_gt_at=round_1_next_box; seen `autocad_windows_33` crop_lost_gt_at=round_1_next_box; seen `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; seen `origin_windows_0` crop_lost_gt_at=round_1_next_box; seen `origin_windows_30` crop_lost_gt_at=round_3_next_box; seen `origin_windows_61` wrong_format crop_lost_gt_at=null; seen `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; seen `premiere_windows_51` crop_lost_gt_at=null; seen `pycharm_macos_0` crop_lost_gt_at=null; NEW `vivado_windows_40` crop_lost_gt_at=null; NEW `vivado_windows_79` crop_lost_gt_at=round_4_next_box. Discord report posted to channel `1506997305923080212`: text message `1510622966524940338`, followed only by two new wrong-case visualization images `1510622972019478719` and `1510622977685848234`.
- 20:45 HKT progress: 75/78 complete, 75 unique samples, 64 correct / 10 wrong / 1 wrong_format = 85.3%. Current active sample: `word_macos_0: create a new list in word`. Last completed sample: `windows_common_windows_80` correct. Active screen/process confirmed; no duplicate run started.
- 20:45 HKT wrong cases unchanged: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; `origin_windows_0` crop_lost_gt_at=round_1_next_box; `origin_windows_30` crop_lost_gt_at=round_3_next_box; `origin_windows_61` wrong_format crop_lost_gt_at=null; `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; `premiere_windows_51` crop_lost_gt_at=null; `pycharm_macos_0` crop_lost_gt_at=null; `vivado_windows_40` crop_lost_gt_at=null; `vivado_windows_79` crop_lost_gt_at=round_4_next_box. Discord report posted to channel `1506997305923080212`: text message `1510625428086329554`. No new wrong-case images this interval.
- 20:55 HKT COMPLETE: component-guided staged+guarded run finished 78/78 complete, 78 unique samples, 67 correct / 10 wrong / 1 wrong_format = 85.9%. Last completed sample: `word_macos_83` correct. Active screen is gone; no duplicate run started.
- 20:55 HKT final wrong cases: `autocad_windows_16` crop_lost_gt_at=round_1_next_box; `autocad_windows_33` crop_lost_gt_at=round_1_next_box; `fruitloops_windows_0` crop_lost_gt_at=round_2_next_box; `origin_windows_0` crop_lost_gt_at=round_1_next_box; `origin_windows_30` crop_lost_gt_at=round_3_next_box; `origin_windows_61` wrong_format crop_lost_gt_at=null; `photoshop_windows_25` crop_lost_gt_at=round_1_next_box; `premiere_windows_51` crop_lost_gt_at=null; `pycharm_macos_0` crop_lost_gt_at=null; `vivado_windows_40` crop_lost_gt_at=null; `vivado_windows_79` crop_lost_gt_at=round_4_next_box. No new wrong-case images this interval. Discord final report posted to channel `1506997305923080212`: text message `1510628017683173566`.
- 20:55 HKT comparison: generic pure baseline snapshot was only 50/78 complete at 39 correct / 9 wrong / 2 wrong_format = 78.0%, with crop_lost_gt_at present in 7/11 failure records. Component staged+guarded completed all 78 at 85.9%, with 10 wrong / 1 wrong_format and crop_lost_gt_at present in 7/11 failure records. Wrong_format improved directionally; crop-lost failures remain recurring, concentrated in early crop transitions plus `origin_windows_30` round_3 and `vivado_windows_79` round_4. Stopped guarded/staged intermediates were too short for reliable full-run comparison.
- 21:05 HKT watchdog check: component-guided staged+guarded run remains complete at 78/78, 67 correct / 10 wrong / 1 wrong_format = 85.9%. Screen `iter_zoom_component_staged_guarded_stratified_pure_k3_20260531_1832` is no longer active; no duplicate run started. No new wrong-case images this interval. Discord no-change report posted to channel `1506997305923080212`: text message `1510630452233240596`.
- 21:15 HKT watchdog check: component-guided staged+guarded run remains complete at 78/78, 67 correct / 10 wrong / 1 wrong_format = 85.9%. Screen `iter_zoom_component_staged_guarded_stratified_pure_k3_20260531_1832` remains inactive; no duplicate run started. No new wrong-case images this interval. Discord no-change report posted to channel `1506997305923080212`: text message `1510632957583298682`.

Next actions:
1. Let the 78-row component-guided staged+guarded stratified run complete.
2. Report every 10 minutes with progress, wrong cases, crop_lost_gt_at, and visualizations.
3. Compare guarded run against the stopped baseline to see whether crop_lost_gt_at and wrong_format drop.
4. Only modify the method for failures that recur across multiple apps/subsets.
