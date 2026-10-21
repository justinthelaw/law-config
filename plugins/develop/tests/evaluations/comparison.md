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

For review cost, predeclare the same reader task on each side: locate the outcome,
supporting evidence, unresolved gate and next action. Record actual review time,
clarification turns, material corrections and mistaken readiness decisions in a
separate private review ledger linked to attempt IDs. Include reviewer/context
identity and timing method; counterbalance presentation order where practical.
Keep this human review cost separate from agent cost and application performance.
Missing measurements remain unknown. Report quality and cost together, including
failed and incomplete attempts; fewer words or messages alone are not savings.
The comparator does not measure these fields or infer a causal benefit.

Measure mandatory agent-review overhead separately in the same private ledger.
For each invocation, record its routine/no-op or consequential stratum, checkpoint,
lane, round, reviewed revision, reviewer identity, elapsed-time method and available
token/USD evidence. Keep coordinator time, parallel checkpoint elapsed time and
summed reviewer time distinct; unknown measurements remain null. Link material
findings to verified repairs or rejected findings so cost is assessed with benefit,
including failed rounds and retries. Do not count schema inspection as an
independent review. A single task measures that task only; retain unmeasured strata
and cross-task comparisons as unfinished. Preserve the existing review gates
until comparable observations support a separately authorized policy change.

Finite attempt costs must also produce finite totals and deltas. Arithmetic
overflow is invalid input (exit 2), never JSON `Infinity` or `NaN`; integer token
totals remain exact.
