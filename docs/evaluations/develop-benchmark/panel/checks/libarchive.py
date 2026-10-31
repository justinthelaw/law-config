import io, os, pathlib, subprocess, tarfile, tempfile
tar = pathlib.Path("build-panel/bin/bsdtar").resolve(strict=True)
with tempfile.TemporaryDirectory() as dir:
    d=pathlib.Path(dir)
    with tarfile.open(d/"inputs.tar","w") as archive:
        for name, data in [("one",b"abc"),("two",b"de")]:
            entry=tarfile.TarInfo(name);entry.size=len(data);archive.addfile(entry,io.BytesIO(data))
    if os.environ["PANEL_STAGE"] == "preserve":
        p = subprocess.run([tar,"-xOf",d/"inputs.tar"],capture_output=True)
        good = p.returncode == 0 and p.stdout == b"abcde"
    else:
        dst=d/"out";dst.write_bytes(b"prefix:")
        # Shell append redirection leaves the initial offset at zero.
        with os.fdopen(os.open(dst, os.O_WRONLY | os.O_APPEND), "wb") as out:
            p=subprocess.run([tar,"-xOf",d/"inputs.tar"],stdout=out,stderr=subprocess.PIPE)
        good=p.returncode == 0 and dst.read_bytes() == b"prefix:abcde"
    print(p.returncode,p.stderr,good)
    raise SystemExit(0 if good else 42)
