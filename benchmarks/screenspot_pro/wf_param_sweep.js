export const meta = {
  name: 'screenspot-param-sweep',
  description: '全参数单变量扫描: 11 arm x 26样本 x M3 (base=quality_8round)',
  phases: [
    { title: 'M3 sweep' },
  ],
}

const REPO = '/Users/fzkuji/Documents/GUI Agent/GUI-Agent-Harness'
const PY = '/opt/miniconda3/bin/python3'
const RESBASE = REPO + '/benchmarks/screenspot_pro/results/param_sweep'
const CFGBASE = REPO + '/benchmarks/screenspot_pro/configs/sweep'

// 减样本加速：每个 app 取 index 0，共 26 样本（覆盖全部 app）。
// 由 sweep_samples_min.json 生成；内联以保证 workflow 自包含。
const SAMPLES = JSON.parse(args && args.samplesJson ? args.samplesJson : 'null') || [
  ['android_studio_macos.json',0],['autocad_windows.json',0],['blender_windows.json',0],
  ['davinci_macos.json',0],['eviews_windows.json',0],['excel_macos.json',0],
  ['fruitloops_windows.json',0],['illustrator_windows.json',0],['inventor_windows.json',0],
  ['linux_common_linux.json',0],['macos_common_macos.json',0],['matlab_macos.json',0],
  ['origin_windows.json',0],['photoshop_windows.json',0],['powerpoint_windows.json',0],
  ['premiere_windows.json',0],['pycharm_macos.json',0],['quartus_windows.json',0],
  ['solidworks_windows.json',0],['stata_windows.json',0],['unreal_engine_windows.json',0],
  ['vivado_windows.json',0],['vmware_macos.json',0],['vscode_macos.json',0],
  ['windows_common_windows.json',0],['word_macos.json',0],
]

const ARMS = ['base','no_crop_check','no_final_recheck','no_staged_crop','no_final_cand_detect',
  'no_final_recrop','reason_first','coords_local','crop_check_last','dedup_05','scale_target_px']
const MODELS = [
  { tag: 'MiniMax-M3', provider: 'minimax-cn-coding-plan', model: 'MiniMax-M3', phase: 'M3 sweep' },
]

const SCHEMA = {
  type: 'object',
  properties: { correctness: { type: 'string' }, elapsed_s: { type: ['number', 'null'] } },
  required: ['correctness'],
}

function unitPrompt(m, arm, ann, idx) {
  const stem = ann.replace('.json', '')
  const out = RESBASE + '/' + m.tag + '/' + arm + '/' + stem + '_' + idx + '.jsonl'
  const work = RESBASE + '/' + m.tag + '/' + arm + '/work/' + stem + '_' + idx
  const cfg = CFGBASE + '/' + arm + '.yaml'
  const cmd = 'cd ' + JSON.stringify(REPO) + ' && ' + PY +
    ' benchmarks/screenspot_pro/run_screenspot_pro.py --annotation ' + ann +
    ' --indexes ' + idx + ' --output ' + JSON.stringify(out) +
    ' --work-dir ' + JSON.stringify(work) +
    ' --provider ' + m.provider + ' --model ' + m.model +
    ' --config ' + JSON.stringify(cfg) +
    ' --runtime-retries 4 --retry-provider-errors 2 --sample-timeout-s 1800' +
    ' --exec-timeout-s 600 --download-timeout-s 60 --download-retries 5'
  return 'Run exactly ONE shell command (it grounds one ScreenSpot-Pro sample), then read its output file. Do not edit any files. Do not run anything else.\n\n' +
    'If the file ' + JSON.stringify(out) + ' already exists and its last line is valid JSON, SKIP running the command and just read that line.\n\n' +
    'Command to run:\n' + cmd + '\n\n' +
    'After it finishes, read the LAST JSON line of ' + JSON.stringify(out) +
    ' and return its "correctness" (string) and "elapsed_s" (number or null).'
}

const units = []
for (const m of MODELS) {
  for (const arm of ARMS) {
    for (const pair of SAMPLES) {
      units.push({ m, arm, ann: pair[0], idx: pair[1] })
    }
  }
}
log('param sweep: ' + units.length + ' grounding units (' + ARMS.length + ' arms x ' + SAMPLES.length + ' samples x ' + MODELS.length + ' models)')

const results = await parallel(units.map(u => () =>
  agent(unitPrompt(u.m, u.arm, u.ann, u.idx), {
    label: u.m.tag + ':' + u.arm + ':' + u.ann.replace('.json', '') + '_' + u.idx,
    phase: u.m.phase,
    schema: SCHEMA,
  })
    .then(r => ({ tag: u.m.tag, arm: u.arm, sample: u.ann.replace('.json', '') + '_' + u.idx, correctness: (r && r.correctness) ? r.correctness : 'ERROR' }))
    .catch(() => ({ tag: u.m.tag, arm: u.arm, sample: u.ann.replace('.json', '') + '_' + u.idx, correctness: 'ERROR' }))
))

return { count: results.length, results }
