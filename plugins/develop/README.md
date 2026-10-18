# Develop

Eight portable skills for scoped development, review and maintenance. Invoke `develop` once with the outcome you want, or call the owning skill directly. It carries authorized work through the requested checks and handoff, preserving narrow review or diagnosis requests. See [installation](INSTALL.md).

| Skill | Owns |
| --- | --- |
| [develop](skills/develop/SKILL.md) | Routes the user's outcome and keeps one coordinator across handoffs. |
| [iterate](skills/iterate/SKILL.md) | Implements, reviews, diagnoses incidents, publishes, monitors CI/reviews and prepares deployment handoffs. |
| [upgrade](skills/upgrade/SKILL.md) | Assesses dependencies/runtimes and plans migrations; uses Iterate for authorized implementation. |
| [adversarial-loop](skills/adversarial-loop/SKILL.md) | Independently reviews artifacts and evidence using optional user rubrics/preferences and bounded fresh review rounds. |
| [clean](skills/clean/SKILL.md) | Removes verified disposable artifacts/processes attributable to the current thread. |
| [deep-clean](skills/deep-clean/SKILL.md) | Inspects or cleans explicitly widened filesystem scope using Clean's protections. |
| [kaizen](skills/kaizen/SKILL.md) | Learns from selected sessions and proposes workflow improvements; uses Iterate when implementation is requested. |
| [upgrade-codex](skills/upgrade-codex/SKILL.md) | Audits selected Codex configuration; explicit invocation only, with requested implementation handed to Iterate. |

![Develop workflow: eight skill owners, explicit-only paths, and the shared review and delivery loop.](docs/develop-overview.png)

The Roux-themed [one-page overview source](docs/develop-overview.html) explains the skill owners, explicit-only paths, shared review and delivery loop without interaction. The [interactive explorer](docs/develop-route-explorer.html) is an optional supplement; it is not needed to understand the plugin.

Debug and deployment/operations handoffs are **Iterate modes**, not additional entrypoints. Review rubrics extend the existing adversarial review engine. Repository workflows share intent/evidence checkpoints; standalone analysis follows its owner's completion policy. Handoffs preserve scope, authority and review budgets. CI-only requests do not start Codex reviews; preparation or publication does not authorize deployment or merging.

To render the overview PNG and check the interactive guide, use an already installed Playwright package and sandbox-capable browser: `node docs/render-guide.mjs`. Use the default Chromium engine, or set `BROWSER_ENGINE=firefox` for an existing Firefox. Set `BROWSER_EXECUTABLE` only to select an existing executable for that engine. The renderer uses a 1600 × 1190 overview at 2× scale and checks desktop/mobile interactions without network dependencies. It is an optional documentation helper, not a plugin runtime requirement. Do not disable browser sandboxing to work around a host restriction.

Each run preserves its screenshots and `browser-qa.json` in a unique `develop-browser-qa-*` directory under the system temporary directory, outside the plugin package by default. This includes failed checks and partial results after browser errors. The printed report path and screenshot paths are absolute. A passing run also updates `docs/develop-overview.png`; retries leave earlier QA evidence intact. Copy evidence elsewhere if it must outlast system temporary-file cleanup.
