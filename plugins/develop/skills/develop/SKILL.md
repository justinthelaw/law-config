---
name: develop
description: Implement and verify repository changes through their callers.
---

# Develop

Reproduce bugs through a real caller. Change the smallest owner and retain existing conversions and fallbacks. Check alternate definitions of dependencies you introduce. Verify the result or written state for the new case and an old input the edit could break.

Start with the cheapest check that executes the changed code. Reuse the project's toolchain, build tree and results. If setup fails, try the documented entry point and a focused executable equivalent. Run required checks and report material gaps.

For long builds and tests, [wait on the running command](references/long-checks.md). Do independent work while it runs. Otherwise let one tool call wait for its exit and diagnostics.

Handle verifiable changes directly. Use [design or review](references/planning-and-review.md) when requested, required, or needed to settle consequential uncertainty. [Iterate](../iterate/SKILL.md) covers delivery.
