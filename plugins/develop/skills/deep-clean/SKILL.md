---
name: deep-clean
description: Use when explicitly selected to inventory or clean a user-selected filesystem scope beyond this thread.
---

# Deep Clean

Start only when the user names or selects Deep Clean. Record the host, exact roots, exclusions and whether inspection or cleanup was requested. Resolve missing scope or action authority before dependent work. Inspection permits metadata reads only.

1. Read the [shared protections](../clean/references/protections.md), [platform guidance](../clean/references/platforms.md) and [inventory guide](references/inventory.md). Use an equivalent native inventory or the bundled Python helper. Verify hidden-entry coverage, identity, links, mounts and exclusions. Keep the report private. Apply requested limits only and disclose incomplete coverage.
2. For broad scope, identify selected local volumes and aliases. Inspect eligible volumes separately. Preserve protected roots, virtual, network, backup and cloud volumes. Record inaccessible entries. Do not elevate, hydrate remote data, cross mounted descendants or add overlapping totals.
3. Classify exact candidates as eligible, protected or blocked using ownership, active handles and process ancestry, reconstruction inputs and sharing. Timestamps and an absence of handles are insufficient. Distinguish measured size from verified reclaimability.
4. For authorized cleanup, follow the same [shared protections](../clean/references/protections.md) and platform procedure within this invocation. Revalidate each exact target and traversal immediately before acting. Verify system Trash or Recycle Bin destinations. If Trash is unavailable, ask before deletion. Retain uncertain targets and preserve application state, active processes and databases.

Report roots, OS, scan time, exclusions, volume gaps and logical versus allocated sizes in decimal MB/GB. Deduplicate aliases and hardlinks, and identify storage sharing or snapshots that affect estimates. List candidate evidence, disposition and the next necessary check. For executed cleanup, report RAM change, verified reclaimed disk and filesystem free-space change. Trash moves reclaim zero bytes. An audit ends with **No cleanup actions performed**.
