export const meta = {
  name: 'screenspot-single-var-ablation',
  description: 'single-var ablation: 4 arms x 20 samples x GPT+M3',
  phases: [
    { title: 'GPT arms' },
    { title: 'M3 arms' },
  ],
}

const REPO = '/Users/fzkuji/Documents/GUI Agent/GUI-Agent-Harness'
const PY = '/opt/miniconda3/bin/python3'
const RESBASE = REPO + '/benchmarks/screenspot_pro/results/ablation_reason_cand'
const CFGBASE = REPO + '/benchmarks/screenspot_pro/configs'

const SAMPLES = [
  ['android_studio_macos.json', 5], ['autocad_windows.json', 4], ['blender_windows.json', 10],
  ['davinci_macos.json', 6], ['eviews_windows.json', 7], ['excel_macos.json', 19],
  ['fruitloops_windows.json', 0], ['illustrator_windows.json', 4], ['inventor_windows.json', 1],
  ['linux_common_linux.json', 32],
  ['android_studio_macos.json', 0], ['autocad_windows.json', 0], ['blender_windows.json', 0],
  ['davinci_macos.json', 0], ['eviews_windows.json', 0], ['excel_macos.json', 0],
  ['fruitloops_windows.json', 1], ['illustrator_windows.json', 0], ['inventor_windows.json', 0],
  ['linux_common_linux.json', 0],
]
const ARMS = ['abl_reason', 'abl_sort', 'abl_dedup', 'abl_coords']
const MODELS = [
  { tag: 'gpt-5_5', provider: 'openai-codex', model: 'gpt-5.5', phase: 'GPT arms' },
  { tag: 'MiniMax-M3', provider: 'minimax-cn-coding-plan', model: 'MiniMax-M3', phase: 'M3 arms' },
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
