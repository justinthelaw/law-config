import os, warnings
import pytest
with warnings.catch_warnings(record=True) as seen:
    warnings.simplefilter("always")
    item = pytest.param(1, 2, marks=pytest.mark.skip, id="two")
ok = not seen and item.values == (1, 2) and item.id == "two" and len(item.marks) == 1
if os.environ["PANEL_STAGE"] in {"contract", "independent"}:
    cls = getattr(pytest, "ParameterSet", None)
    ok = ok and cls is type(item) and cls.__module__ == "pytest" and "ParameterSet" in pytest.__all__
    if ok and os.environ["PANEL_STAGE"] == "independent":
        with warnings.catch_warnings(record=True) as seen:
            warnings.simplefilter("always")
            cls((3,), (), "three")
        ok = any(issubclass(w.category, pytest.PytestDeprecationWarning) for w in seen)
print("public parameter type", ok)
raise SystemExit(0 if ok else 42)
