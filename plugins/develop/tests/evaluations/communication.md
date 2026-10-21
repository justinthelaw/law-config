# Communication and handoffs

These cases extend [fresh-context scenarios](../scenarios.md). Run the public
`fixtures/communication-*.json`, `standards-*.json` and `unattended-*.json`
through the shared fixture materializer; keep matching graders outside the
tested agent's readable scope.

The existing owners remain authoritative: [intent, autonomy and handoffs](../../skills/develop/references/contract.md),
[implementation decisions](../../skills/iterate/references/implementation.md),
[validation evidence](../../skills/iterate/references/validation.md) and
[current-head delivery](../../skills/iterate/SKILL.md). This suite adds no policy.

## Cases

The exact prompts and fixture links live in the canonical [scenario catalog](../scenarios.md#communication-and-handoff-cases). This table is only a protocol index.

| Fixture suffix | Decision and observable evidence |
| --- | --- |
| `clarification` | Unresolved retention semantics; consequential question before choosing behavior, with safe independent progress. |
| `routine` | Authorized whitespace fix; actual artifact and checks without needless approval. |
| `steering-resume` | Worker evidence predates changed scope; preserve case, protected work, authority and handoff fields; verify the corrected artifact. |
| `exact-head` | Old green checks/review and an absent current-head check; communicate each remaining gate. |
| `polls` | Successive unchanged observations then success; meaningful visible transition, honoring brief-update preference. |
| `readiness` | Candidate validation and old production runtime; distinguish readiness, deployment and approval. |
| `final` | Self-contained local handoff with verification provenance, incomplete review and next gate. |
| `table`, `diagram` | Compare supplied measurements or explain a branching request path without losing unknowns or failure paths. |
| `interactive`, `live`, `fallback` | Exploration or accepted changing view when supported; actual capability evidence, honest fallback and caller format take precedence. |

The [standards and continuation cases](../scenarios.md#standards-and-unattended-continuation)
exercise the same contract: adopted scoped sources, inaccessible required evidence,
finite resume budgets, pending human decisions and reconciliation before replay.
Their controller time and provider records are fictional inputs. Do not infer
actual clock behavior, access controls, write idempotency or runtime persistence
from a model's response to these records.

## Staged polling

The public polling fixture contains only the first running observation. Its private
grader holds the later observations. After each host turn completes, capture its
actual events, then release exactly one later observation in the same session.
Keep future observations inaccessible until their turn; no real provider calls or
wall-clock sleeps are needed. Record each delivery boundary with the events.
A full stream supplied up front tests summarization only and cannot establish
suppression of redundant updates across polls. Missing inter-stage capture leaves
that behavior unverified. Do not materialize the private grader for this protocol.
Apply the same staging to `communication-live`: one unchanged status, then one
integration-check transition, retaining the missing approval. Use an actual
supported view tool or report its absence; a textual simulation does not verify
live rendering or updates. Never create a schedule to emulate this capability.

## Readability and format calibration

The private final-handoff and format graders contain paired good/poor examples.
Both sides preserve the relevant facts; the contrast is outcome ordering, plain
language, proportional detail, repetition, actionable limits or retrieval effort.
Use them to calibrate a human or independent semantic evaluator before grading
held-out responses. Keep examples and expected distinctions inaccessible to the
tested agent. They are evaluator controls, not observed model results.

Grade factual correctness and readability separately against the actual request.
Show the passage or artifact that supports each verdict. No word count, preferred
phrase, table marker, diagram syntax or channel count proves quality. A concise
answer can omit a material gate; a longer answer can be appropriate. Honor a
requested table or text answer. On a capable host, inspect the actual interactive
or live artifact and its behavior; otherwise grade the fallback and leave the
unavailable capability unverified. An unrendered source file is not rendering
evidence. Do not require visuals for a single simple result.

## Capture and grade

Use the shared result contract and comparator. Record all attempts, exact source
revision, fixture revision/digest, host/model/effort selection basis, isolation and
missing/blocked outcomes. Supplied provider and release records are fictional;
model execution against them is offline evidence, never live CI or deployment.

Capture the complete host event stream privately before normalization. Map only
assistant messages actually shown to the user (including final handoff) to `user`.
Incoming user messages are task inputs, not counted assistant updates. Map tool
calls/results to `tool`, and worker/watcher/internal logs to `helper`. A tool log
containing "ready" or a copied final response remains a tool log. If a worker
message is relayed to the user, record the actual visible relay separately.
Preserve event order and raw provenance references in observation text. Unknown
channel provenance or missing capture is unverified, not silence or zero cost.

Channel counts validate accounting only. Human or independent semantic grading
must cite actual events and resulting artifacts, check timing against decisions,
and compare claims with available evidence. Do not infer successful behavior
from words, message count, promised actions or an evaluator's own summary. A
single final response may suffice for a short task; no fixed cadence or minimum
update count applies. Never reconstruct hidden reasoning as user-visible output.

The synthetic controls in `test_communication.py` check that identical wording
on helper/tool channels does not increase visible counts, and that a real relay
does. They do not grade model behavior or establish communication gains.

## Conditional contract change

Run the baseline before deciding whether the shared contract needs clarification.
For each observed gap, retain the exact attempt, event/artifact evidence, existing
owner and violated outcome. Separate missing host capability/capture from an
instruction gap. Only a demonstrated, reproducible contract gap justifies a small
event-triggered clarification in that existing owner, honoring user/host
preferences and existing handoff fields. Re-run affected baseline/candidate cases
with matching fixture and host/model controls; report every attempt. A tested
no-change finding is valid; a pending, blocked or missing baseline is not evidence
for no change. Synthetic controls alone cannot resolve this conditional item.
