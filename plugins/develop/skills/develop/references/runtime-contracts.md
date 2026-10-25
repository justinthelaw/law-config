# Runtime identities and contracts

Use this when planning or verifying a changed developer tool, embedded runtime, build artifact or deployed integration.

## Prove each identity separately

Discover owners and runtime boundaries from selected repositories, launchers, manifests, build recipes and deployment references. Keep developer clients and packaged runtimes separate even when their intended versions match. Reuse assessment target evidence, preserving intentional channels and independent pins.

Record only applicable layers and the evidence that establishes each:

| Layer | Evidence |
| --- | --- |
| Maintained source | Revision, declared pin, lockfile and build/download inputs |
| Installed package | Package metadata and resolved installation location |
| Executed runtime | Resolved executable and safe native identity output |
| Built artifact | Actual binary identity or immutable image/artifact digest |
| Deployment | Selected environment's resolved artifact identity and effective configuration |

A source pin does not prove artifact contents; package metadata does not prove which binary executes; an image tag does not prove a deployed digest. Keep unavailable or unversioned identities explicit. Even version probes can update state through launchers: prefer supported metadata or a verified safe binary, and do not execute arbitrary launchers merely to improve coverage.

## Inspect consumed contracts

Trace relevant baseline-to-target changes through actual consumers. Focus on changed interfaces and supported high-signal failures, rather than reviewing every unrelated component:

- **Build and configuration:** downloads/checksums, supporting locks, packaged configuration, feature negotiation, permissions and preserved user settings.
- **Invocation and data:** arguments, API/schema initialization, required capabilities, event ordering/parsing, completion markers and report/error formats.
- **Lifecycle:** partial results, cancellation, deadlines/timeouts, retries and cleanup ownership. Test unsuccessful and interrupted runs as well as success.
- **Integration:** affected controllers, services, artifact consumers and telemetry contracts. Trace a shared change through every in-scope owner that must rebuild or adapt.

An unchanged interface name does not prove unchanged semantics. Keep supporting dependency edits tied to compatibility, correctness or security evidence.

## Verify the claimed layer

Use owner-defined acceptance checks against the actual affected contract; changing a version assertion alone is insufficient. Keep source checks, offline fixtures, built-artifact checks and deployed behavior distinct. Select runtime/container endpoints through the owning workflow; never fall back to an unrelated default environment.

Implementation authority does not automatically authorize client installation, service lifecycle changes, publication or deployment. Verify only authorized layers and report the remaining gap. Route execution and evidence handling through iterate, without copying its delivery workflow here.
