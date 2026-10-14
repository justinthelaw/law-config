# Dependency assessment

Use this before upgrading or consolidating dependency changes, and as the full workflow for a review-only request.

## Establish the comparison

Resolve selected checkouts and their maintained owners. Read applicable repository instructions, manifests, lockfiles, runtime/toolchain pins, build recipes and CI. Discover the actual package manager and owner-defined validation commands; do not substitute familiar tooling. Resolve aliases without reviewing the same source twice.

Record the current revision, requested comparison baseline and exact candidate. A baseline may be a release, commit or existing pin; an unknown baseline stays unknown. Separate existing failures and unavailable prerequisites from regressions. Read-only review can inspect existing evidence and use verified non-mutating queries; do not run installers or resolvers that rewrite locks or prepare environments. Report missing evidence instead.

Within selected scope, include runtime, development/test, optional/peer, build, package-manager, automation, container and transitive constraints. Review additions, removals, downgrades and majors as well as version increases. Compare native resolver output or lockfile graphs for transitive fan-out and interacting constraints; direct manifests alone do not establish the effective dependency set. Flag relevant security, provenance, license, runtime/platform and support changes with evidence, not version-number assumptions.

## Choose and evaluate targets

Verify releases, support dates, migration guides and security/deprecation notices against official upstream or registry sources. Freeze exact versions/commits, channels, evidence URLs and check dates for the assessment; compare each baseline over its relevant release interval.

Preserve explicit targets and deliberate prerelease or long-term-support channels. Without a selected channel, prefer supported stable releases or an appropriate supported long-term-support line. Do not silently downgrade a deliberate prerelease to stable. Mark unavailable targets or unverifiable compatibility as `Blocked/unverified` rather than substituting another target.

Group compatible dependency families and identify required intermediate migrations. Evaluate affected call sites, peers, runtime floors and platform/CI coverage. Avoid overriding transitive leaves without proving constraints remain compatible. A supporting dependency is a candidate, not an automatic bump.

For each material risk, record evidence, applicability, smallest sufficient change and acceptance check. Distinguish required compatibility work, optional improvement and unresolved hypothesis. Inventory, a matching pin or a passing narrow check does not establish full compatibility; retain justified unchanged decisions and coverage gaps.

## Consolidating dependency PRs

When requested, capture each in-scope source PR's URL, head/base revisions, intent, dependencies and review state, including draft or human-authored work. Keep unrelated feature work outside scope. Plan integration in dependency order, without duplicate changes or lost attribution; map each intent to incorporation, unchanged decision or blocker.

Implementation and publication use iterate. Close source PRs only with explicit closure authority or a request for one remaining consolidated PR, after iterate's incorporation and readiness checks. Preserve incomplete sources and branches; report blocked repositories while continuing independent authorized work.
