import subprocess
for program, stderr in [('null|halt_error(4)', b''), ('"x\\n"|halt_error(4)', b'x\n')]:
    out = subprocess.run(["./jq", "-nc", program], capture_output=True)
    if (out.returncode, out.stdout, out.stderr) != (4, b"", stderr):
        print(program, out.returncode, out.stdout, out.stderr)
        raise SystemExit(42)
