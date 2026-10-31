"""Self-contained registered Black callers; deterministic pass/red/setup output."""
import ast, contextlib, io, json, os, sys, tempfile
sys.path.insert(0, os.getcwd())
DATA = {
    'operand': r'''import ast
import json
import black

cases = {
    "unary_trailer": "with -(  # fmt: skip\n    a\n).real and b:\n    pass\n",
    "directive_prefix": "with  left  + (  # fmt: skip\n    kept(  )\n) as value:\n    variable=  1\n",
}
for name, source in cases.items():
    original = ast.dump(ast.parse(source))
    try:
        formatted = black.format_str(source, mode=black.Mode())
        result = {"formatted": formatted, "preserved_ast": ast.dump(ast.parse(formatted)) == original,
                  "idempotent": black.format_str(formatted, mode=black.Mode()) == formatted,
                  "directive_line_unchanged": source.splitlines()[0] == formatted.splitlines()[0]}
    except Exception as exc:
        result = {"error_type": type(exc).__name__, "error": str(exc)}
    print(json.dumps({"case": name, **result}, sort_keys=True))
''',
    'conditional': r'''import ast
import json
import black

source = "def f():\n    yield a if b else (  # fmt: skip\n        c\n    ) +  d\n"
try:
    formatted = black.format_str(source, mode=black.Mode())
    result = {"formatted": formatted, "same_ast": ast.dump(ast.parse(formatted)) == ast.dump(ast.parse(source)),
              "idempotent": black.format_str(formatted, mode=black.Mode()) == formatted}
except Exception as exc:
    result = {"error_type": type(exc).__name__}
print(json.dumps(result, sort_keys=True))
''',
    'fixtures': {
        'fmtskip_nested_with.py': r'''before=  0
with first + (  # fmt: skip
    second(  )
) as resource:
    body=  1

after=  2

async def f():
    before=  0
    async with first * (  # fmt: skip
        second(  )
    ) +  last as resource:
        body=  1
    after=  2

# A neighboring context manager with a directly skipped bracket.
with (  # fmt: skip
    manager(  )
):
    body=  1

# output

before = 0
with first + (  # fmt: skip
    second(  )
) as resource:
    body = 1

after = 2


async def f():
    before = 0
    async with first * (  # fmt: skip
        second(  )
    ) + last as resource:
        body = 1
    after = 2


# A neighboring context manager with a directly skipped bracket.
with (  # fmt: skip
    manager(  )
):
    body = 1
''',
        'fmtskip_nested_yield.py': r'''def f():
    before=  0
    yield first * (  # fmt: skip
        x,  y
    ) +  last
    yield from first * (  # fmt: skip
        x,  y
    ) +  last
    after=  2

# A neighboring expression that is fully captured by the skip.
def g():
    yield first + (  # fmt: skip
        x,  y
    )
    after=  2

# output

def f():
    before = 0
    yield first * (  # fmt: skip
        x,  y
    ) + last
    yield from first * (  # fmt: skip
        x,  y
    ) + last
    after = 2


# A neighboring expression that is fully captured by the skip.
def g():
    yield first + (  # fmt: skip
        x,  y
    )
    after = 2
''',
    },
    'suffix': r'''def g():
    value = yield a + (  # fmt: skip
        b  +  c
    ), other
    after  =  2
''',
}
try:
    import black
    stage = os.environ["PANEL_STAGE"]
    checks = {}
    if stage in ("operand", "conditional"):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(compile(DATA[stage], "<frozen caller>", "exec"), {})
        rows = [json.loads(line) for line in stream.getvalue().splitlines()]
        if len(rows) != (2 if stage == "operand" else 1):
            raise RuntimeError("caller produced incomplete observations")
        for index, row in enumerate(rows):
            error = row.get("error_type")
            calibrated_unpack = (stage == "operand" and row.get("case") == "unary_trailer"
                                 and error == "ValueError"
                                 and row.get("error") == "not enough values to unpack (expected 2, got 1)")
            if error and error not in ("InvalidInput", "ASTSafetyError", "AssertionError") and not calibrated_unpack:
                raise RuntimeError("unclassified caller error: " + error)
            checks[str(index)] = not row.get("error_type") and all(row.get(k) for k in
                (("preserved_ast", "idempotent", "directive_line_unchanged") if stage == "operand" else ("same_ast", "idempotent")))
        if stage == "conditional":
            checks["whitespace"] = rows[0].get("formatted") == "def f():\n    yield a if b else (  # fmt: skip\n        c\n    ) +  d\n"
    elif stage == "suffix":
        source = DATA["suffix"]
        formatted = black.format_str(source, mode=black.Mode())
        black.assert_equivalent(source, formatted)
        black.assert_stable(source, formatted, black.Mode())
        checks["ast_stable"] = True
    elif stage in DATA["fixtures"]:
        from tests.test_format import check_file
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, stage), "w") as file:
                file.write(DATA["fixtures"][stage])
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                check_file(folder, stage)
        checks["expected_output"] = True
    else:
        raise KeyError(stage)
    outcome = "pass" if checks and all(checks.values()) else "behavioral-red"
    result = {"checks": checks, "outcome": outcome}
except Exception as exc:
    red = isinstance(exc, AssertionError) or type(exc).__name__ in ("InvalidInput", "ASTSafetyError")
    result = {"error_type": type(exc).__name__, "outcome": "behavioral-red" if red else "setup-error"}
print(json.dumps(result, sort_keys=True))
sys.exit({"pass": 0, "behavioral-red": 42, "setup-error": 70}[result["outcome"]])
