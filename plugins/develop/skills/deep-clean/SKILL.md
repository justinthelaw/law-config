---
name: deep-clean
description: Inspect or clean an explicitly expanded filesystem scope beyond this thread including a user selected entire machine root.
---

# Deep clean

Use only after the user explicitly requests wider inspection or cleanup, by naming deep-clean or describing expanded scope such as "index and clean my entire machine starting at `/`". A reference from clean is not authorization. Resolve missing root or action authority before dependent work; inspection-only requests authorize no removal or process stopping.

Read [the shared contract](../develop/references/contract.md), [shared protections](../clean/references/protections.md), [platform guidance](../clean/references/platforms.md), and [inventory guidance](references/inventory.md). Reuse one invocation and the clean execution/review gates. Repository discovery is unnecessary.

1. Record the explicit root, host, exclusions, audit/cleanup boundary and accessible filesystems. Broad inspection can include foreign-owned metadata; removal eligibility requires separate ownership and authority checks. Do not elevate or hydrate remote files.
2. Run the bundled [metadata inventory](scripts/inventory.py) using installed Python 3.10+ and a new private report outside the scanned root when possible. Pass protected subtrees through `--exclude`; never scan a protected root. No default depth, node or time cutoff applies. Monitor progress, inspect aggregates before selected records, and report deliberate exclusions and incomplete coverage. Never dump the inventory into chat.
3. For `/` or another broad root, enumerate local mounted volumes and OS aliases. The helper does not cross mount boundaries. Inventory each explicitly covered local volume separately when safely accessible, preserve virtual/network/cloud/backup exclusions, deduplicate aliases and hardlinks across reports, and never add overlapping totals. Record every skipped volume and permission gap. Starting at `/` does not authorize deleting `/` or other aggregate roots.
4. Assess meaningful candidates using ownership, open read/write handles, live process activity and ancestry, creation/modification/access timestamps with their platform limitations, retained reconstruction inputs, shared dependencies and uncertainty. Use native read-only tools; unavailable checks remain unknown. Timestamps and an absence of handles never establish safety.
5. Give each proposed action a risk score with its scale, confidence and evidence explained; no prescribed numeric scale is required. Protected resources are excluded regardless of score. Keep measured size separate from reclaimability, which remains unknown until verified.
6. For authorized cleanup, use [clean's workflow](../clean/SKILL.md#workflow), process rules and verification on exact eligible targets. Complete verified candidates without repeated per-item approval; retain uncertain ones. Use macOS system Trash and report moves as zero reclaimed bytes. Do not migrate state, retire tasks or repair databases.

Report root, OS, scan time, coverage, volume gaps and logical versus allocated sizes. Use decimal MB/GB and label filesystem free space separately. Hardlink deduplication does not resolve APFS clones, compression, snapshots or shared extents. Provide one concise candidate table with path/group, measured size, risk score and evidence, action/protected/blocked disposition and next verification. Include clean's RAM/disk/free-space measurements for executed cleanup. Audit reports end with **No cleanup actions performed**.
