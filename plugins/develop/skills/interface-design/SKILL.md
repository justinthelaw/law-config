---
name: interface-design
description: Use before creating or changing user-facing interfaces, interaction flows, visual states or accessibility behavior.
---

# Interface Design

Plan the user task and observable behavior before changing an interface.

Use the shared [planning and review path](../develop/references/contract.md#applicable-planning). Reuse a current accepted design after checking its task, source and constraints. Non-interface work does not invoke this skill. Read the affected surface, existing components/tokens, callers and relevant accessibility or interaction tests.

Add only applicable decisions to the existing brief:

- User task and primary flow; entry/exit, loading, empty, error, success and recovery states.
- Interaction and accessibility contracts: keyboard/focus, labels, feedback and responsive behavior; existing components/tokens to reuse.
- Concrete acceptance checks using the real rendered surface and affected transitions, not a mockup alone.

For a checkout retry button, reuse the existing button, prevent duplicate submission, preserve focus, expose progress/failure and test recovery against the real retry contract. Scale detail to the change; do not invent a design system for a small fix.

When [Engineering Design](../engineering-design/SKILL.md) also applies, share discovery, one decision brief and one review. Return decisions, source/intent revisions, review disposition, unresolved questions and visual/interaction checks to the existing execution owner. Planning does not authorize execution or replace required approvals.
