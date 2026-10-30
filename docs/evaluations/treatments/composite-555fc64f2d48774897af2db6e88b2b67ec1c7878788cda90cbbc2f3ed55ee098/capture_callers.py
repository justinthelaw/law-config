"""Fresh portable export and registered caller replay before immutable publication."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile

ROOT = Path.cwd()
REPLAYER = ROOT / 'docs/evaluations/tools/replay_caller.py'
sys.path[:0] = [str(ROOT / 'docs/evaluations'), str(ROOT / 'docs/evaluations/tools')]
import benchmark as B
from native_panel import E
from export_panel import export_pilot
from records import read_pilot


def capture(name, source, scratch):
    source, scratch = source.resolve(), scratch.resolve()
    policy = E.read(source / 'hypothesis.json')
    spec = policy['caller_capture']
    root = E.STATE / 'pilots' / B.valid_name(name)
    registration = E.read(root / 'registration.json')
    if registration['hypothesis'] != policy['id'] or registration['hypothesis_sha256'] != E.sha(source / 'hypothesis.json'):
        raise ValueError('registered hypothesis differs')
    for path, field in [(source / 'capture_callers.py', 'program_sha256'), (REPLAYER, 'replay_program_sha256'),
                        (source / 'calibration.json', 'calibration_sha256'), (source / 'probe.py', 'probe_sha256')]:
        if E.sha(path) != spec[field]:
            raise ValueError('registered caller source differs: ' + path.name)
    temporary = Path(tempfile.mkdtemp(prefix='caller-export-', dir=scratch))
    destination = temporary / name / 'result.json'
    export_pilot(name, destination)
    target = read_pilot(destination)
    if target['treatments'] != policy['composite_identities']:
        raise ValueError('exported treatment differs')
    arms = [target['submissions'][role] for role in ('control', 'develop')] + [target['prior_develop']]
    if (any(arm['state'] != 'completed' or arm['patch_sha256'] is None for arm in arms)
            or any(not target['submissions'][role]['stages'] for role in ('control', 'develop'))
            or not target['prior_develop']['stage_exits']):
        raise ValueError('missing sealed participant grade')
    supplement = E.read(source / 'calibration.json')
    supplement['probe'] = (source / 'probe.py').read_text()
    original = ROOT / spec['calibration_source']
    replay = runpy.run_path(str(REPLAYER))['replay_paths']
    record = replay(original, 'black-callers', destination, supplement=supplement, scratch=temporary)
    controls = supplement['evidence']['roles']
    if set(record['roles']) != set(controls):
        raise ValueError('missing measured role')
    for role, row in record['roles'].items():
        if not row or set(row['stages']) != set(controls['base']['stages']):
            raise ValueError('missing measured stage')
        for stage, result in row['stages'].items():
            outcome = json.loads(result['output']).get('outcome')
            if result['exit'] not in (0, 42) or outcome != ('pass' if result['exit'] == 0 else 'behavioral-red'):
                raise ValueError('caller setup error or skip')
            result['command'] = controls['base']['stages'][stage]['command']
    result = {'case': target['case'], 'registration_sha256': target['registration_sha256'],
              **{key: spec[key] for key in ('program_sha256', 'replay_program_sha256', 'calibration_sha256', 'probe_sha256')},
              'source_sha256': record['source_sha256'], 'roles': record['roles'],
              'outcome': 'candidate-pass' if all(row['exit'] == 0 for row in record['roles']['candidate-develop']['stages'].values()) else 'candidate-behavioral-red'}
    folder = root / 'sensitivity' / 'black-callers'
    folder.mkdir(parents=True, exist_ok=True)
    probe, receipt = folder / 'probe.py', folder / 'receipt.json'
    if probe.exists() and E.sha(probe) != spec['probe_sha256']:
        raise ValueError('saved probe differs')
    with tempfile.NamedTemporaryFile(dir=folder, prefix='.probe-', delete=False) as pending:
        pending.write((source / 'probe.py').read_bytes())
        pending.flush()
        os.fsync(pending.fileno())
    os.replace(pending.name, probe)
    if receipt.exists():
        if E.read(receipt) != result:
            raise ValueError('saved receipt differs from fresh replay')
    else:
        E.save(receipt, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', type=B.valid_name)
    args = parser.parse_args()
    E.configure()
    B.configure_temp()
    try:
        result = capture(args.name, Path(__file__).resolve().parent, B.STATE / 'volatile')
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['outcome'] == 'candidate-pass' else 42)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(70, str(exc) + '\n')
