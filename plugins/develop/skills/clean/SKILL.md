---
name: clean
description: Explicit cleanup or audit of resources attributable to this thread.
---

# Clean

Trace exact paths and processes to this thread or its workers. Inspect metadata only. Record baseline memory, free space and candidate sizes using [platform operations](references/platforms.md). Check [protections](references/protections.md) before traversing candidates. Classify eligible, protected and uncertain targets from ownership, current use and rebuildability.

An audit stops at findings. For authorized cleanup, recheck identity, links, mounts, handles and service ancestry immediately before action. Leave a selected working directory before moving it last. Move files to verified system Trash. If unavailable, retain them and ask before deletion. Stop only attributable in-scope processes, gracefully unless force is authorized.

Report actions, retained targets and partial failures. Measure memory and per-filesystem free-space changes separately from deduplicated allocated bytes reclaimed. Trash moves reclaim zero bytes.
