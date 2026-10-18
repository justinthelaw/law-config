# Consequential design pilot

This bounded offline pilot extends the [fresh-context scenarios](../scenarios.md).
It calibrates a public behavior oracle and a held-out change, not measured agent
gains. Reuse the current [intent checkpoint](../../skills/develop/references/contract.md#review-gates);
no architecture skill, mandatory design document or new invariant framework.

## Unresolved ownership

[Public fixture](fixtures/architecture-ownership.json): implement latest-request
search with cancellation and late-result suppression. The internal owner is
undecided. A deterministic transport permits delayed and duplicate callbacks;
start is synchronous, never raises, and never invokes a callback inline. Threads,
transport failures, retries and application performance are outside this pilot.

[Evaluator-only grader](graders/architecture-ownership.json) holds a later request:
add autosave while callers share a transport. Freeze the first implementation,
rationale, tests and costs before releasing only that request. Judge the actual
adaptation, not whether the first design predicted autosave. A justified move of
ownership is allowed; no fixed class structure or line quota earns a pass.

| Dimension | Evidence |
| --- | --- |
| Ownership | Identify the owner of identity, cancel and close; explain concrete tradeoffs. |
| Caller burden | Compare frozen and adapted source; count duplicated lifecycle rules and required caller bookkeeping. |
| Correctness | Unchanged public tests plus independent caller, stale/duplicate callback and terminal-close probes. |
| Effort | Every attempt and phase, elapsed agent time and tokens when exposed; otherwise null. Diff size is only a proxy. |

The seeded transport-global owner passes the initial single-caller tests but
fails when autosave cancels a screen's request. A per-caller lifecycle owner
passes both, with the second caller delegating the same rules. These are authored
calibration implementations, not baseline/candidate agent results. The probe uses
public methods and observable callbacks/cancel counts, not internal class names.
Additional seeded defects calibrate completed-job cancellation, autosave close
interference, a stale callback first delivered after its replacement completes,
and nonterminal idle close. The probe checks both fresh and completed callers.

## Already-decided control

[Public fixture](fixtures/architecture-simple.json) asks for one conditional in an
existing label function. The [grader](graders/architecture-simple.json) checks
outputs and the absence of added design ceremony. Offline calibration proves the
minimal change works; only complete agent traces can establish actual ceremony,
approval requests or agent effort.

## Running and interpreting

From the repository root after the fixture-contract layer is present:

```sh
python -m unittest discover -s plugins/develop/tests -p test_architecture_probe.py -v
```

For fresh paired trials, materialize only `agent.inputs` using the shared
[fixture helper](../../scripts/evaluation.py). Give both arms the same initial
prompt/files, model/effort, tool budget and transport contract. The baseline uses
existing implementation guidance. Only the candidate receives this treatment:
"Within the existing intent checkpoint, identify the owner of request identity,
cancellation and close; briefly consider ownership and caller burden when choosing
a small design." Record that candidate-only addition with its exact guidance
revision; the shared revision-2 task prompt contains no such instruction.
Do not give tested agents this
document, grader JSON, probe source or calibration implementations. A working
directory alone is not isolation: use a host read boundary excluding the evaluator
tree and record verified/unverified isolation in the result contract.

Revision 1 included the ownership/caller-burden treatment in the shared prompt.
Any actual revision-1 pilot remains historical evidence from a single prompted
pilot, not an untreated baseline or a paired treatment comparison. Preserve its
original fixture/grader revisions and phase artifacts; do not relabel it as a
revision-2 trial. Grader isolation and unavailable agent costs remain unverified.

Freeze phase one, then release `held_out_change.prompt` to both arms with their
own implementation. Freeze phase two before an evaluator runs the unchanged
public tests and `probe_change(case, app, transport_type)` against the adaptation.
Run candidate code only in a disposable restricted environment; importing code is
execution, and the standard-library test helper is not a security sandbox.
Keep the simple control in both arms. Preserve failures, missing/blocked trials,
source/fixture/grader hashes and attribution using the shared result contract and
comparator. Record each phase as a planned attempt; identify the parent frozen
artifact in observations. Keep agent time/tokens under `cost`; any separately
measured application runtime belongs under `application_performance`.

Do not infer architecture quality from class count, passing initial tests or a
written rationale alone. Report functional and evaluator verdicts separately.
This fixture does not demonstrate a baseline guidance gap or justify changing
Develop policy without matching fresh-agent evidence.
