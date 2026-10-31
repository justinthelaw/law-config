import os
from packaging.specifiers import SpecifierSet
s = SpecifierSet(">=1")
if os.environ["PANEL_STAGE"] == "preserve":
    good = "1.2" in s and "0.9" not in s
else:
    good = hasattr(s, "__replace__") and s.__replace__(specifiers=">=1") is s
print("contains/stable identity:", good)
raise SystemExit(0 if good else 42)
