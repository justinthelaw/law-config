---
name: develop
description: Implement and verify repository changes through their callers.
---

# Develop

Trace the requested behavior to its smallest owner. Reproduce bugs through a real caller. When extending a condition or replacing a representation, preserve an input the old path accepted that the new one might lose.

Make the change and run the focused regression with the project's configuration. Exercise changed entry points as users invoke them. For writes and cleanup, check the resulting state. Complete required checks and report what ran.

Handle a local, verifiable change directly. Use [design or review](references/planning-and-review.md) for a requested review, repository requirement, or consequential uncertainty the checks cannot settle. [Iterate](../iterate/SKILL.md) covers delivery.
