import json
from packaging.specifiers import Specifier
s=Specifier('>=1.0')
def run(**kw):
 try:
  r=s.__replace__(**kw);return {'accepted':True,'text':str(r),'operator':r.operator,'version':r.version,'prereleases':r.prereleases}
 except Exception as e:return {'accepted':False,'error':type(e).__name__}
print(json.dumps({'boundary':run(operator='>=1',version='.0'),'version_integer':run(version=2),'prereleases_integer':run(prereleases=1),'valid':run(operator='<',version='2')},sort_keys=True))
