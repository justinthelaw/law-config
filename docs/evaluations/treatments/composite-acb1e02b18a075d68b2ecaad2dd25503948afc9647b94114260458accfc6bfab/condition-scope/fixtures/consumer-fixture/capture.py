"""Guest diagnostic: pinned production + selected/base test identity, no edits."""
import hashlib, importlib.metadata, json, pathlib, subprocess, sys, warnings
import xml.etree.ElementTree as ET
from werkzeug.wrappers import Response

paths=['src/werkzeug/wrappers/response.py','tests/test_internal.py','tests/test_test.py']
result={'python':sys.version.split()[0], 'pytest':importlib.metadata.version('pytest'),
        'files':{p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in paths}}
if sys.argv[1]=='selected':
    result['partition']=[]
    for body in [['x','y'],[b'x',b'y'],[b'x','y'],['x',b'y']]:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            response=Response(body); value=response.get_data(); response.close()
        result['partition'].append({'bytes':list(value),'warnings':[
            [w.category.__module__+'.'+w.category.__qualname__,str(w.message)] for w in caught]})
xml=pathlib.Path('/evidence')/(sys.argv[2]+'.xml')
command=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
         '--basetemp=/evidence/'+sys.argv[2]+'-temp','--junitxml='+str(xml),
         'tests/test_internal.py::test_wrapper_internals',
         'tests/test_test.py::test_path_info_script_name_unquoting']
p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
pathlib.Path('/evidence',sys.argv[2]+'.log').write_bytes(p.stdout)
result['exit']=p.returncode; result['cases']=[]
if xml.exists():
    for test in ET.parse(xml).iter('testcase'):
        bad=test.find('failure'); setup=test.find('error')
        result['cases'].append({'name':test.attrib['name'],'status':'failure' if bad is not None else 'error' if setup is not None else 'passed',
                                'message':bad.attrib.get('message','') if bad is not None else setup.attrib.get('message','') if setup is not None else ''})
else: result['setup_output']=p.stdout.decode(errors='replace')
print(json.dumps(result))
