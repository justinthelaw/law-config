# Communication and handoffs

These cases extend [fresh-context scenarios](../scenarios.md). Run the public
`fixtures/communication-*.json` through the shared fixture materializer; keep
`graders/communication-*.json` outside the tested agent's readable scope.

The existing owners remain authoritative: [intent, autonomy and handoffs](../../skills/develop/references/contract.md),
[implementation decisions](../../skills/iterate/references/implementation.md),
[validation evidence](../../skills/iterate/references/validation.md) and
[current-head delivery](../../skills/iterate/SKILL.md). This suite adds no policy.

## Cases

| Fixture suffix | Decision and observable evidence |
| --- | --- |
| `clarification` | Unresolved retention semantics; consequential question before choosing behavior, with safe independent progress. |
| `routine` | Authorized whitespace fix; actual artifact and checks without needless approval. |
| `steering-resume` | Worker evidence predates changed scope; preserve case, protected work, authority and handoff fields; verify the corrected artifact. |
| `exact-head` | Old green checks/review and an absent current-head check; communicate each remaining gate. |
| `polls` | Three unchanged observations then success; meaningful visible transition, honoring brief-update preference. |
| `readiness` | Candidate validation and old production runtime; distinguish readiness, deployment and approval. |
| `final` | Self-contained local handoff with verification provenance, incomplete review and next gate. |

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
