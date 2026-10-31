"""Strictly validate behavior receipts and replay preserved original consumers."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path.cwd()
OUT = ROOT / 'tmp/pr-quality-panel/condition-scope-measure'
sys.path[:0] = [str(ROOT/'docs/evaluations'), str(ROOT/'docs/evaluations/tools')]
from native_panel import C, E
from cpu_leases import lease
from records import read_json, read_pilot, digest
SOURCE = ROOT/'docs/evaluations/runs/tuning/observable-werkzeug-01/result.json'
NODES = ['test_wrapper_internals', 'test_path_info_script_name_unquoting']
FILES = ['tests/test_internal.py', 'tests/test_test.py']
FIX = OUT/'consumer-fixture'

def save(name, value):
    with (OUT/name).open('x') as file: file.write(json.dumps(value, indent=2)+'\n')

def behavior(stage, kind):
    if digest(stage['output'].encode()) != stage['log_sha256']: raise ValueError('log hash differs')
    value = read_json(stage['output'])
    if type(stage['exit']) is not int or (stage['exit'], value.get('outcome')) not in ((0,'green'), (42,'red-behavior')):
        raise ValueError('setup, unknown or inconsistent exit/outcome')
    if kind == 'stream':
        if value['generated_cases'] != 144 or type(value['failing_cases']) is not int or not 0 <= value['failing_cases'] <= 144:
            raise ValueError('invalid stream denominator')
        passed = value['failing_cases'] == 0
    else:
        if [r['input'] for r in value['rows']] != ['strings','bytes','bytes-strings','strings-bytes']:
            raise ValueError('warning input partition differs')
        checks = []
        for index, row in enumerate(value['rows']):
            if [o['operation'] for o in row['operations']] != ['get_data','close']: raise ValueError('attribution differs')
            classes = [w['class'] for op in row['operations'] for w in op['warnings']]
            good = (not row.get('error') and row.get('bytes') == [120,121]
                    and (bool(row['operations'][0]['warnings']) if index > 1 else not classes)
                    and all(c == 'builtins.DeprecationWarning' for c in classes))
            if row['pass'] is not good: raise ValueError('warning row verdict differs')
            checks.append(good)
        passed = all(checks)
    if passed != (stage['exit'] == 0): raise ValueError('behavior and exit differ')
    return value['outcome']

def consumer(value, outer_exit):
    if outer_exit != 0 or [c['name'] for c in value.get('cases',[])] != NODES:
        raise ValueError('consumer driver or collection setup error')
    states = [c['status'] for c in value['cases']]
    if any(s not in ('passed','failure') for s in states) or value['exit'] not in (0,1):
        raise ValueError('consumer setup error')
    passed = states == ['passed','passed']
    if passed != (value['exit'] == 0): raise ValueError('consumer exit differs')
    return 'green' if passed else 'red-behavior'

os.environ.update(OAIPKG_DISABLE_META_MISSING='1', PYTHONDONTWRITEBYTECODE='1')
E.configure()
for key in ('TMPDIR','TMP','TEMP'): os.environ[key] = str(OUT/'scratch')
tempfile.tempdir = str(OUT/'scratch')
os.environ['PANEL_CPUSET'] = '0,1'
os.sched_setaffinity(0,{0,1})
if sys.argv[1] == 'register':
    FIX.mkdir()
    contract = read_json(SOURCE.with_name('warning-contract-replay.json').read_bytes())
    base = ROOT/'tmp/pr-quality-panel/werkzeug-warning-replay/tree-base/work'
    for path in FILES:
        assert E.sha(base/path) == contract['base_test_sha256'][path]
        shutil.copyfile(base/path, FIX/Path(path).name)
    helper = ROOT/'tmp/pr-quality-panel/consumer-suite-selection/docker-capture.py'
    shutil.copyfile(helper,FIX/'capture.py')
    rejected = []
    for name, stage in [('setup',{'exit':70,'output':'{"outcome":"setup-error"}'}),
                        ('malformed',{'exit':0,'output':'{"outcome":'}),
                        ('unknown',{'exit':0,'output':'{"outcome":"unknown"}'}),
                        ('mismatch',{'exit':42,'output':'{"outcome":"green"}'})]:
        stage['log_sha256'] = digest(stage['output'].encode())
        try: behavior(stage,'stream')
        except (ValueError,KeyError): rejected.append(name)
    assert len(rejected) == 4
    old = read_json((OUT/'historical-replay.json').read_bytes())
    calibrated = [behavior(r['stages']['caller'],'stream' if m.startswith('observable') else 'warnings')
                  for m,v in old['measurements'].items() for r in v['roles'].values() if r]
    assert calibrated.count('green') == 2 and calibrated.count('red-behavior') == 8
    for value in ({'exit':2,'cases':[]},{'exit':0,'cases':[{'name':n,'status':'error'} for n in NODES]}):
        try: consumer(value,0)
        except ValueError: rejected.append('consumer-setup')
    assert len(rejected) == 6
    save('selftest-v2.json',{'rejected':rejected,'calibrated_outcomes':calibrated,'all_passed':True})
    save('registration-v2.json',{'scope':'Assessor-only; original scores and states unchanged; diagnostic until separate official screen.',
         'previous_registration_sha256':E.sha(OUT/'registration.json'),'runner_sha256':E.sha(Path(__file__)),
         'source_sha256':E.sha(SOURCE),'fixtures':{p.name:E.sha(p) for p in FIX.iterdir()},
         'helper_source':str(helper.relative_to(ROOT)),'helper_source_sha256':E.sha(helper),
         'consumer_source_sha256':E.sha(SOURCE.with_name('warning-contract-replay.json')),
         'consumer_test_sha256':contract['base_test_sha256'],
         'consumer_command':['python','-B','/evidence/capture.py','base-tests','consumer'],
         'pytest_command':['python','-B','-m','pytest','-q','-p','no:cacheprovider','--basetemp=/evidence/consumer-temp','--junitxml=/evidence/consumer.xml',*[p+'::'+n for p,n in zip(FILES,NODES)]],
         'selftest_sha256':E.sha(OUT/'selftest-v2.json')})
    raise SystemExit(0)

target_path, receipt_path, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
reg = read_json((OUT/'registration-v2.json').read_bytes())
assert E.sha(Path(__file__)) == reg['runner_sha256'] and E.sha(SOURCE) == reg['source_sha256']
assert E.sha(OUT/'registration.json') == reg['previous_registration_sha256']
assert {p.name:E.sha(p) for p in FIX.iterdir()} == reg['fixtures']
target = read_pilot(target_path)
receipt = read_json(receipt_path.read_bytes())
checks = {}
for measure, row in receipt['measurements'].items():
    assert row['source_sha256'] == E.sha(SOURCE) and row['target_sha256'] == E.sha(target_path)
    checks[measure] = {role:behavior(v['stages']['caller'],'stream' if measure.startswith('observable') else 'warnings') if v else 'unavailable' for role,v in row['roles'].items()}
assert set(checks) == {'observable-red-green-replay','condition-scope-body-warnings'}
patches = {'base':None,'gold':target['submissions']['upstream']['patch'],
           'candidate-control':target['submissions']['control']['patch'],'candidate-develop':target['submissions']['develop']['patch'],
           'prior-develop':target['prior_develop'].get('patch')}
rows = {}
with lease(E.STATE,[0,1]):
    for role, patch in patches.items():
        if patch is None and role != 'base': rows[role] = {'outcome':'unavailable'}; continue
        folder = OUT/name/role
        folder.mkdir(parents=True)
        patch_path = folder/'proposal.patch' if patch else None
        if patch_path: patch_path.write_text(patch)
        grade = C.grading.grade(E.CASES['werkzeug'],target['base'],folder/'tree',patch_path,phases=[],target=target['merged'] if role=='gold' else None)
        assert not patch_path or grade['applied']
        work = folder/'tree/work'
        evidence = folder/'evidence'
        evidence.mkdir()
        shutil.copyfile(FIX/'capture.py',evidence/'capture.py')
        args,image = E.lab.docker(E.CASES['werkzeug'],work)
        mount = f'type=bind,src={work},dst=/work'; assert args.count(mount)==1
        args[args.index(mount)] += ',readonly'
        args += ['--mount',f'type=bind,src={evidence},dst=/evidence','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','-e','TMPDIR=/evidence','-e','TEMP=/evidence','-e','TMP=/evidence']
        for path in FILES: args += ['--mount',f'type=bind,src={FIX/Path(path).name},dst=/work/{path},readonly']
        run = subprocess.run([*args,image,*reg['consumer_command']],capture_output=True,timeout=60)
        (evidence/'driver.log').write_bytes(run.stdout+run.stderr)
        try:
            value = read_json(run.stdout)
            assert not run.stderr
            assert {p:value['files'][p] for p in FILES} == reg['consumer_test_sha256']
            assert value['files']['src/werkzeug/wrappers/response.py'] == E.sha(work/'src/werkzeug/wrappers/response.py')
            outcome = consumer(value,run.returncode)
        except (ValueError,KeyError,AssertionError) as error:
            value, outcome = {'setup_error':type(error).__name__}, 'setup-error'
        rows[role] = {'outcome':outcome,'patch_sha256':digest(patch.encode()) if patch is not None else None,
                      'driver_exit':run.returncode,'driver_log_sha256':E.sha(evidence/'driver.log'),'observed':value}
save(name+'.json',{'scope':'Diagnostic only; no primary scores or producer states changed.','release_eligible':False,
     'registration_sha256':E.sha(OUT/'registration-v2.json'),'target_sha256':E.sha(target_path),
     'behavior_receipt_sha256':E.sha(receipt_path),'producers_complete':receipt['producers_complete'],
     'producer_states':{r:v['state'] for r,v in target['submissions'].items()},'behavior':checks,'preserved_consumers':rows})
