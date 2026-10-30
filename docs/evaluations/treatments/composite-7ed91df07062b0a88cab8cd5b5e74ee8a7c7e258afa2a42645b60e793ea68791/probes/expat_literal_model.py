"""Classify the public parser's acceptance and protection error categories."""
import contextlib
import io
import json
from pathlib import Path
import runpy

EXPECTED = {"simple_comment": True, "unused_chain": True, "literal_cycle_comment": True,
            "literal_cycle_pi": True, "literal_chain_comment": True, "literal_chain_pi": True,
            "real_cycle": False, "real_chain": False}
# Public XML_Error enum: XML_ERROR_RECURSIVE_ENTITY_REF and XML_ERROR_AMPLIFICATION_LIMIT_BREACH.
ERRORS = {"real_cycle": 12, "real_chain": 43}

def assess(rows):
    if len(rows)!=len(EXPECTED) or {row['case'] for row in rows}!=set(EXPECTED):
        raise ValueError('incomplete observations')
    if any(row['error_code']==1 for row in rows):
        raise MemoryError('parser allocation')
    if any(row['error_code']==25 for row in rows):
        raise NotImplementedError('XML DTD feature unavailable')
    return [row['case'] for row in rows if row['accepted']!=EXPECTED[row['case']]
            or (row['case'] in ERRORS and row['error_code']!=ERRORS[row['case']])]

def main():
    try:
        captured=io.StringIO()
        with contextlib.redirect_stdout(captured):
            runpy.run_path(str(Path(__file__).with_name('expat_parameter_entities.py')))
        rows=[json.loads(line) for line in captured.getvalue().splitlines()]
        failed=assess(rows)
    except (ImportError,OSError,AssertionError,AttributeError,MemoryError,NotImplementedError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'outcome':'infrastructure-error','class':type(exc).__name__}))
        return 70
    print(json.dumps({'outcome':'red-behavior' if failed else 'green','cases':len(rows),
                      'failures':failed,'observations':rows}))
    return 42 if failed else 0

if __name__=='__main__':
    raise SystemExit(main())
