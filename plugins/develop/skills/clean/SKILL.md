---
name: clean
description: Inspect disk and RAM, clean disposable files, and investigate orphaned or zombie processes on Windows, Linux or macOS.
---

# Clean

Inspect first, remove verified disposable targets, and measure the result.

## Start

Read [the shared contract](../develop/references/contract.md) and [platform guidance](references/platforms.md). Reuse the invocation; its coordinator reviews proposed targets before removal and evidence before completion.

Identify the actual OS, shell, writable roots and tools. A local, remote or hosted runtime does not grant access to another device. Respect the requested scope; inspection-only means no deletion or process stopping.

In upgrade **prepare mode**, remove only verified unused, rebuildable caches/build output within authorized workspace/scratch boundaries. Preserve checkouts, current directory, installed toolchains and active services; a measured no-op is valid.

## Workflow

1. **Measure.** Record current directory, available/used memory, free disk per affected filesystem and candidate sizes. Use comparable before/after methods; distinguish logical/allocated bytes and label unavailable metrics.
2. **Inspect.** Enumerate one authorized directory at a time with `rg --files --hidden --no-ignore -g '!.git' -- <scoped-directory>` or the host equivalent. Include hidden and ignored artifacts such as `.next`, `.venv`, `node_modules` and caches; exclude protected Git metadata. Check ownership, active handles/process use, reconstruction inputs, symlinks/reparse points and mounted descendants, including same-device bind mounts.
3. **Classify.** Mark exact paths removable, protected or blocked with evidence. Protect source, lockfiles, credentials, persistent data, managed runtimes/mounts, active services/previews, dirty/untracked work, worktrees, stashes, unpublished commits and active incident logs. Inspect repository state and recoverability before considering an old checkout; age proves nothing. Dependency trees require retained reconstruction inputs and no active use. Prefer package-manager dry-run/cleanup support for caches and orphan packages.
4. **Review.** Send the concrete inventory to the intent checkpoint. No safe candidates means a no-op, not broader scope.
5. **Remove.** Immediately re-resolve every exact absolute target inside its authorized parent; recheck ownership, use and traversal boundaries. Reject roots, home directories, entire workspace/scratch roots, unresolved globs and ambiguous paths. Do not traverse links, junctions or mounted descendants; preserve targets whose traversal cannot be proven safe. Use one native shell end-to-end, PowerShell `-LiteralPath` on Windows; never interpolate enumerated paths into another shell. POSIX `-xdev` alone does not exclude same-device mounts.
6. **Verify.** Check exit statuses and actual removals; preserve partial-failure evidence. Repeat measurements, protected-boundary and service checks. Run package consistency checks if databases changed. Submit results to the evidence checkpoint.

Recoverable moves must have verified destinations and do not count as reclaimed disk space. If removal of the current directory was explicitly requested, leave it, revalidate and handle it last. Never unmount harness-managed contents.

## Processes

Inspect PID, parent, owner, command, working directory and service ancestry. PPID 1 or high RAM use does not establish disposability. Preserve supervisors, agent/transfer/preview services and system processes. Zombies need parent reaping, not killing or supervisor restarts.

Stop only verified disposable live tasks within explicit scope. Prefer graceful termination; forced termination requires applicable explicit authorization. Recheck process identity and state because inventories race.

## Report

Summarize removed, protected and blocked targets, then return:

| Metric | Result |
| --- | --- |
| RAM reclaimed, estimate | Before-used minus after-used; retain negative values |
| Disk reclaimed, estimate | Verified deletions' allocated bytes; deduplicate overlaps/hard links, or mark unavailable |
| Filesystem free-space change | After-available minus before-available per same filesystem |

Give bytes and readable units. Exclude failed deletions, proposed sizes and quarantine moves; label unmeasurable partial deletion unknown. Explain discrepancies from concurrent activity, open deleted files or shared storage. Stop when scoped cleanup is verified.
