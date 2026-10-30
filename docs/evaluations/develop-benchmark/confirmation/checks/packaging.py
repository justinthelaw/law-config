import os
from unittest.mock import patch
from packaging import _ranges
from packaging.specifiers import SpecifierSet

# Count bound comparisons after both ranges are constructed. The first components
# overlap. Adding disjoint tails cannot change the answer or require scanning them.
def count(parts):
    left=SpecifierSet("==1").to_range()
    right=SpecifierSet("==1").to_range()
    for n in range(10,10+parts):
        left=left | SpecifierSet(f"=={3*n}").to_range()
        right=right | SpecifierSet(f"=={3*n+1}").to_range()
    from packaging.version import Version
    calls=0
    methods=("__lt__","__le__","__gt__","__ge__","__eq__")
    from contextlib import ExitStack
    def counter(f):
        def wrapper(self,other):
            nonlocal calls
            calls+=1
            return f(self,other)
        return wrapper
    with ExitStack() as stack:
        for method in methods:stack.enter_context(patch.object(Version,method,counter(getattr(Version,method))))
        if left.is_disjoint(right):raise SystemExit(42)
    return calls
if os.environ["PANEL_STAGE"]=="preserve":
    a=SpecifierSet(">=2").to_range();b=SpecifierSet("<2").to_range()
    raise SystemExit(0 if a.is_disjoint(b) else 42)
short,long=count(3),count(40)
print("bound comparisons",short,long)
if not short or not long:raise RuntimeError("comparison counters inactive")
raise SystemExit(0 if long <= short+8 else 42)
