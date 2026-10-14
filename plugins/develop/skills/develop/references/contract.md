# Shared invocation contract

Read once for repository workflows and direct `iterate`, `upgrade` or `clean` calls. Standalone `kaizen` and `adversarial-loop` follow their own scoped protocols without repository discovery or implementation prerequisites.

## Intent and ownership

Use one invocation ID and coordinator. Preserve original and ordered steering messages verbatim, with secrets/unrelated private content redacted. Record outcome, delivery mode, targets, constraints, acceptance criteria, authorized actions, thread signing preference, artifact revision and original coordinator model/effort. Summaries supplement the messages. Keep packets private; never commit transcripts.

New steering supersedes conflicting requirements, preserves other goals and increments the intent revision. Invalidate affected reviews. Capture model/class and effort from runtime metadata or documented inheritance; never guess them.

## Targets

Use the explicitly selected repositories or an unambiguous current checkout. If repository scope is missing, ask one focused question before expanding discovery. Fleet work requires the user's selected or configured owner, provider and inclusion rules; never infer the package author's account. Enumerate authorized fleets with complete authenticated pagination. Unless narrowed, include owned non-archived repositories and forks; activity, stars and PR counts do not define active. Report disabled/inaccessible targets and incomplete coverage.

Publication of existing changes and monitoring use the explicitly selected repository, or the current checkout and its initialized submodules when unambiguous. They do not expand to the account-wide default or sibling repositories. Record the selected roots once and preserve them across publication and repair handoffs.

Explicit repositories, URLs, providers, exclusions or an unambiguous continuation override that default. A checkout is selected only when the request/context refers to it. Preserve other providers' identities.

Prefer connected provider tools, then permitted authenticated CLI/API and Git. Selected-repository integrations and public-only search provide partial coverage: report that limit and continue verified targets. Recheck archive status before writes; archived targets need explicit authorization. Report no-ops without manufacturing changes or empty PRs.

## Dependencies and autonomy

- `upgrade` owns assessment and migration decisions; `iterate` owns implementation and delivery. Use `clean` only when requested or when an identified resource constraint needs authorized cleanup. Review-only work does not enter cleanup or implementation.
- Resolve qualified installed skills or their packaged sibling files. The bundled [implementation guidance](../../iterate/references/implementation.md) is sufficient without an external workflow plugin; use compatible installed guidance when useful. Do not invent tools, dependencies or capabilities.
- Preserve explicit user/repository preferences for planning and execution. A scoped implementation request permits routine implementation decisions; honor an explicit plan-only boundary or requested approval. Do not introduce repeated internal permission prompts. Independent review cannot replace a required human decision or host approval.
- Preserve repository instructions, contribution requirements, host approvals, access controls and explicit user stops. Review cannot supply missing authorization. Merges, destructive actions, production changes and person-directed messages require applicable authorization.
- If a required dependency or fresh matching reviewer is unavailable, finish safe read-only discovery/preparation and report the exact gap before implementation. Try permitted existing access paths; do not install/connect integrations without authorization. Continue unaffected targets.
- Publishing follows the requested delivery scope. Preserve unrelated work and never force-push over others' changes.

## Authorization

Reading, comparing, installing or mentioning a skill does not authorize commits or publication. Record the operations and exact targets authorized by the user's request. Reuse existing authority within that scope; do not ask again merely because a nested skill or CI repair pass begins. New repositories, destinations or materially different actions need their own authority.

Keep local implementation, ordinary publication, history replacement, external issue/PR changes, review-thread resolution, merging and deletion distinct. A review verdict is evidence, not permission. The read-only watcher never posts review requests, resolves threads, reruns workflows or changes repository state. Prepare concrete proposed external changes before requesting any missing authorization. Host approval and security controls remain separate.

## Nonblocking commit signing

Default to `prefer`: sign when an existing signer is configured and works noninteractively; otherwise make an unsigned commit. `unsigned` explicitly selects unsigned commits for the thread. Honor an existing user choice without another question. When useful and supported, ask for this preference once with `request_user_input` or the host equivalent; tool unavailability or an unanswered optional question uses the default, not a new gate. The preference belongs to the thread contract, survives handoffs and must be included in compaction/continuation summaries. It is not a persistent Git setting or authorization to commit/push.

Use a bounded, noninteractive signing attempt. If only signing is unavailable or fails, inspect HEAD and the index to establish whether a commit was created before retrying unsigned with a command-scoped setting such as `git -c commit.gpgsign=false commit`. Never repeat a successful commit. Do not seek key setup, pinentry interaction or host escalation solely for signing; do not copy signing keys or change persistent Git configuration. Honor the configured signing backend instead of requiring OpenPGP.

Unsigned outgoing commits and unavailable local signature verification are not blockers. Report signed, unsigned or unverified status accurately; only claim a verified signature after verification. Identity, hook, conflict and other repository failures are separate and must not be bypassed as signing failures. Actual server-enforced signed-commit rules may reject a push: preserve that protection, report the publication constraint and continue unaffected work. Commit signing preferences do not apply to signed tags, signed pushes or DCO sign-offs.

## Handoffs

Pass the invocation/intent revisions, literal messages, delivery mode, selected roots, applicable instructions, existing authorization, thread signing preference, acceptance criteria, protected work, original model/effort, artifact paths and revisions, evidence and open findings.

Return handled scope, current artifacts, changes/no-op, verification and limitations, findings, blockers and next gate. `iterate` owns repository/CI delivery; `upgrade` owns its dependency ledger and combined report; `clean` owns resource measurements. The coordinator integrates results.

## Review gates

The coordinator runs `adversarial-loop` at **intent** before consequential work and **evidence** before completion, including read-only, blocked and no-op invocations. Review the actual discovery result when there is no diff. Nested workers reuse these gates; reviewers never recurse.

Repeat affected checkpoints after material steering, design/scope changes, repairs or a new pushed head. Identify both intent and artifact revisions. Missing fresh agents or unverified model/effort means blocked/unverified, never a solo substitute or pass.

Completion requires task validation and current independent review without unresolved material findings. Internal review does not replace required tests, CI, provider reviews or human approvals, and never authorizes merging.
