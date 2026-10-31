---
name: develop
description: Implement and verify repository changes through their callers.
---

# Develop

Reproduce bugs through a real caller. Change the smallest owner and retain existing conversions and fallbacks. Check alternate definitions of dependencies you introduce. Verify the result or written state for the new case and an old input the edit could break.

Before a cold framework build, prove the bug with a tiny supported public caller on current source where feasible. For compiled callers, run `python3 <skill-dir>/scripts/probe.py --help` to compile and run a fresh executable with the project toolchain and task scratch directory. Update code and tests, then run the required final target once in the supported configuration and report material coverage gaps.

Handle verifiable changes directly. Use [design or review](references/planning-and-review.md) when requested, required, or needed to settle consequential uncertainty. [Iterate](../iterate/SKILL.md) covers delivery.
