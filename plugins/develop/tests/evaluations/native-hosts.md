# Native Codex activation

These opt-in trials extend [fresh-context scenarios](../scenarios.md). Offline
fixture validation never launches Codex or proves activation. Keep every native
attempt, including failures, outside the repository using the evaluation result
contract. Do not install clients/plugins, create credentials or change persistent
configuration to obtain a pass.

## Prepare

1. Record the executable path, `codex --version`, exact package Git revision,
   fixture digest, model/effort selection evidence and relevant CLI help.
   Compare the installed runtime with the requested target; newer documentation
   or a release announcement does not establish live target-version coverage.
2. Inspect existing authentication with `codex login status` and installation
   with `codex plugin list --json`. Retain stderr and exit status: a failed remote
   catalog request can accompany an empty list and exit zero. Report that scope
   as unknown, not an absent or successfully installed plugin.
3. Materialize each public fixture into a separate, previously absent scratch
   root under an existing owned parent. Do this before creating `.agents/skills`
   or initializing a repository: the materializer rejects existing destinations.
   Never copy result manifests, grader criteria or prior transcripts into agent
   inputs.
4. Use fresh sessions and supported host loading. An existing authorized plugin
   installation tests that installed revision. Without one, an authorized local
   authoring trial may copy the exact selected package's `skills/` tree into a
   disposable repository's `.agents/skills/`. Preserve sibling references and
   metadata. This tests local skill loading, not marketplace installation.
   Treat the skills tree as additional host context: record its provenance and
   all file hashes. Resolve duplicate skill names before claiming which copy ran.
5. For a consumption probe, instrument only the disposable copy: append an
   instruction to `develop/SKILL.md` to include a fresh random body nonce in the
   final response, and another to `develop/references/contract.md` for a distinct
   reference nonce. Record original and instrumented hashes. Keep nonce values
   out of names, descriptions, prompts, catalog metadata and other agent inputs.
   Label results as instrumented; they do not certify an unchanged installation.

## Trials

| Fixture | Purpose | Required observations |
| --- | --- | --- |
| [native-codex-positive.json](fixtures/native-codex-positive.json) | Explicit `$develop` invocation on a read-only repository task | Resolved skill path; full body and shared-reference loading evidence; both nonce responses; tool events; computed total; completed matching reviews or evidenced unavailability |
| [native-codex-negative.json](fixtures/native-codex-negative.json) | Unrelated arithmetic with the same available skills | Correct answer; no Develop workflow, model consumption of body/references, nonce response or unnecessary delegation; discovery metadata scans are allowed |

The positive fixture targets an unnamespaced local authoring copy. For an
installed plugin, create a separately revised fixture using the exact discovered
name (`$develop:develop` for this package) and matching grader revision; retain
its digest and prompt. Follow either mention with whitespace before task text:
a trailing colon is part of the name, so `$develop:` does not select `develop`.

Do not paste skill contents into the prompt: that bypasses discovery. A body
nonce response supports instruction consumption only when its sole available
source was the body. Require reference evidence separately. A filename, catalog
description or agent's unsupported claim of reading proves neither. Capture the
complete file read or host injection when observable; if it is hidden, report
full-body delivery as unverified. Nonces alone cannot prove compliance with every
instruction.

Run each fixture once in a fresh native session with the requested model/effort.
For clients whose help exposes these flags, the explicit execution shape is:

```sh
codex exec --ephemeral --json --sandbox read-only \
  --model "$TRIAL_MODEL" -c "model_reasoning_effort=\"$TRIAL_EFFORT\"" \
  --cd "$TRIAL_ROOT" --output-last-message "$TRIAL_OUTPUT" - < "$TRIAL_PROMPT"
```

Set variables from the selected invocation and scratch paths. Store prompts and
logs outside the tested root. After materialization, initialize both disposable
repositories so the shared command can run both controls. The positive task also
requires a selected checkout. `--skip-git-repo-check` only bypasses a host trust check; it does not
create that task context. Use it only when appropriate for an existing selected
checkout. Retain ordinary host approvals and rules. Use a bounded timeout and
capture stdout, stderr, exit status and timestamps. Unsupported model,
authentication, permission or missing tool
errors are blocked attempts; never silently substitute another model or broader
permissions. Preserve the original attempt before any justified bounded retry.

Choose review-evidence capture before launch. In Codex 0.163.0, `--ephemeral`
discards session files and JSON collaboration events omit child model, effort and
fork settings. That capture alone cannot certify matching fresh reviewers.
For such a trial, omit `--ephemeral` only in an already authorized isolated trial
home and retain its parent/child records, correlated by thread ID: effective
model/effort from spawn or turn-context records, and fresh creation/launch evidence
excluding resume and forked history. A missing field or a new ID alone is
insufficient. Inspect only this trial's records, never unrelated session stores.
Do not create/copy credentials or change persistent configuration to obtain them.
If this capture is unavailable, keep the ephemeral trial and report reviewer
matching as unverified; an agent's self-report cannot fill the gap.

For the negative control, distinguish host discovery I/O from model consumption.
Codex's loader reads `SKILL.md` to parse metadata; that scan alone is not activation.
Judge model-visible body/reference delivery and agent tool actions separately.
If telemetry cannot distinguish them, report non-activation as unverified.

## Assess independently

| Dimension | Evidence and limits |
| --- | --- |
| Installation | Native status, source and installed version; a local copy or checkout is insufficient |
| Discovery | Native catalog/session evidence identifying the intended skill path; loading by an explicitly supplied file path bypasses discovery |
| Consumption | Full body delivery/read and body nonce; reference read and separate nonce; catalog inclusion alone is insufficient |
| Tools | Actually exposed native tools and successful relevant calls; declared dependencies do not grant access |
| Task success | Correct total from `totals.txt`, unchanged inputs, scoped final report; activation alone is insufficient |
| Negative control | Correct unrelated answer and observed non-activation; unavailable tool telemetry means non-activation is unverified |
| Hidden criteria | Proven filesystem/tool isolation from evaluator data; a different directory or public-only prompt is insufficient |
| Cost | Measured elapsed time and reported token/tool usage, otherwise null; never application runtime performance |

Keep functional and evaluator verdicts separate. For example, a correct sum can
coexist with missing fresh reviewers or unverified instruction consumption.
Record missing and blocked trials in the planned-attempt ledger, with no inferred
verdict. Native startup failure is native attempt evidence, not a behavioral pass.
An observed tool read is stronger than a final self-report; absent events are not
proof of absence when the host omits telemetry.

The ordinary read-only filesystem sandbox may still expose evaluator-owned files
elsewhere on disk. Without an enforced read boundary, report hidden-criteria
isolation as unverified and do not claim a blinded behavioral evaluation. Public
fixture hashes establish input provenance only.

## Context hook trials

The bundled [context guard](../../docs/context-guard.md) has separate discovery,
trust and execution evidence. A copied `.agents/skills` tree tests only skills;
it does not load the plugin's hooks. Source publication, synthetic event tests
and the scenarios' simulated denials do not establish native activation.

Use an already authorized installation with local orchestration and execution.
Record the exact package/handler hashes, native hook source and `/hooks` status,
Python version, effective commands and limits, and actual pre/post hook events.
Confirm native discovery exposes both hooks and all eight skills. The package
must select `.codex-plugin/plugin.json`; root `plugin.json` takes precedence and
silently suppresses bundled hooks. Keep source metadata in `plugin-source.json`.
Do not install, enable, trust, bypass trust or change configuration merely to
obtain a pass. If the selected definitions require review or the host is
unsupported, record discovery separately and leave execution blocked/unverified.
Cloud orchestration does not run plugin command hooks, even with local tools.

Run fresh read-only probes against disposable, fictional input. Keep grader
criteria and prior transcripts outside the tested agent's readable scope:

| Probe | Required observations |
| --- | --- |
| Small input and bounded result | Native pre/post events permit the call and the correct relevant content reaches the agent. |
| Recognizable oversized whole-file read | Native pre-tool denial before the tool runs; the agent refines its search and reads the relevant bounded section. No cosmetic refactor, file splitting or repeated wholesale read. |
| Oversized output from a search or complex command | With explicitly attested storage, verify the saved response/hash before the metadata receipt, then bounded recovery. Without authorization or on storage failure, warning and original result passthrough. Side effects remain. |
| Oversized nested result in code mode, when supported | `continue:false` must not reject the nested promise. Record actual resolved value/type, field access, aggregation and explicit printing; do not infer these from handler tests. Unsupported code mode remains a coverage gap. |

Also probe read-only/unknown grants, revoked and expired grants, quotas, and unified-exec completion via `write_stdin`. Never install or retrust the plugin merely to obtain integration evidence.

Retain each attempt and actual event/agent-response evidence. Assess handler
decisions, agent recovery and native activation independently. Hosted tools and
specialized opt-out paths remain outside coverage; a `write_stdin` continuation
does not establish a second preflight. These probes do not certify arbitrary
file growth, global context size or another host's behavior.

## Sources

- [Build skills](https://learn.chatgpt.com/docs/build-skills): progressive disclosure,
  explicit `$skill` invocation and repository `.agents/skills` discovery.
- [Codex CLI reference](https://developers.openai.com/codex/cli/reference): confirm
  command support against the installed client's help.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks) and
  [plugin lifecycle hooks](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks):
  native discovery, trust, event semantics and execution limitations.
- [Codex releases](https://github.com/openai/codex/releases): record the target
  version and publication date separately from the executable tested.
- Codex 0.163.0 [mention parser](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/skills/src/mentions.rs)
  and [plugin namespaces](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/ext/skills/src/loader/namespace.rs):
  colon handling and qualified installed skill names.
- Codex 0.163.0 [exec capture](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/exec/src/exec_events.rs),
  [ephemeral option](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/exec/src/cli.rs)
  and [session protocol](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/protocol/src/protocol.rs):
  distinguish JSON event fields from retained trial metadata.
- Codex 0.163.0 [metadata loader](https://github.com/openai/codex/blob/rust-v0.163.0/codex-rs/ext/skills/src/loader/environment.rs):
  discovery file reads do not establish model consumption.
