# Dependency assessment

## Baseline and scope

- Resolve selected checkouts/aliases once and maintained owners. Read owner instructions, manifests, locks, runtime/toolchain pins, build recipes and CI; use their package manager and validation commands.
- Record revision, comparison baseline and exact candidate. Unknown stays unknown. Separate pre-existing failures/unavailable prerequisites from regressions. Read-only assessment uses existing evidence or verified non-mutating queries; no installers, environment preparation or lock-writing resolvers.
- Cover runtime, development/test, optional/peer, build, package-manager, automation, container and transitive constraints; include additions, removals, downgrades and majors. Compare native resolver/lock graphs for fan-out and interacting constraints. Direct manifests do not establish the effective set.
- Evidence relevant security, provenance, license, platform/runtime and support changes; version numbers alone prove none.

## Targets and compatibility

- Verify official upstream/registry releases, support dates, migrations and security/deprecation notices over the baseline's release interval. Freeze exact versions/commits, channels, evidence URLs and dates.
- Preserve explicit targets and deliberate prerelease/LTS channels. Otherwise prefer supported stable or suitable LTS. Unavailable targets or unverifiable compatibility are `Blocked/unverified`; do not silently substitute.
- Use the owning manager for authorized changes. Verify supported runtimes before removing dependencies (e.g. `tomllib` requires Python 3.11; retain a compatible reader for 3.10). Exercise changed framework syntax with representative inputs.
- Group compatible families, intermediate migrations, call sites, peers, runtime floors and platform/CI checks. Prove constraints before overriding transitive leaves; supporting dependencies are candidates, not automatic bumps.
- For material risks record evidence, applicability, smallest change and acceptance check. Separate required work, optional improvements and hypotheses. Inventory, matching pins or narrow passing checks do not prove full compatibility; retain justified unchanged decisions and gaps.

## Consolidating PRs

Capture requested source PR URLs, head/base revisions, intent, dependencies and review state, including draft/human work. Exclude unrelated features. Integrate in dependency order without duplication or lost attribution; map every intent to incorporation, unchanged decision or blocker.

Use Iterate for implementation/publication. Close sources only with explicit closure authority or a request for one remaining consolidated PR, after Iterate's incorporation/readiness checks. Preserve incomplete sources/branches; report blockers while continuing independent authorized work.
