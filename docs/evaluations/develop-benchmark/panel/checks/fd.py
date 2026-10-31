import os, pathlib, subprocess, tempfile
binary = pathlib.Path("target/debug/fd").resolve(strict=True)
with tempfile.TemporaryDirectory() as d:
    (pathlib.Path(d)/"one-byte").write_text("x")
    if os.environ["PANEL_STAGE"] == "preserve":
        p = subprocess.run([binary, "--size", "1b", "one-byte", d], capture_output=True)
        ok = p.returncode == 0 and b"one-byte" in p.stdout
    else:
        ok = True
        subprocess.run(["cargo","build","--locked","--offline","--release","--bin","fd"],check=True)
        for executable in (binary, pathlib.Path("target/release/fd").resolve(strict=True)):
            for value in ("18446744073709551615kb", "+18446744073709552k", "-17179869184GiB"):
                p = subprocess.run([executable, "--size", value, ".", d], capture_output=True)
                reject = p.returncode in (1, 2) and b"valid size" in p.stderr.lower()
                print(executable.parent.name, value, p.returncode, p.stderr[:200])
                ok &= reject and b"panick" not in p.stderr.lower()
    if not ok: raise SystemExit(42)
