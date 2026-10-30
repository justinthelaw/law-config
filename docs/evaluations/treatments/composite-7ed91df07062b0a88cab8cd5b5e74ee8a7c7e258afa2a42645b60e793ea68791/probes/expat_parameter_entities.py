"""Exercise literal and real parameter references in the public, DTD-enabled Expat parser."""
import ctypes as C
import json
from pathlib import Path
import resource

resource.setrlimit(resource.RLIMIT_CPU, (10, 12))
resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
lib = C.CDLL(str(Path("build-panel/libexpat.so").resolve()))
for fn, args, ret in (
    ("XML_ParserCreate", [C.c_char_p], C.c_void_p),
    ("XML_SetParamEntityParsing", [C.c_void_p, C.c_int], C.c_int),
    ("XML_Parse", [C.c_void_p, C.c_char_p, C.c_int, C.c_int], C.c_int),
    ("XML_GetErrorCode", [C.c_void_p], C.c_int),
    ("XML_ErrorString", [C.c_int], C.c_char_p),
    ("XML_ParserFree", [C.c_void_p], None),
):
    call = getattr(lib, fn)
    call.argtypes, call.restype = args, ret

def check(declarations):
    document = f"<!DOCTYPE r [{declarations}]><r/>".encode()
    parser = lib.XML_ParserCreate(None)
    if not parser:
        raise MemoryError("parser allocation")
    try:
        if lib.XML_SetParamEntityParsing(parser, 2) != 1:
            raise NotImplementedError("DTD parameter parsing unavailable")
        status = lib.XML_Parse(parser, document, len(document), 1)
        code = lib.XML_GetErrorCode(parser)
        return {"accepted": status == 1, "error_code": code, "error": (lib.XML_ErrorString(code) or b"").decode()}
    finally:
        lib.XML_ParserFree(parser)

def declare(name, text):
    return f'<!ENTITY % {name} "{text}">'

chain = declare("b0", "<!--leaf-->") + "".join(declare(f"b{i}", f"&#37;b{i-1};" * 2) for i in range(1, 65))
cases = {
    "simple_comment": declare("lit", "<!--text-->") + "%lit;",
    "unused_chain": chain,
    "literal_cycle_comment": declare("lit", "<!--&#37;lit;-->") + "%lit;",
    "literal_cycle_pi": declare("lit", "<?q &#37;lit;?>") + "%lit;",
    "literal_chain_comment": chain + declare("lit", "<!--&#37;b64;-->") + "%lit;",
    "literal_chain_pi": chain + declare("lit", "<?q &#37;b64;?>") + "%lit;",
    "real_cycle": declare("lit", "&#37;lit;") + "%lit;",
    "real_chain": chain + "%b64;",
}
for name, xml in cases.items():
    print(json.dumps({"case": name, **check(xml)}), flush=True)
