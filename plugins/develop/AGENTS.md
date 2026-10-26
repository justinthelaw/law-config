# Maintaining develop

## Package and workflow contracts

- Keep ten portable skills and the concrete native Codex context guard: `PreToolUse` and `PostToolUse` in `hooks/hooks.json`, handled by `hooks/context_guard.py`. Bundled, explicitly invoked offline/read-only helpers remain separate. Do not add machine-specific paths, tokens, other executable hooks, an MCP server or a service dependency without a concrete need. Preserve existing runtime pins and Git/security hooks.
- For changes under `skills/`, follow the [skill authoring rules](skills/AGENTS.md). Keep shared defaults and handoffs in `skills/develop/references/contract.md`, with domain detail in owning references. Standalone `kaizen`, `adversarial-loop` and audit-only `upgrade-codex` use their entrypoint's completion policy without repository discovery or coding dependencies.
- Preserve selected repository/session scope, dependency assessment before upgrades, explicit post-plan bypass, fresh non-forked reviews and original model/effort matching. Bundled implementation guidance works without an external framework. Host metadata and optional adapters must not become generic prerequisites. Keep ten entry points; `upgrade` owns dependency upgrades and explicit-only `upgrade-codex` owns Codex compatibility sweeps. Never route generic upgrades or Kaizen requests to `upgrade-codex`.
- Commit signing is nonblocking: prefer an existing noninteractive signer and fall back unsigned, preserving the thread's explicit preference and actual repository/server restrictions. Do not import donor signing gates, change persistent Git configuration or set up keys to satisfy this workflow.
- Change user-facing behavior only within the request; never use internal review as authorization to bypass host controls. Keep conversation packets and task-specific findings outside tracked files.

## Review guidelines

When a passing test could miss the behavior it claims to cover, check whether it catches a plausible defect and still passes after a harmless refactor. Tie findings to the observed results and identify any untested case. The [test-quality controls](tests/evaluations/quality.md) give a bounded example.

## Verify and release

With Python 3.10 or newer, from this plugin directory:

```sh
python scripts/generate_codex_manifest.py
python scripts/validate.py --marketplace-root ../..
python -m unittest discover -s tests
python -m unittest discover -s skills/iterate/scripts -p 'test_*.py'
python -m unittest discover -s skills/deep-clean/tests -p 'test_*.py'
```

Run `git diff --check` and the [contribution checks](../../docs/CONTRIBUTING.md#validation) from the repository root. Commit the source metadata and generated manifest together. For detached installed payloads, omit `--marketplace-root`; run fixture-writing package tests on a disposable copy outside the installed cache.

For Develop changes, follow [behavioral testing](AGENTS.test.md): observe fresh ephemeral agents on affected scenarios before relying on unit-test results. Before publication, also check affected packaged references/helpers from an unrelated working directory and changed artwork at actual display sizes. Inspect actual artifacts; structure checks, text matching and simulated decisions do not prove agent behavior, installation, live publication or deployment. Commit only scoped changes, update the plugin version when releasing, and verify the same Git revision on each installed surface.

## Host metadata and activation

`plugin-source.json` preserves portable source metadata; generated `.codex-plugin/plugin.json` is the sole runtime manifest in this Codex distributable. Do not add root `plugin.json`: Codex gives it precedence and skips bundled hooks for that format. Source metadata is not a discoverable package for other hosts. Asset paths resolve from the package root. The `com.openai` namespace and skill `agents/openai.yaml` files remain host adapters. Do not edit installed caches. The repository catalog is `.agents/plugins/marketplace.json`, published as `law-config`.

Use each host's supported installer and update flow. Checkout, publication, installation, enablement and runtime discovery are separate states. Verify version and skill discovery in a fresh session on every intended device/environment; a local install or downloaded bundle does not establish cloud/remote activation. Inspect CLI warnings as well as JSON: unavailable remote catalogs can leave an empty listing without proving absence.

The [context guard](docs/context-guard.md) additionally requires native hook review/trust and supported local orchestration and execution. Cloud orchestration does not run plugin command hooks, even with local tools. Keep hook-bearing distribution in the existing Git marketplace; it is not eligible for the public plugin directory. Skill portability does not establish hook support on another host. Do not install, enable or trust hooks as a side effect of source validation.

In Codex, installed invocation uses `$develop:develop` or the exact `/skills` entry; an unnamespaced repository-local copy uses `$develop`. Put whitespace before task text; a trailing colon becomes part of the skill name. Catalog metadata does not prove instruction/reference consumption. Follow the [native activation trials](tests/evaluations/native-hosts.md), including positive and unrelated-task controls. Repository-local `.agents/skills` authoring tests loading separately from marketplace installation.

Other hosts use their documented loading and account/workspace distribution flows. Verify filesystem access, native provider tools and fresh independent reviewer capability; do not assume another host's commands or permissions. Report required reviewer matching as unverified when the runtime cannot establish it.

## Artwork and overview rendering

Follow [artwork ownership](assets/AGENTS.md). Preserve approved logo/icon pixels; new skill icons must match the existing Roux palette, proportions and crisp pixel edges, with transparent backgrounds and a clear task prop. Declare both `icon_small` and `icon_large` in each skill's `agents/openai.yaml`; inspect the set together at 48 px and smaller.

Keep the README's linked PNG and [HTML source](docs/develop-overview.html) to one workflow and one skill directory. Trace the example from the user's chat request through the owning skill to the answer or missing evidence. Show each skill's logo and description once; show the shared context guard as one small annotation, never an extra skill or separate section. Keep detailed policy in the owning skill. The former [explorer](docs/develop-route-explorer.html) redirects to this overview. From this plugin directory, use an already installed Playwright package and sandbox-capable browser:

```sh
node docs/render-guide.mjs
```

Chromium is the default. Set `BROWSER_ENGINE=firefox` for an existing Firefox; `BROWSER_EXECUTABLE` may select an existing executable for that engine. Do not install dependencies or disable sandboxing merely to run this optional documentation helper; it is not a plugin runtime requirement.

The renderer captures the 1000-pixel-wide overview at 2× scale, checks the actual PNG at an 860-pixel README display width, and checks the responsive HTML at desktop, mobile and short viewports, skill links and the legacy explorer redirect without network dependencies. Inspect the screenshots. Point `TMPDIR`, `TEMP` and `TMP` at the task's private temporary directory before running the renderer. Each run retains screenshots and `browser-qa.json`, including partial results, in a new `develop-browser-qa-*` folder there. The renderer prints absolute evidence paths and updates `docs/develop-overview.png` after its checks pass.

## Source and installation changes

Source consolidation, installation, retirement, commits and publication require their own applicable authorization. Before replacing an installed skill, inventory its live callers, helpers, links and repository-owned behavior. Verify replacement source, version and installation state; disclose gaps. Preserve repository-specific operations under their owner; do not copy machine-specific scripts or native transcript parsers into generic workflows.

Move retired sources and exact matching links to recoverable Trash where supported; preserve Git history, unrelated skills and work. Repair live callers and remove only obsolete grants/packaging entries.
