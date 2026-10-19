# Documentation drift

Use when reviewing or maintaining selected documentation. Review-only produces findings; edits require the user's implementation scope.

- Read owning instructions and explicit exclusions before discovery. Select maintained docs relevant to the task; omit generated, vendored, cached and runtime data unless requested. Repository-specific protected files and writing conventions stay with the repository.
- Compare claims, commands, paths, examples and diagrams with current source, tests, configuration and build/workflow definitions. Recent commits and remembered behavior are investigation leads, not proof that documentation is wrong.
- Preserve owner boundaries: explain integration where it is owned and implementation where it is maintained. Reference one authoritative explanation instead of duplicating it. Use the repository's style; avoid rewriting accurate prose for preference alone.
- Report confirmed drift with the document location, conflicting current evidence and smallest correction. Distinguish a verified no-change result from unavailable evidence or out-of-scope material. Do not claim documentation is current when its relevant source could not be inspected.
- Repair only confirmed in-scope drift. Validate local links, referenced commands and relevant doc/build checks at the touched owner. Do not execute deployment or destructive examples as link verification, or hand-edit generated outputs.

## Focused source reading

Combine path and content clues before broad reads. Use `rg --files` with owner paths and glob filters to find candidates, then `rg -n` within those paths for exact terms (`-F`), heading patterns or symbol names. Read bounded sections around relevant matches, including their definitions, callers, constraints and tests as needed to understand the claim.

When results are noisy or truncated, refine paths, globs and terms before widening the search. Expand to another owner only when evidence points there or the required coverage demands it. A bounded excerpt is a navigation aid, not proof of complete coverage: inspect the full relevant contract, diff or authorized inventory when the task requires it, and report any coverage gaps. Keep useful comments and coherent ownership; cosmetic splitting or removing explanation merely to pass a [staged-file byte budget](staged-file-size.md) is not a documentation improvement.

## Skill and plugin documentation

For Codex skill/plugin changes, compare layout, triggers, metadata and references with current official [skill](https://learn.chatgpt.com/docs/build-skills) and [plugin](https://developers.openai.com/plugins/build/plugins) guidance. Separate requirements, optional guidance and local design choices; record dated traceability in the handoff, not bulky skill context. Structural agreement does not establish native discovery or instruction consumption.

When a table helps, use `Document | Finding | Current evidence | Correction or limitation`. A short no-change explanation is enough when nothing is stale.
