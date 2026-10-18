# Documentation drift

Use when reviewing or maintaining selected documentation. Review-only produces findings; edits require the user's implementation scope.

- Read owning instructions and explicit exclusions before discovery. Select maintained docs relevant to the task; omit generated, vendored, cached and runtime data unless requested. Repository-specific protected files and writing conventions stay with the repository.
- Compare claims, commands, paths, examples and diagrams with current source, tests, configuration and build/workflow definitions. Recent commits and remembered behavior are investigation leads, not proof that documentation is wrong.
- Preserve owner boundaries: explain integration where it is owned and implementation where it is maintained. Reference one authoritative explanation instead of duplicating it. Use the repository's style; avoid rewriting accurate prose for preference alone.
- Report confirmed drift with the document location, conflicting current evidence and smallest correction. Distinguish a verified no-change result from unavailable evidence or out-of-scope material. Do not claim documentation is current when its relevant source could not be inspected.
- Repair only confirmed in-scope drift. Validate local links, referenced commands and relevant doc/build checks at the touched owner. Do not execute deployment or destructive examples as link verification, or hand-edit generated outputs.

For Codex skill/plugin changes, compare layout, triggers, metadata and references with current official [skill](https://learn.chatgpt.com/docs/build-skills) and [plugin](https://developers.openai.com/plugins/build/plugins) guidance. Separate requirements, optional guidance and local design choices; record dated traceability in the handoff, not bulky skill context. Structural agreement does not establish native discovery or instruction consumption.

When a table helps, use `Document | Finding | Current evidence | Correction or limitation`. A short no-change explanation is enough when nothing is stale.
