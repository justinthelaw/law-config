# Develop

Eight portable skills for scoped development, review and maintenance. Invoke `develop` once with the outcome you want, or call the owning skill directly. It carries authorized work through the requested checks and handoff, preserving narrow review or diagnosis requests. See [installation](INSTALL.md).

| Skill | Owns |
| --- | --- |
| [develop](skills/develop/SKILL.md) | Routes the user's outcome and keeps one coordinator across handoffs. |
| [iterate](skills/iterate/SKILL.md) | Implements, refactors, reviews, diagnoses incidents, publishes, monitors CI/reviews and prepares deployment handoffs. |
| [upgrade](skills/upgrade/SKILL.md) | Assesses dependencies/runtimes and plans migrations; uses Iterate for authorized implementation. |
| [adversarial-loop](skills/adversarial-loop/SKILL.md) | Independently reviews artifacts and evidence using optional user rubrics/preferences and bounded fresh review rounds. |
| [clean](skills/clean/SKILL.md) | Removes verified disposable artifacts/processes attributable to the current thread. |
| [deep-clean](skills/deep-clean/SKILL.md) | Inspects or cleans explicitly widened filesystem scope using Clean's protections. |
| [kaizen](skills/kaizen/SKILL.md) | Learns from selected sessions and proposes workflow improvements; uses Iterate when implementation is requested. |
| [upgrade-codex](skills/upgrade-codex/SKILL.md) | Audits selected Codex configuration; explicit invocation only, with requested implementation handed to Iterate. |

![Develop skill calls: conditional handoffs into Iterate, shared adversarial review, resource cleanup and a separate delivery phase loop.](docs/develop-overview.png)

The Roux-themed [one-page overview source](docs/develop-overview.html) shows skill calls and their conditions separately from delivery phase order. It is readable without interaction. The [interactive explorer](docs/develop-route-explorer.html) is an optional supplement.

## Who calls whom

These are conditional calls or workflow reuse, not a sequence every task runs.
Composed work returns through the [shared handoff](skills/develop/references/contract.md#handoffs);
direct standalone calls keep their owner's completion policy.

| Caller | Calls / reuses | Condition and return |
| --- | --- | --- |
| Develop | Iterate, Upgrade, Clean, Kaizen or adversarial-loop | Select the owner for the requested outcome. Deep-clean and upgrade-codex require their explicit scope/invocation; a generic upgrade never selects upgrade-codex. |
| Iterate | adversarial-loop; optionally Clean | The coordinator runs intent/evidence checkpoints, reusing current nested gates. Call Clean only for requested cleanup or an identified authorized resource need; return measurements and protected/blocked targets. |
| Upgrade | adversarial-loop; Iterate; optionally Clean | Review assessment and final evidence through shared gates. Call Iterate only for authorized implementation/delivery, then combine its result with the dependency ledger. Clean requires a demonstrated authorized resource need, not a mandatory preparation phase. |
| upgrade-codex | Iterate; conditionally adversarial-loop | A bare explicit invocation audits only. Audit review is opt-in; requested implementation uses Iterate and the shared gates. Return implementation evidence to the Codex coverage report. |
| Kaizen | adversarial-loop; conditionally Iterate | Review selected-session recommendations. Call Iterate only for specifically authorized improvements; return tested outcomes without expanding session/repository scope. |
| Clean | adversarial-loop; conditionally Deep-clean | Review proposed targets and outcome. Explicitly widened inspection/cleanup may hand off to Deep-clean with the same scope and authority. |
| Deep-clean | Clean's execution/protection workflow and shared review gates | Reuse the existing Clean workflow for eligible targets; do not route recursively back through Clean's start. Return coverage, measurements and dispositions to the caller. |
| adversarial-loop | Fresh independent reviewers | Reviewers return findings to the calling coordinator. They never invoke nested reviews or acquire implementation authority. |

Iterate owns repository delivery, including **Refactor**, Debug and deployment/operations
handoff modes. [Refactor](skills/iterate/references/refactoring.md) can use a focused
worker with bounded files, an objective, preserved behavior/performance and
acceptance checks. The worker returns its diff and evidence; the coordinator
integrates, runs applicable full tests and reviews the result. Its goal is
maintainability within requested or justified scope; it is neither a ninth skill
nor automatic repository-wide polishing. Clean continues to mean disposable
resource cleanup.

Review rubrics extend the existing adversarial engine. Handoffs preserve scope,
authority and review budgets; nested work does not create another delivery owner,
review engine or watcher. CI-only requests do not start Codex reviews; preparation
or publication does not authorize deployment or merging.

To render the overview PNG and check the interactive guide, use an already installed Playwright package and sandbox-capable browser: `node docs/render-guide.mjs`. Use the default Chromium engine, or set `BROWSER_ENGINE=firefox` for an existing Firefox. Set `BROWSER_EXECUTABLE` only to select an existing executable for that engine. The renderer captures the 1000-pixel-wide static overview at 2× scale, checks its actual PNG at an 860-pixel README display width, and checks desktop/mobile explorer interactions without network dependencies. It is an optional documentation helper, not a plugin runtime requirement. Do not disable browser sandboxing to work around a host restriction.

Each run preserves its screenshots and `browser-qa.json` in a unique `develop-browser-qa-*` directory under the system temporary directory, outside the plugin package by default. This includes failed checks and partial results after browser errors. The printed report path and screenshot paths are absolute. A passing run also updates `docs/develop-overview.png`; retries leave earlier QA evidence intact. Copy evidence elsewhere if it must outlast system temporary-file cleanup.
