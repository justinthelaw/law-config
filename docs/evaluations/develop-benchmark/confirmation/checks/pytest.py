import os
from pathlib import Path
from tempfile import TemporaryDirectory
from _pytest.tmpdir import TempPathFactory
with TemporaryDirectory() as tmp:
    d=Path(tmp)/"base"
    factory=TempPathFactory(d,3,"all",lambda *args: None,_ispytest=True)
    factory.getbasetemp()
    original=os.scandir
    if os.environ["PANEL_STAGE"]=="contract":
        (d/"unit0").mkdir()
        def check(path="."):
            if Path(path)==d:
                raise RuntimeError("listed the base directory")
            return original(path)
        os.scandir=check
    try:
        names=[factory.mktemp("unit").name for _ in range(3)]
    except RuntimeError as exc:
        if str(exc)!="listed the base directory":raise
        print(exc);raise SystemExit(42)
    finally:
        os.scandir=original
    expected=1 if (d/"unit3").exists() or os.environ["PANEL_STAGE"]=="contract" else 0
    print(names)
    raise SystemExit(0 if names==["unit"+str(n) for n in range(expected,expected+3)] else 42)
