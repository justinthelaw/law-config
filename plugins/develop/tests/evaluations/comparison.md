# Compare recorded evaluations

Use the [result contract](README.md) and declare paired attempt IDs before running
baseline and candidate. Keep input/fixture and hidden-grader hashes, host version, model, effort,
selection basis and evidence kind identical; source commits may differ.

```bash
python plugins/develop/scripts/compare_evaluations.py baseline.json candidate.json > comparison.json
```

Exit `0` means complete recorded candidate passes, `1` a recorded candidate
failure, and `2` invalid, incompatible or incomplete evidence. None certifies
native activation, hidden grader isolation or a causal improvement. The report
retains both full manifests, every attempt, outcomes and isolation limitations.
Validate fixture hashes against the actual inputs separately; supplied identities
are attribution, not authenticated provenance.

Retries use new IDs. An unpaired retry remains incomplete; omitted planned
records are invalid. Do not drop cases, failures or earlier attempts to obtain a
complete comparison. Preserve the predeclared plan outside the tested agent's
reach so changes to that plan are reviewable.

Channel counts separate actual `user` messages from `tool` and `helper` output.
Counts do not grade communication quality. Agent wall time, tokens and USD are
reported separately from application metrics; unknown costs remain null. Cost
deltas require identical plans and complete measurements. Different host/model
conditions are rejected rather than attributed to the candidate instructions.

Finite attempt costs must also produce finite totals and deltas. Arithmetic
overflow is invalid input (exit 2), never JSON `Infinity` or `NaN`; integer token
totals remain exact.
