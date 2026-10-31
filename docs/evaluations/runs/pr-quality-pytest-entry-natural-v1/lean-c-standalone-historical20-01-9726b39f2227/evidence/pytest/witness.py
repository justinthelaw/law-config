import ast,json,warnings
from pathlib import Path
import pytest
p=Path('src/_pytest/mark/structures.py');tree=ast.parse(p.read_text());c=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='ParameterSet')
with warnings.catch_warnings(record=True) as seen:
 warnings.simplefilter('always'); obj=pytest.ParameterSet((1,),(),None)
print(json.dumps({'constructor_defined':any(isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name=='__new__' for x in c.body),'warnings':[type(w.message).__name__ for w in seen],'tuple_values':list(obj.values),'source_module':pytest.ParameterSet.__module__},sort_keys=True))
