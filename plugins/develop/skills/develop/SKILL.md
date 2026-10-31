---
name: develop
description: Implement and verify repository changes through their callers.
---

# Develop

Reproduce bugs through a real caller. Change the smallest owner and retain existing conversions and fallbacks. Check alternate definitions of dependencies you introduce. Verify the result or written state for the new case and an old input the edit could break.

For a cold build, establish the baseline with the cheapest real caller. Reuse the project's toolchain, build tree and results. Keep one owner per build tree and source state. Diagnose progress before starting another. Run required final checks in the supported configuration and report gaps.

For long builds and tests, start once and wait for completion. In code mode, use `// @exec: {"yield_time_ms":300000}` and loop `tools.write_stdin({session_id,chars:"",yield_time_ms:300000})` inside the cell until exit. If the cell yields, resume it with `functions.wait` and `{"cell_id":"<id>","yield_time_ms":300000}`. Long waits return on completion. Preserve exit status and failure output. Use a shorter first yield if independent work is ready.

Handle verifiable changes directly. Use [design or review](references/planning-and-review.md) when requested, required, or needed to settle consequential uncertainty. [Iterate](../iterate/SKILL.md) covers delivery.
