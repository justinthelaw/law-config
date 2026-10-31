---
name: clean
description: Use when explicitly selected to inspect or clean verified disposable resources from this thread and its delegated work.
---

# Clean

Use this skill only when the user names or selects it. Limit discovery to resources attributable to the current thread and its workers, wherever located. A wider inspection request does not invoke Deep Clean. Handle the authorized request within its stated scope and identify any part beyond this skill.

Read the [shared protections](references/protections.md), the [host guidance](references/platforms.md) and the applicable [review gates](../develop/references/planning-and-review.md#review-gates). Use the actual host and writable roots. An audit permits inspection only.

## Workflow

1. Record the working directory, used memory, free disk by filesystem and candidate sizes. Keep raw units and distinguish logical from allocated bytes.
2. Attribute each exact path or PID to observed thread activity. Check ownership, reconstruction inputs, repository state, live handles, service ancestry, links and mounted descendants. Include hidden disposable artifacts within scope. Preserve uncertain candidates. Age, location, size and PPID alone establish neither ownership nor disposability. Apply no default age, depth or size cutoff.
3. Classify candidates as eligible, protected or blocked. Review a consequential inventory before mutation. For explicitly authorized upgrade preparation, limit cleanup to unused, rebuildable output in the selected workspace or scratch area. Preserve checkouts, toolchains and services.
4. Re-resolve each target under its authorized parent immediately before acting. Reject aggregate roots, globs, ambiguous identities and unsafe traversal, including same-device bind mounts and reparse points. Use literal paths in one native shell. Leave an explicitly selected current directory first and handle it last. Preserve managed mounts.
5. Move eligible files to the host's system Trash or Recycle Bin and verify the destination. If unavailable, ask before deletion. Retain targets pending that decision. Never empty Trash. Prefer a package manager's dry run for its own caches.
6. For a live process, recheck PID, owner, command, working directory, parent and service ownership. Stop only a verified disposable task within explicit scope. Prefer graceful termination. Force requires explicit authorization. A zombie needs parent reaping.
7. Verify each outcome, protected boundary and affected service. Repeat the original measurements. Check package consistency after database changes and retain partial failures. Complete the applicable evidence review.

Report removed, protected and blocked targets. Give estimated RAM change as before-used minus after-used, verified deleted allocated bytes with hardlinks deduplicated, and free-space change per filesystem. Show bytes and readable units. Trash moves reclaim zero bytes. Retain negative and unknown results and explain material differences.
