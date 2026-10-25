---
name: engineering-design
description: Use before engineering changes or consequential architecture, API, data, configuration, runtime or migration decisions, including direct implementation and upgrade requests.
---

# Engineering Design

Make the smallest decision brief that lets the existing execution owner implement and verify the right change.

Use the shared [planning and review path](../develop/references/contract.md#applicable-planning). Revalidate an accepted plan before reusing it; a new skill handoff alone does not restart planning. Read only affected owners, consumers, contracts and relevant tests, widening for hidden consumers or conflicting evidence.

The brief covers what matters for this change:

- Outcome, constraints and acceptance criteria; existing owner and affected consumers.
- Meaningful alternatives and the selected rationale; interfaces, data/state boundaries and invariants that must survive.
- Relevant compatibility, failure, migration and rollback risks; concrete checks that will establish the claimed behavior.

Prefer existing components, standard/native capabilities and one owner per rule. Trace shared changes through real callers; remove duplication without inventing a framework. A pagination fix can be one paragraph naming the shared paginator, API/CLI consumers, unchanged contract and boundary regression; it needs no architecture template.

For interface work, combine [Interface Design](../interface-design/SKILL.md) decisions into this same brief and review. Return the accepted, waived or delegated-review disposition, source/intent revisions, open decisions and verification to Iterate or the current execution owner. Do not implement, publish or create a second coordinator merely because planning completed.
