import os
import black
ordinary = os.environ["PANEL_STAGE"] != "contract"
src = "if enabled: print(0)\nelse:\n    print(1)\nvalue=  3\n" if not ordinary else "value=  3\n"
wanted = src.replace("value=  3","value = 3")
try:
    got = black.format_str(src, mode=black.Mode(), lines=[(4,4)] if not ordinary else [(1,1)])
except black.parsing.InvalidInput as exc:
    if "cannot parse" not in str(exc).lower():raise
    print(type(exc).__name__,exc)
    raise SystemExit(42)
print(repr(got))
raise SystemExit(0 if got==wanted else 42)
