"""Calibrate once, then replay immutable genuine published targets post-score."""
import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / 'tmp/pr-quality-panel/condition-scope-measure'
sys.path[:0] = [str(ROOT / 'docs/evaluations'), str(ROOT / 'docs/evaluations/tools')]
from replay_caller import COMMAND, E, C, replay_paths
from cpu_leases import lease
from records import digest, read_pilot

SOURCE = ROOT / 'docs/evaluations/runs/tuning/observable-werkzeug-01/result.json'
STREAM = 'observable-red-green-replay'
WARNING = 'condition-scope-body-warnings'
HELPER = ROOT / 'docs/evaluations/tools/replay_caller.py'

def save(name, value):
    with (OUT / name).open('x') as file:
        file.write(json.dumps(value, indent=2) + '\n')

def invoke(work, probe):
    args, image = E.lab.docker(E.CASES['werkzeug'], work)
    mount = f'type=bind,src={work},dst=/work'
    assert args.count(mount) == 1
    args[args.index(mount)] += ',readonly'
    result = subprocess.run([*args, '--mount', f'type=bind,src={probe},dst=/oracle/probe.py,readonly',
                             image, 'sh', '-ec', COMMAND], capture_output=True, timeout=180)
    assert not result.stderr, result.stderr.decode()
    return {'command': COMMAND, 'exit': result.returncode, 'log_sha256': digest(result.stdout),
            'output': result.stdout.decode()}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('operation', choices=('calibrate', 'replay'))
parser.add_argument('--target', type=Path, default=SOURCE)
parser.add_argument('--output', default='historical-replay.json')
args = parser.parse_args()
os.environ.update(OAIPKG_DISABLE_META_MISSING='1', PYTHONDONTWRITEBYTECODE='1')
E.configure()
for key in ('TMPDIR', 'TMP', 'TEMP'):
    os.environ[key] = str(OUT / 'scratch')
tempfile.tempdir = str(OUT / 'scratch')
os.environ['PANEL_CPUSET'] = '0,1'
os.sched_setaffinity(0, {0, 1})
archive = read_pilot(SOURCE)
probe = OUT / 'body_probe.py'
stream = next(o for o in archive['observations'] if o['id'] == STREAM)
if args.operation == 'calibrate':
    previous = ROOT / 'tmp/pr-quality-panel/werkzeug-warning-replay'
    controls = json.loads((previous / 'portable-companion.json').read_bytes())
    warning = ROOT / 'docs/evaluations/runs/tuning/observable-werkzeug-01/warning-contract-replay.json'
    assert E.sha(SOURCE) == controls['source_result_sha256']
    rows = {}
    with lease(E.STATE, [0, 1]):
        for role, control in controls['rows'].items():
            work = previous / ('tree-' + role) / 'work'
            assert subprocess.check_output(['git', '-C', work, 'write-tree'], text=True).strip() == control['reconstructed_tree']
            subprocess.run(['git', '-C', work, 'diff', '--exit-code'], check=True, capture_output=True)
            label = 'gold' if role == 'merge' else role
            assert control['patch_sha256'] == json.loads(warning.read_bytes())['rows'][role]['patch_sha256']
            rows[label] = {'patch_sha256': control['patch_sha256'], 'grade_sha256': control['grade_sha256'],
                           'stages': {'caller': invoke(work, probe)}}
        positive = ROOT / 'tmp/pr-quality-panel/werkzeug-constructive-control/combined.patch'
        snapshot = C.grading.grade(E.CASES['werkzeug'], archive['base'], OUT / 'positive', positive, phases=[])
        assert snapshot['applied']
        positive_rows = {'warnings': invoke(OUT / 'positive/work', probe)}
        stream_probe = OUT / 'stream_probe.py'
        stream_probe.write_text(stream['probe'])
        positive_rows['stream'] = invoke(OUT / 'positive/work', stream_probe)
        assert all(row['exit'] == 0 for row in positive_rows.values())
    evidence = {'case': archive['case'], 'registration_sha256': archive['registration_sha256'],
                'probe_sha256': E.sha(probe), 'warning_contract_source_sha256': E.sha(warning),
                'roles': rows, 'scope': 'Post-score supplement; exact logs calibrate identity, not message/count requirements.'}
    supplement = {'id': WARNING, 'source_sha256': E.sha(SOURCE), 'probe': probe.read_text(),
                  'evidence': evidence, 'receipt_sha256': digest((json.dumps(evidence, indent=2) + '\n').encode())}
    save('warning-supplement.json', supplement)
    save('registration.json', {'scope': 'New exposed Werkzeug-only assessor contract; no participant release or score edits.',
         'source_sha256': E.sha(SOURCE), 'helper_sha256': E.sha(HELPER), 'runner_sha256': E.sha(Path(__file__)),
         'warning_supplement_sha256': E.sha(OUT / 'warning-supplement.json'), 'stream_probe_sha256': stream['evidence']['probe_sha256'],
         'stream_receipt_sha256': stream['receipt_sha256'], 'command': COMMAND,
         'positive_patch_sha256': E.sha(positive), 'positive': positive_rows})
else:
    registration = json.loads((OUT / 'registration.json').read_bytes())
    assert (E.sha(SOURCE), E.sha(HELPER), E.sha(Path(__file__)), E.sha(OUT / 'warning-supplement.json')) == tuple(
        registration[k] for k in ('source_sha256', 'helper_sha256', 'runner_sha256', 'warning_supplement_sha256'))
    target = read_pilot(args.target)
    supplement = json.loads((OUT / 'warning-supplement.json').read_bytes())
    rows = {STREAM: replay_paths(SOURCE, STREAM, args.target, scratch=OUT / 'scratch'),
            WARNING: replay_paths(SOURCE, WARNING, args.target, supplement=supplement, scratch=OUT / 'scratch')}
    complete = all(target['submissions'][role]['state'] == 'completed' for role in ('control', 'develop'))
    save(args.output, {'scope': 'Diagnostic only; official grades, costs and producer states unchanged.',
         'producers_complete': complete, 'release_eligible': False,
         'registration_sha256': E.sha(OUT / 'registration.json'), 'measurements': rows})
