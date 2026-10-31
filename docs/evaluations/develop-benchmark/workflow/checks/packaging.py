"""Exercise the public replacement protocol, including inherited and reset prereleases."""
import copy
from packaging.specifiers import InvalidSpecifier, Specifier, SpecifierSet

def require(value, message):
    if not value:
        print(message)
        raise SystemExit(42)

one = Specifier(">=2.0a1", prereleases=False)
many = SpecifierSet(">=2.0a1,<3", prereleases=False)
require(hasattr(one, "__replace__") and hasattr(many, "__replace__"), "protocol absent")
require(copy.replace(one) is one and copy.replace(many) is many, "no-op replacement lost identity")

class Child(Specifier):
    pass
child = copy.replace(Child(">=1"), operator="==", version="4")
require(isinstance(child, Child) and str(child) == "==4", "subclass or replacement lost")
require(copy.replace(one, version="4").prereleases is False, "omitted override lost")
require(copy.replace(one, prereleases=None).prereleases is True, "explicit reset lost")
new = copy.replace(many, specifiers=[Specifier("!=5")], prereleases=True)
require(str(new) == "!=5" and new.prereleases is True, "iterable replacement lost")
require(copy.replace(many, specifiers="==6").prereleases is False, "set override lost")
require(str(one) == ">=2.0a1" and str(many) == "<3,>=2.0a1", "original mutated")
try:
    copy.replace(one, operator="<<<")
except InvalidSpecifier:
    pass
else:
    require(False, "invalid operator accepted")
