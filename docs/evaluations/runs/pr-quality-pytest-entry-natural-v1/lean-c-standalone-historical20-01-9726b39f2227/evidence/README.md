# Adjudication evidence

The [run](../run.json) identifies each pinned base and merge. The [submissions](../submissions.jsonl) contain captured patches and adjudications. These witnesses use separate base and subject materializations and do not change the scored proposals.

| Flagged role | Evidence | Result and limit |
| --- | --- | --- |
| SymPy Develop | [Preservation probe](sympy/preserve-probe.py), [witness](sympy/witness.py), [baseline](sympy/baseline-preserve-probe.log), [subject](sympy/subject-preserve-probe.log) | The pinned Python worker passed the base and raised `NotImplementedError` on the subject for a tuple point. The Point3D controls passed both. |
| Libarchive Develop | [Preprocessing script](libarchive/reproduce.sh), [ruling](libarchive/ruling.json), target logs in this directory | Both Windows-target preprocessing checks passed the base and rejected the subject’s two-argument `fcntl` call. Missing SDK headers were skipped. No complete Windows build or link ran. |
| Packaging merge | [Witness](packaging/witness.py), [result](packaging/evidence.json) | The pinned Python worker accepted invalid replacement fields while the valid control passed. The base has no replacement API. |
| Pytest merge | [Witness](pytest/witness.py), [result](pytest/evidence.json) | The complete patch lacks the claimed constructor and test file. The public constructor emitted no warning. Runtime import used a generated version fixture in an isolated copy. Intent remains unknown. |

Run the Python witnesses from the materialized subject with its source directory on `PYTHONPATH`. The SymPy preservation probe also requires `PANEL_STAGE=preserve` and the pinned dependencies. The libarchive script expects sibling `baseline` and `subject` source directories. The sealed base, merge and patch identities are in the run bundle.
