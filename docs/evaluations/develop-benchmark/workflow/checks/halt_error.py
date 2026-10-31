"""Keep trailing bytes intact; shell substitution strips exactly the regression at issue."""
import subprocess

for expr, stderr in [
    ('{"utf8":"é"}', '{"utf8":"é"}'.encode()),
    ("[1,true]", b"[1,true]"), ("17", b"17"), ('"ok\\n"', b"ok\n"), ("null", b""),
]:
    got = subprocess.run(["./jq", "-nc", expr + "|halt_error(9)"], capture_output=True)
    if (got.returncode, got.stdout, got.stderr) != (9, b"", stderr):
        print(expr, got.returncode, got.stdout, got.stderr)
        raise SystemExit(42)
