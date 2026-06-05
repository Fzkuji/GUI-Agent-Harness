export const meta = {
  name: 'screenspot-hard100-best-vs-legacy',
  description: 'best vs legacy 难题对比: 100难题 x (GPT×best, M3×best, M3×legacy) = 300单元',
  phases: [
    { title: 'GPT best' },
    { title: 'M3 best' },
    { title: 'M3 legacy' },
  ],
}

const REPO = '/Users/fzkuji/Documents/GUI Agent/GUI-Agent-Harness'
const PY = '/opt/miniconda3/bin/python3'
const RESBASE = REPO + '/benchmarks/screenspot_pro/results/hard100'
const CFGBASE = REPO + '/benchmarks/screenspot_pro/configs'

// 100 难题（GPT-5.5 在 legacy 下答错的，分层抽样），由 hard100_samples.json 生成。
const SAMPLES = JSON.parse(args && args.samplesJson ? args.samplesJson : 'null') || [
  ['android_studio_macos.json',5],['android_studio_macos.json',15],['android_studio_macos.json',20],['android_studio_macos.json',41],
  ['autocad_windows.json',4],['autocad_windows.json',8],['autocad_windows.json',9],['autocad_windows.json',16],['autocad_windows.json',17],
  ['blender_windows.json',10],['blender_windows.json',19],['blender_windows.json',30],
  ['davinci_macos.json',6],['davinci_macos.json',8],['davinci_macos.json',12],['davinci_macos.json',14],
  ['eviews_windows.json',7],
  ['excel_macos.json',19],
  ['fruitloops_windows.json',0],['fruitloops_windows.json',7],['fruitloops_windows.json',8],['fruitloops_windows.json',9],['fruitloops_windows.json',16],['fruitloops_windows.json',23],['fruitloops_windows.json',31],
  ['illustrator_windows.json',4],['illustrator_windows.json',16],['illustrator_windows.json',17],
  ['inventor_windows.json',1],['inventor_windows.json',21],['inventor_windows.json',25],['inventor_windows.json',26],['inventor_windows.json',30],['inventor_windows.json',34],
  ['linux_common_linux.json',32],['linux_common_linux.json',36],
  ['macos_common_macos.json',12],['macos_common_macos.json',22],
  ['matlab_macos.json',11],['matlab_macos.json',12],['matlab_macos.json',13],['matlab_macos.json',37],['matlab_macos.json',41],
  ['origin_windows.json',0],['origin_windows.json',1],['origin_windows.json',2],['origin_windows.json',3],['origin_windows.json',5],['origin_windows.json',7],['origin_windows.json',9],['origin_windows.json',12],['origin_windows.json',20],['origin_windows.json',21],['origin_windows.json',22],
  ['photoshop_windows.json',1],['photoshop_windows.json',8],['photoshop_windows.json',13],['photoshop_windows.json',15],
  ['powerpoint_windows.json',0],['powerpoint_windows.json',1],['powerpoint_windows.json',15],
  ['premiere_windows.json',14],['premiere_windows.json',30],['premiere_windows.json',33],
  ['pycharm_macos.json',0],['pycharm_macos.json',1],['pycharm_macos.json',5],['pycharm_macos.json',21],['pycharm_macos.json',24],['pycharm_macos.json',34],['pycharm_macos.json',36],['pycharm_macos.json',41],
  ['quartus_windows.json',1],['quartus_windows.json',5],['quartus_windows.json',6],['quartus_windows.json',12],['quartus_windows.json',15],['quartus_windows.json',24],
  ['solidworks_windows.json',13],['solidworks_windows.json',35],['solidworks_windows.json',36],
  ['stata_windows.json',26],['stata_windows.json',30],
  ['unreal_engine_windows.json',6],['unreal_engine_windows.json',28],
  ['vivado_windows.json',8],['vivado_windows.json',9],['vivado_windows.json',15],['vivado_windows.json',34],['vivado_windows.json',40],
  ['vmware_macos.json',33],
  ['vscode_macos.json',10],['vscode_macos.json',11],
  ['windows_common_windows.json',4],['windows_common_windows.json',5],['windows_common_windows.json',24],['windows_common_windows.json',25],['windows_common_windows.json',27],['windows_common_windows.json',32],
  ['word_macos.json',5],
]

// 3 组：GPT×best、M3×best、M3×legacy（GPT×legacy 省略，≈0）。
const COMBOS = [
  { tag: 'gpt-5_5', provider: 'openai-codex', model: 'gpt-5.5', cfg: 'best', phase: 'GPT best' },
  { tag: 'MiniMax-M3', provider: 'minimax-cn-coding-plan', model: 'MiniMax-M3', cfg: 'best', phase: 'M3 best' },
  { tag: 'MiniMax-M3', provider: 'minimax-cn-coding-plan', model: 'MiniMax-M3', cfg: 'legacy_baseline', phase: 'M3 legacy' },
]

const SCHEMA = {
  type: 'object',
  properties: { correctness: { type: 'string' }, elapsed_s: { type: ['number', 'null'] } },
  required: ['correctness'],
}

function unitPrompt(c, ann, idx) {
  const stem = ann.replace('.json', '')
  const out = RESBASE + '/' + c.tag + '/' + c.cfg + '/' + stem + '_' + idx + '.jsonl'
  const work = RESBASE + '/' + c.tag + '/' + c.cfg + '/work/' + stem + '_' + idx
  const cfg = CFGBASE + '/' + c.cfg + '.yaml'
  const cmd = 'cd ' + JSON.stringify(REPO) + ' && ' + PY +
    ' benchmarks/screenspot_pro/run_screenspot_pro.py --annotation ' + ann +
    ' --indexes ' + idx + ' --output ' + JSON.stringify(out) +
    ' --work-dir ' + JSON.stringify(work) +
    ' --provider ' + c.provider + ' --model ' + c.model +
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
for (const c of COMBOS) {
  for (const pair of SAMPLES) {
    units.push({ c, ann: pair[0], idx: pair[1] })
  }
}
log('hard100: ' + units.length + ' units (' + SAMPLES.length + ' 难题 x 3 组)')

const results = await parallel(units.map(u => () =>
  agent(unitPrompt(u.c, u.ann, u.idx), {
    label: u.c.tag + ':' + u.c.cfg + ':' + u.ann.replace('.json', '') + '_' + u.idx,
    phase: u.c.phase,
    schema: SCHEMA,
  })
    .then(r => ({ tag: u.c.tag, cfg: u.c.cfg, sample: u.ann.replace('.json', '') + '_' + u.idx, correctness: (r && r.correctness) ? r.correctness : 'ERROR' }))
    .catch(() => ({ tag: u.c.tag, cfg: u.c.cfg, sample: u.ann.replace('.json', '') + '_' + u.idx, correctness: 'ERROR' }))
))

return { count: results.length, results }
