# Shared cleanup protections

Apply these rules to clean and deep-clean, including explicit whole-machine requests. Expanded discovery does not waive protection or grant privileged access.

Protect source, lockfiles, useful work and retained deliverables, `.env` files and variants, credentials, Codex memories, persistent application data, retained plugin caches/state and their bound cache repositories, and shared dependencies. Ordinary repository scratch is eligible when disposable and in scope. Preserve checkouts, Git metadata, worktrees, stashes, unpublished commits, current incidents, managed runtimes/mounts and services. Task retirement and SQLite repair are separate workflows and are not part of cleanup.

Resolve retained plugin state from known configuration and path-only binding fields, without initializing, refreshing or syncing plugins. For Q&A protect `CHATGPT_QA_STATE_DIR`, otherwise `$CODEX_HOME/chatgpt-question-and-answer` (Codex home defaults to `~/.codex`), all workspace/source paths in its `binding.json`, and `CHATGPT_QA_COORDINATION_DIR`, otherwise `$CODEX_HOME/chatgpt-qa-coordination`. Protect Codex memories under the actual Codex home and any configured alternate location. Preserve lexical paths and resolved aliases. If bindings or dependencies are uncertain, retain the uncertain candidate.

Exclude protected subtrees from broad inventories; never scan a root inside them. Recheck the complete protected set immediately before each mutation. Reject parent-directory operations, symlink aliases, task/worktree cascades, shared Git stores or process stopping that could affect protected descendants or dependencies. Lack of active handles, age, old versions or a clean tracked diff alone does not establish disposability.

Read only names and filesystem metadata for size inventories. Native process/handle inspection and minimal configuration path fields may support verification; never dump secret values or private file bodies into reports. Permission failure is a coverage gap, not authority to elevate. Revalidate identity, ownership, current use and traversal immediately before any action.
