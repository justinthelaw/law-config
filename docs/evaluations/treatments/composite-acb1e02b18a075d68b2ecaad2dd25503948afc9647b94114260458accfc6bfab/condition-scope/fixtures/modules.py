"""Additional full original-module run on the v2 sealed reconstructed trees."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path.cwd(); OUT=ROOT/'tmp/pr-quality-panel/condition-scope-measure'
sys.path[:0]=[str(ROOT/'docs/evaluations'),str(ROOT/'docs/evaluations/tools')]
from native_panel import E
from cpu_leases import lease
from records import read_json, read_pilot, digest
FILES=['tests/test_internal.py','tests/test_test.py']
def save(name,value):
    with (OUT/name).open('x') as f:f.write(json.dumps(value,indent=2)+'\n')
def classify(value,exit):
    cases=value.get('cases',[])
    if exit!=0 or len(cases)!=74 or value.get('exit') not in (0,1) or any(c.get('status') not in ('passed','failure') for c in cases):
        return 'setup-error'
    passed=all(c['status']=='passed' for c in cases)
    if passed!=(value['exit']==0):return 'setup-error'
    return 'green' if passed else 'red-behavior'
os.environ.update(OAIPKG_DISABLE_META_MISSING='1',PYTHONDONTWRITEBYTECODE='1')
E.configure()
for key in ('TMPDIR','TMP','TEMP'):os.environ[key]=str(OUT/'scratch')
tempfile.tempdir=str(OUT/'scratch');os.environ['PANEL_CPUSET']='0,1';os.sched_setaffinity(0,{0,1})
if sys.argv[1]=='register':
    source=OUT/'consumer-fixture/capture.py'; code=source.read_text()
    for path,node in zip(FILES,['test_wrapper_internals','test_path_info_script_name_unquoting']):
        assert code.count(repr(path+'::'+node))==1
        code=code.replace(repr(path+'::'+node),repr(path))
    with (OUT/'modules-capture.py').open('x') as f:f.write(code)
    assert classify({'exit':0,'cases':[{'status':'passed'}]*74},0)=='green'
    assert classify({'exit':1,'cases':[{'status':'passed'}]*73+[{'status':'failure'}]},0)=='red-behavior'
    for value,exit in [({'exit':0,'cases':[]},0),({'exit':0,'cases':[{'status':'passed'}]*73},0),({'exit':0,'cases':[{'status':'error'}]*74},0),({'exit':0,'cases':[{'status':'failure'}]*74},0),({'exit':0,'cases':[{'status':'passed'}]*74},70)]:assert classify(value,exit)=='setup-error'
    previous=read_json((OUT/'registration-v2.json').read_bytes())
    save('registration-modules.json',{'scope':'Additional preserved original two-module assessor supplement; diagnostic only.',
         'v2_registration_sha256':E.sha(OUT/'registration-v2.json'),'runner_sha256':E.sha(Path(__file__)),
         'collector_source_sha256':E.sha(source),'collector_sha256':E.sha(OUT/'modules-capture.py'),
         'collector_change':'Only replace the two existing node-ID selection arguments with their full module paths.',
         'test_sha256':previous['consumer_test_sha256'],'expected_tests':74,
         'command':['python','-B','/evidence/capture.py','base-tests','modules'],
         'pytest_command':['python','-B','-m','pytest','-q','-p','no:cacheprovider','--basetemp=/evidence/modules-temp','--junitxml=/evidence/modules.xml',*FILES],
         'selftest':'74 pass green; 73 pass/1 failure red; 0/73 collected, test error, exit mismatch and driver setup rejected'})
    raise SystemExit(0)
target_path,v2_path,name=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
reg=read_json((OUT/'registration-modules.json').read_bytes()); v2=read_json(v2_path.read_bytes()); target=read_pilot(target_path)
assert E.sha(Path(__file__))==reg['runner_sha256'] and E.sha(OUT/'modules-capture.py')==reg['collector_sha256']
assert E.sha(OUT/'registration-v2.json')==reg['v2_registration_sha256']==v2['registration_sha256']
assert E.sha(target_path)==v2['target_sha256'] and not v2['release_eligible']
for path in FILES:assert E.sha(OUT/'consumer-fixture'/Path(path).name)==reg['test_sha256'][path]
roles={role:(OUT/v2_path.stem/role/'tree/work',row.get('patch_sha256')) for role,row in v2['preserved_consumers'].items() if row['outcome']!='unavailable'}
roles['constructive-positive']=(OUT/'positive/work',E.sha(OUT/'positive.patch'))
rows={}
with lease(E.STATE,[0,1]):
    for role,(work,patch_sha) in roles.items():
        assert digest(subprocess.check_output(['git','-C',work,'diff','--binary','HEAD']))==patch_sha if patch_sha else not subprocess.check_output(['git','-C',work,'diff','--binary','HEAD'])
        folder=OUT/name/role;folder.mkdir(parents=True)
        args,image=E.lab.docker(E.CASES['werkzeug'],work);mount=f'type=bind,src={work},dst=/work';assert args.count(mount)==1;args[args.index(mount)]+=',readonly'
        args+=['--mount',f'type=bind,src={folder},dst=/evidence','--mount',f'type=bind,src={OUT/"modules-capture.py"},dst=/evidence/capture.py,readonly','-e','PYTEST_DISABLE_PLUGIN_AUTOLOAD=1','-e','TMPDIR=/evidence','-e','TEMP=/evidence','-e','TMP=/evidence']
        for path in FILES:args+=['--mount',f'type=bind,src={OUT/"consumer-fixture"/Path(path).name},dst=/work/{path},readonly']
        run=subprocess.run([*args,image,*reg['command']],capture_output=True,timeout=90);(folder/'driver.log').write_bytes(run.stdout+run.stderr)
        try:
            value=read_json(run.stdout);assert not run.stderr
            assert {p:value['files'][p] for p in FILES}==reg['test_sha256']
            assert value['files']['src/werkzeug/wrappers/response.py']==E.sha(work/'src/werkzeug/wrappers/response.py')
            outcome=classify(value,run.returncode)
            xml=ET.parse(folder/'modules.xml');failure_ids=[c.attrib.get('classname','').replace('.','/')+'.py::'+c.attrib['name'] for c in xml.iter('testcase') if c.find('failure') is not None]
        except (ValueError,KeyError,AssertionError,ET.ParseError,FileNotFoundError) as error:value={'setup_error':type(error).__name__};outcome='setup-error';failure_ids=[]
        rows[role]={'outcome':outcome,'patch_sha256':patch_sha,'driver_exit':run.returncode,'driver_log_sha256':E.sha(folder/'driver.log'),'failure_ids':failure_ids,'observed':value}
save(name+'.json',{'scope':'Full original modules; additional diagnostic supplement; primary scores and states unchanged.','release_eligible':False,
     'registration_sha256':E.sha(OUT/'registration-modules.json'),'v2_receipt_sha256':E.sha(v2_path),'target_sha256':E.sha(target_path),
     'producers_complete':v2['producers_complete'],'producer_states':v2['producer_states'],'rows':rows})
