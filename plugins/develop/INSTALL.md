# Install Develop

Source: [justinthelaw/law-config, plugins/develop](https://github.com/justinthelaw/law-config/tree/main/plugins/develop). The package contains eight skills: `develop`, `iterate`, `upgrade`, `upgrade-codex`, `clean`, `deep-clean`, `adversarial-loop` and `kaizen`. It needs no external workflow plugin and uses the [Apache-2.0 license](LICENSE).

## Choose a host

Use the host's supported marketplace/package installer. Repository checkout, publication, installation, enablement and runtime discovery are separate states. Verify the selected version and skill discovery in a fresh session on each intended device or environment. Local installation alone does not install a cloud or remote copy.

The root `plugin.json` is portable metadata. Generated `.codex-plugin/plugin.json`, the `com.openai` metadata namespace and skill `agents/openai.yaml` files are compatibility adapters, not product-specific workflow requirements. Both manifests resolve assets from the package root. Keep these technical names accurate; do not edit installed caches.

For Codex clients supporting the native plugin CLI:

```sh
codex plugin marketplace add justinthelaw/law-config --ref main
codex plugin add develop@law-config
codex plugin list --marketplace law-config --json
```

The repository catalog is `.agents/plugins/marketplace.json`, published as the `law-config` marketplace. Refresh the configured Git source with `codex plugin marketplace upgrade law-config`, then use the client's supported update/install flow. Restart or refresh the host and begin a new chat to verify its active catalog. A downloaded bundle alone does not prove activation.

Other hosts use their documented skill/plugin loading and account/workspace distribution flows. Verify filesystem access, native provider tools and fresh independent reviewer capability there; do not assume another host's command names or permissions. Required reviewer matching that the runtime cannot establish must be reported as unverified.

## Use

- `develop iterate: fix this checkout's failing build; preserve its public API.`
- `develop iterate: review these documents against current code; report only.`
- `develop iterate: publish these prepared changes; signing is optional.`
- `develop upgrade: assess and upgrade dependencies in this repository.`
- `develop upgrade: review this dependency PR only.`
- `$upgrade-codex: audit this project's Codex setup against the installed version; report only.`
- `$upgrade-codex: check these configs, instructions, skills and plugins against Codex <version>.`
- `develop clean: inspect disk and memory usage; do not delete anything.`
- `develop kaizen: analyze these two selected sessions and recommend workflow improvements; make no changes.`
- `adversarial-loop: fact-check this draft; report findings only.`

Dependency assessment is upgrade's first stage. A user may explicitly bypass the separate assessment after planning; factual prerequisites, validation and protections still apply. Scope stays with selected repositories and sessions; no author-account fleet or machine-wide history is implied. Repository-specific conventions and user preferences remain with their owners.

`upgrade-codex` runs only when explicitly invoked. It checks every Codex primitive
in the selected scope against the installed or specified version, reports gaps
in coverage, and separates required fixes from optional improvements. It starts
with an audit; applying changes requires a request. Client installation is a
separate action. See the [skill](skills/upgrade-codex/SKILL.md).

Signing is nonblocking: use an existing noninteractive signer when available, otherwise fall back unsigned, preserving any thread preference. Do not change persistent Git configuration or set up keys to satisfy this workflow. Actual repository/server restrictions still apply.

The bundled watcher supports GitHub CI. Its optional vendor-specific review adapter is selected explicitly; other required reviews use native evidence. A successful CI-only watcher does not certify all PR approvals. See [monitoring](skills/iterate/references/github-monitoring.md).

## Verify and release

With Python 3.10 or newer, from the repository root:

```sh
python plugins/develop/scripts/generate_codex_manifest.py
python plugins/develop/scripts/validate.py --marketplace-root .
python -m unittest discover -s plugins/develop/tests -p test_validate.py
python -m unittest discover -s plugins/develop/skills/iterate/scripts -p 'test_*.py'
```

Commit both manifests after portable metadata changes. For a detached installed payload, omit `--marketplace-root`; run fixture-writing package tests on a disposable copy outside the installed cache. Exercise [fresh-context scenarios](tests/scenarios.md), packaged references/helpers from an unrelated working directory, and actual icon legibility. Structure checks and simulated decisions do not prove installation, live publication or deployment.

## Source and installation changes

Before replacing another installed skill, inventory its live callers, helpers, links and repository-owned behavior. Verify the chosen replacement's source, version and installation state; disclose any installation gap. Preserve operations that remain specific to a repository. Machine-specific scripts and native transcript parsers are not copied into generic workflows.

Move retired sources and exact matching links to recoverable Trash where supported; preserve Git history, unrelated skills and work. Repair live callers and remove only obsolete grants/packaging entries. Retain repository-owned operations that were not consolidated under their proper owner. Source consolidation alone does not authorize installation, retirement, commits or publication.

`clean` defaults to this thread's disposable artifacts and processes across paths. Explicitly broaden scope (for example, "index and clean my entire machine starting at `/`") to use `deep-clean`; its policy disables implicit invocation. Both preserve retained plugin state, memories, secrets and useful/shared work. Deep inventories require installed Python 3.10+ and do not imply removal eligibility.
