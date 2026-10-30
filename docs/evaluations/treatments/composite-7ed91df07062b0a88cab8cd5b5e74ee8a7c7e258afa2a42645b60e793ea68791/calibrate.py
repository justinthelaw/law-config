"""Replay five exposed Werkzeug artifacts. Infrastructure never establishes behavioral red/green."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path

EXPECTED={'werkzeug':144,'expat':8}

def classify(case,returncode,stdout):
    if returncode<0 or returncode>=128:
        return {'outcome':'infrastructure-error','class':'signal','exit':returncode}
    try:
        data=json.loads(stdout)
    except (ValueError,UnicodeError):
        return {'outcome':'infrastructure-error','class':'unparseable-output','exit':returncode}
    if not isinstance(data,dict):
        return {'outcome':'infrastructure-error','class':'invalid-output','exit':returncode}
    if data.get('outcome')=='infrastructure-error':
        return {'outcome':'infrastructure-error','class':data.get('class','probe-setup'),'exit':returncode,'observed':data}
    count=data.get('generated_cases' if case=='werkzeug' else 'cases')
    failures=data.get('failing_cases') if case=='werkzeug' else len(data.get('failures',[])) if isinstance(data.get('failures'),list) else None
    valid=(returncode in (0,42) and type(count) is int and count==EXPECTED[case]
           and type(failures) is int and 0<=failures<=count
           and data.get('outcome')==('red-behavior' if failures else 'green')
           and returncode==(42 if failures else 0))
    if not valid:
        return {'outcome':'infrastructure-error','class':'invalid-output','exit':returncode}
    return {'outcome':data['outcome'],'exit':returncode,'observed':data}

def run_command(command,case,cwd=None,timeout=30):
    try:
        result=subprocess.run(command,cwd=cwd,capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return {'outcome':'infrastructure-error','class':'timeout','exit':None},exc.stdout or b'',exc.stderr or b''
    except OSError as exc:
        return {'outcome':'infrastructure-error','class':'launch-'+type(exc).__name__,'exit':None},b'',b''
    return classify(case,result.returncode,result.stdout),result.stdout,result.stderr

def main():
    sys.path.insert(0,'docs/evaluations')
    import benchmark as B
    from native_panel import C,E
    from records import read_pilot
    from cpu_leases import lease
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--werkzeug-only',action='store_true',help='Repeat the actual five trees from portable sealed patches.')
    options=parser.parse_args()
    B.configure_temp();E.configure()
    cpus=sorted(os.sched_getaffinity(0))[:2]
    if len(cpus)!=2:raise ValueError('two available CPUs required')
    os.environ['PANEL_CPUSET']=','.join(map(str,cpus))
    root=Path(__file__).resolve().parent;probes=root/'probes'
    results=E.STATE/'observable-replay-calibration';results.mkdir(exist_ok=True)
    out=Path(tempfile.mkdtemp(prefix='calibration-',dir=results))
    source=Path(__file__).read_bytes();(out/'calibration-source.py').write_bytes(source)
    frozen=out/'probes';frozen.mkdir()
    for name in ('werkzeug_stream_model.py','expat_literal_model.py','expat_parameter_entities.py'):
        (frozen/name).write_bytes((probes/name).read_bytes())
    probes=frozen
    pilot=read_pilot(B.pilot_file('review-entry-werkzeug-01'));case=E.CASES['werkzeug']
    patches={'base':None};merged=out/'merged.patch';merged.write_text(pilot['submissions']['upstream']['patch'])
    assert E.sha(merged)==pilot['submissions']['upstream']['patch_sha256'];patches['original-merge']=merged
    native={}
    for role,cohort,arm in [('stock','candidate','control'),('develop-3b','prior','develop'),('develop-c979','candidate','develop')]:
        saved=pilot['prior_develop'] if cohort=='prior' else pilot['submissions'][arm]
        content=saved.get('patch')
        if 'patch' not in saved and saved['patch_sha256'] is not None:
            from records import read_json,verify_artifacts
            artifacts=read_json(B.pilot_file('review-entry-werkzeug-01').with_name('prior.json').read_bytes())
            verify_artifacts('prior Develop',saved,artifacts);content=artifacts['patch']
        if content is None:raise ValueError('missing sealed patch')
        patch=out/(role+'.patch');patch.write_text(content)
        assert E.sha(patch)==saved['patch_sha256'];patches[role]=patch
        treatment=pilot['treatments'][cohort]
        native[role]={'installed_package_sha256':treatment if arm=='develop' else None,
           'paired_plan_treatment_sha256':treatment,'state':saved['state'],
           'estimated_usd':saved['effort']['estimated_usd'],'coverage':saved['effort']['coverage']}
    if not (E.dependencies(case)/'ready').is_file():raise FileNotFoundError('prepared dependency fixture unavailable')
    rows={}
    def observe(key,role,work,names):
        args,image=E.lab.docker(E.CASES[key],work);mount=f'type=bind,src={work},dst=/work'
        assert args.count(mount)==1;args[args.index(mount)]=mount+',readonly'
        box='behavior-'+out.name+'-'+key+'-'+role;args+=['--name',box]
        for name in names:args+=['--mount',f'type=bind,src={probes/name},dst=/oracle/{name},readonly']
        row,stdout,stderr=run_command([*args,image,'python3','-B','/oracle/'+names[0]],key)
        if row.get('class')=='timeout':subprocess.run(['docker','stop','-t','1',box],capture_output=True,timeout=10)
        path=out/(key+'-'+role+'.stdout.json');path.write_bytes(stdout)
        (out/(key+'-'+role+'.stderr.log')).write_bytes(stderr)
        return {**row,'stdout_sha256':E.sha(path)}
    with lease(E.STATE,cpus):
        for role,patch in patches.items():
            grade=C.grading.grade(case,case['base'],out/('werkzeug-'+role),patch,phases=[],target=case['gold'] if role=='original-merge' else None)
            assert patch is None or grade['applied']
            rows['werkzeug/'+role]={**observe('werkzeug',role,out/('werkzeug-'+role)/'work',['werkzeug_stream_model.py']),
                                    'patch_sha256':E.sha(patch) if patch else None,'native_proposal':native.get(role)}
    record={'scope':'Corrected model-free calibration on exposed sealed artifacts only. Prior ignored observations and immutable scores remain unchanged.',
        'program_sha256':hashlib.sha256(source).hexdigest(),'probe_sha256':{name:E.sha(probes/name) for name in ('werkzeug_stream_model.py','expat_literal_model.py','expat_parameter_entities.py')},
        'source_result_sha256':E.sha(B.pilot_file('review-entry-werkzeug-01')),
        'base':case['base'],'merged':case['gold'],'cpus':cpus,'seed':None,
        'corpus':'Eight fixed strings, one/two writes and two normalization orders. Shrinking preserves the failed public operation.',
        'rows':rows}
    expected={'werkzeug/base':42,'werkzeug/original-merge':42,'werkzeug/stock':42,'werkzeug/develop-3b':0,'werkzeug/develop-c979':42}
    expected={k:v for k,v in expected.items() if k in rows}
    record['expected_control_exits']=expected
    record['calibration_valid']=all(rows[k]['exit']==v and rows[k]['outcome']!='infrastructure-error' for k,v in expected.items())
    (out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
    (results/'latest-calibration.txt').write_text(out.name+'\n')
    print(out.name,{key:(row['outcome'],row.get('observed',{}).get('failing_cases',row.get('observed',{}).get('failures'))) for key,row in rows.items()})
    return 70 if any(r['outcome']=='infrastructure-error' for r in rows.values()) else 0 if record['calibration_valid'] else 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ImportError,OSError,ValueError,KeyError,AssertionError) as exc:
        print(json.dumps({'outcome':'infrastructure-error','class':type(exc).__name__}))
        raise SystemExit(70)
