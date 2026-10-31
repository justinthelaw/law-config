# Develop

[Install](INSTALL.md), then use `$develop:develop` with a repository task. Develop traces the caller, makes the change and verifies the behavior using the project's own commands. Design and review are available when a decision or risk warrants them.

| Skill | Use |
| --- | --- |
| [Develop](skills/develop/SKILL.md) | Implement and verify a change |
| [Iterate](skills/iterate/SKILL.md) | Diagnose failures, publish and monitor CI |
| [Upgrade](skills/upgrade/SKILL.md) | Assess dependencies or implement upgrades |
| [Upgrade Codex](skills/upgrade-codex/SKILL.md) | Audit or update a Codex setup |
| [Kaizen](skills/kaizen/SKILL.md) | Improve workflows from selected sessions |
| [Clean](skills/clean/SKILL.md) | Inspect this thread's disposable resources |
| [Deep Clean](skills/deep-clean/SKILL.md) | Inventory selected filesystem roots |

Select each of the five maintenance skills by name, for example `$develop:upgrade-codex`. The former Engineering Design, Interface Design and Adversarial Loop entries are now [on-demand guidance](skills/develop/references/planning-and-review.md).

Local Codex sessions can use the [context guard](docs/context-guard.md) to bound large reads and preserve oversized results after explicit authorization. The separate [staged-file checker](skills/iterate/references/staged-file-size.md) inspects Git's index on request.

[Maintainer guide](AGENTS.md) · [Apache-2.0 license](LICENSE)
