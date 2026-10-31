# Six-repository native workflow

Both workflows finished on five of the six repositories. Pure Codex stopped at provider capacity on jq. Develop finished jq, so that case has no complete pair. The [six-repository comparison](../../runs/native-workflow-v1/2026-10-28/comparison.json) retains every attempt. For the current twenty-repository protocol and its scoring rubric, use the [panel runbook](../panel/README.md).

## What changed after issue 71

| Earlier result | Change in this experiment |
| --- | --- |
| Both source-packet arms passed 7 of 13 fmt checks. Six affected call paths still failed. | Iterate asks for an observable check at each affected public entry point. |
| Both runner-space patches failed compilation. Develop's tests also had four type errors. | Iterate asks for the cheapest real compiler or typecheck before final review. |
| Develop used 23.5% more tokens on recovered fixtures and 25.7% more on replacements. | Shorter review packets group absent fields. Each workflow chooses its own reviewers. |
| Historical and replacement fixtures measured different behaviors. One browser suite timed out. | Grade each proposal against the same starting tree and compare it with its actual merge. |

Across 84 source-packet calls, Develop used 383,513 more total tokens and 379,358 more uncached input tokens. The four reviewer phases accounted for 217,537 excess tokens, or 56.7%. This native study tests the revised package as a whole. A separate treatment arm would be needed to attribute a difference to one edit. [Per-call usage](../replication/phase-usage.csv) · [Historical report](../README.md)

## Six pinned tasks

| Merged reference | First commit | Files | + / − | What the independent check exercises |
| --- | --- | ---: | ---: | --- |
| [packaging #1457](https://github.com/pypa/packaging/pull/1457) | Oct 19 | 3 | 186 / 1 | Python replacement dispatch, no-op identity, subclass preservation, explicit reset and invalid replacements |
| [ripgrep #3578](https://github.com/BurntSushi/ripgrep/pull/3578) | Oct 26 | 1 | 8 / 1 | Rust ignore walker and shared excludes in a real linked worktree |
| [jq #3694](https://github.com/jqlang/jq/pull/3694) | Oct 23 | 2 | 9 / 8 | C executable, exact stderr bytes, exit status and stdout |
| [Marked #4145](https://github.com/markedjs/marked/pull/4145) | Oct 17 | 3 | 55 / 12 | CommonMark delimiter flanking and multiple-of-three behavior |
| [go-git #2538](https://github.com/go-git/go-git/pull/2538) | Oct 23 | 5 | 386 / 70 | Public octal parsing and normalization, plus tree decoding against the Git CLI across a read buffer |
| [runner-space #69](https://github.com/justinthelaw/maximize-github-runner-space/pull/69) | Oct 25 | 3 | 55 / 2 | Action SHA, linter version tag, upgrade ledger and protected action/runtime artifacts |

The first five projects are external. Runner-space is the owner maintenance case and includes Dependabot contributions. The [manifest](cases.json) pins the base and merge, prompts, commands and images. Each worker receives a synthetic local commit with no remotes. jq retains its pinned submodule. The runner verifies snapshot paths, modes and blob IDs against upstream.

The first commits date from October 17–26, 2026. The model documentation lists an April 30 knowledge cutoff, and a public GPT-6.1 Sol run is dated October 6. These dates screen for recency. Exact training membership and author assistance are unknown. [Model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol) · [Dated model run](https://github.com/devrev/enterprise-bench/pull/106)

## Restore and run

Use Linux/amd64, Docker with QEMU, Git, Python 3.12+ and authenticated access to the frozen Codex distribution. Set `BENCHMARK_CODEX` to the Codex 0.166.0-alpha.3 executable. The distribution must include its matching `codex-resources/bwrap`. If a TLS proxy requires a public CA bundle, set `BENCHMARK_CA_FILE` to that path.

From the repository root, restore the historical package and runner.

```sh
python3 -B docs/evaluations/benchmark.py restore-six
```

Change to the printed workflow directory. Its private checkout contains the verified 205-file treatment. All raw data stays under that checkout's ignored `tmp/six-repo-workflow/`. Docker manages its own image layers.

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 -B run.py build-workers
for case in packaging ripgrep jq marked go-git runner-space; do
  python3 -B lab.py calibrate "$case" || exit 1
  python3 -B feasibility.py "$case" || exit 1
done
python3 -B run.py qualify && python3 -B run.py run
python3 -B report.py
```

Preparation fetches pinned Git objects and dependencies. Each model works as a non-root user in an offline two-vCPU guest. The controller owns authentication, reference objects and the held-out grader. Qualification checks both the root and a named child. It verifies isolation, per-thread usage, installed skills and trusted hook hashes.

Each task gets at least 20 minutes or twice its cold build and native test time, rounded up to a minute. The same deadline applies to both arms. Marked excludes timing-sensitive tests inside the emulated worker. The native-speed grader still runs the full upstream spec suite. These times describe this executor.

Admission requires the base to fail the target behavior with exit 42 and the merge to pass. Both must pass the selected build and regressions. Check authors saw the original change. The grader reapplies each submission to a clean base and records grading time separately. Empty patches, timeouts and technical stops stay visible.

## Review a pair

1. After both arms finish, run `python3 -B blind.py CASE`.
2. Give a fresh assessor the starting source and the generated `packet/` directory. It contains all three shuffled patches.
3. Have the assessor fill in `judgment-template.json`. Record ties, uncertainty and distinguishing evidence.
4. Seal the judgment with `python3 -B blind.py CASE --judgment FILE` before reading the private key.

The runner checks the task, patch digests and grades. The runner-space ledger can reveal authorship. Compare build outcomes, behavior, test quality and scope separately. Marked has two CommonMark examples that regress on the merge. The selected checks do not measure long-input parser performance.

## Resume after provider capacity

The primary run stops at its first infrastructure or service failure. If the error is `serverOverloaded`, use these commands in order.

```sh
python3 -B resume.py freeze
python3 -B resume.py run
python3 -B resume.py report
```

Freeze retains the primary report and its released receipts. Resume qualifies the root, child and hooks before releasing the remaining slots. A second capacity error pauses the supplement. The primary's five allocations and the supplement's seven stay in separate cohorts. The original jq stop stays in its primary row.

## Read the measurements

- Sum usage once per thread. Cached input is part of input, and reasoning is part of output. Preserve partial metering as a lower bound.
- Report setup, proposal, grading and qualification time separately. PR open-to-merge time includes queues and review. Human labor and spend are unknown.
- Compare each task with its own merge. Separate the external tasks from the owner case. One attempt per arm establishes the outcome for this sample.
