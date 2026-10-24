# Session evidence

## Reconstruct a causal episode

Read preceding context through the initiating request, then follow relevant actions,
results, user corrections and the observed outcome. Preserve chronological order
and match calls to results using native identifiers when available. Missing context
limits attribution; a confident completion message, silent tool or finished turn
does not establish success.

Distinguish observed invocation from a catalog entry, quoted prompt, copied tool
output or proposed command. Attribute an outcome to a skill only when evidence
shows it governed the relevant action. Otherwise report the observed behavior
without assigning an unsupported cause. Consider external failures and explicit
user steering before proposing instruction changes.

Track episodes by source/session identity and event range. Forked, copied,
compressed or summarized representations of the same events count once; separate
new actions from inherited context. Unsupported linked or reverted histories are
coverage gaps; do not reconstruct them by guessing or following out-of-scope
pointers.

## Bound retrieval and claims

Apply the budget across all selected sources, including malformed, duplicate and
rejected reads. For a sampled request, stop when sufficient complete evidence supports the findings. For "every session," follow all accessible pages in each selected source. Count distinct sessions separately from deduplicated episodes. Record unfinished pages, inaccessible sources and a private resume point when a limit is reached.
Retain minimal private working evidence; reviewers receive sanitized causal
summaries and permitted source locators.

Report selected/readable sources, reviewed relevant episodes, observed outcomes,
omissions and reached limits separately. State sampling or retrieval order bias
and inaccessible or still-in-progress episodes. Partial coverage cannot establish
absence of a problem across the selection. A single supported defect can justify
a narrow correction without establishing recurrence.

## Make the recommendation testable

Use this compact shape where useful:

| Evidence and confidence | Current owner | Smallest useful change | Verification |
| --- | --- | --- | --- |
| Sanitized request/action/result with source locator and independent count | Existing skill, instructions, rule or capability | Concrete proposed correction and expected effect | Realistic scenario, observable outcome and relevant scope boundary |

Distinguish a missing instruction from a stale version, conflict or execution
error. Record verified sources and capability gaps for new skill/plugin
recommendations; label proposed skills as not yet implemented. For hooks or rules,
state trigger, scope, failure behavior and permissions. Verify with a scenario
that can expose the original failure, rather than matching the new wording.
Report insufficient evidence rather than manufacturing a recommendation.
