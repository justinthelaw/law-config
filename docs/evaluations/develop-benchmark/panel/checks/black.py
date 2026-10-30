import ast, os
import black
base = "def sample( ):\n    value= 1\n"
inputs = [base] if os.environ["PANEL_STAGE"] == "preserve" else [
    "with (  # fmt: skip\n  res\n) == 1 and active:\n    target  =  3\n",
    "def emit():\n    yield not (  # fmt: skip\n        item\n    ) or other\n",
    "async def f():\n    async with (  # fmt: skip\n        handle\n    ) in services and enabled:\n        pass\n"]
for src in inputs:
    try:
        output = black.format_str(src, mode=black.Mode())
        ok = (ast.dump(ast.parse(src)) == ast.dump(ast.parse(output)) and
              black.format_str(output, mode=black.Mode()) == output)
        if "target  =" in src: ok &= "target = 3" in output and "(  # fmt: skip\n  res\n)" in output
        if src == base: ok &= "value = 1" in output
    except (ValueError, SyntaxError, AssertionError, black.InvalidInput) as err:
        print(type(err).__name__, err); ok = False
    if not ok:
        print(src); raise SystemExit(42)
