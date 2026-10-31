# Develop on 20 historical repositories

Stock Codex averaged **82.50/100** across all 20 tasks. Develop with Superpowers averaged **75.19/100**. The actual merged PRs averaged **59.88/100**, with 17 functional changes. Each repository received one stock attempt, one Develop attempt and three blind reviews against the merge.

| Measure | Stock Codex | Develop | Develop vs. stock | Coverage |
| --- | ---: | ---: | ---: | --- |
| Mean functional PR quality /100 | 82.50 | 75.19 | -7.31 points | All 20 |
| Functional PRs | 18 | 16 | -2 | All 20 |
| Mean checkout to PR | 22m 40s | 27m 35s | +21.7% time | 17 completed pairs |
| Mean checkout to completion or timeout | 20m 49s | 26m 33s | +27.5% time | All 20 |
| Estimated proposal cost | $11.23 | $14.19 | +26.4% | 17 pairs |
| Total tokens | 65.63M | 74.62M | +13.7% | 17 pairs |

The quality mean gives equal weight to all 20 repositories. A missing PR, a failed mandatory check or a confirmed critical defect earns zero. The blinded full-PR score combines code and tests (85 points) with PR communication (15). Three judges rotate the labels and the rubric uses per-axis medians. Among submissions with a complete score, including scored failures, the means were 89.12 for stock (n=20), 91.62 for Develop (n=17) and 66.56 for the actual merges (n=20). [Rubric](../../develop-benchmark/panel/rubric.md) · [Scores and frozen reporting rule](comparison.json)

In the paired blind comparison, Develop won 4, stock won 3 and 10 tied. Three pairs lacked a complete Develop PR score. Each of Develop's four blind wins cost more than stock. No repository recorded a ready Develop PR with a blind win at equal or lower cost. Against the actual merges, stock won 18, tied once and lost once. Develop won 14, tied twice and lost once across its 17 scored proposals.

Across all attempts, stock's estimated proposal spend was $12.53. Develop's observed spend was at least $15.04. Develop timed out on Marked, Black and SymPy. These three pairs lack complete cost meters. Proposal estimates use the frozen Standard rates for root and worker tokens. Human labor, cost and active implementation time are unknown.

## Results by repository

Time is checkout to capture in minutes and seconds. A dagger marks a timeout. A lower bound includes observed usage from an incomplete meter. Each upstream link opens the PR scored as the merge.

| Repository | Stock /100 | Develop /100 | Merge /100 | Time, stock / Develop | USD, stock / Develop | Upstream PR |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| apache/commons-lang | 93.75 | 93.75 | 56.25 | 9:23 / 15:06 | $0.442 / $0.655 | [#1840](https://github.com/apache/commons-lang/pull/1840) |
| BurntSushi/ripgrep | 96.25 | 96.25 | 83.75 | 7:50 / 12:22 | $0.271 / $0.390 | [#3578](https://github.com/BurntSushi/ripgrep/pull/3578) |
| CLIUtils/CLI11 | 96.25 | 96.25 | 86.25 | 6:00 / 8:01 | $0.268 / $0.343 | [#1479](https://github.com/CLIUtils/CLI11/pull/1479) |
| django/django | 100 | 53.75 | 50 | 11:41 / 19:43 | $0.460 / $0.754 | [#22169](https://github.com/django/django/pull/22169) |
| fmtlib/fmt | 96.25 | 96.25 | 78.75 | 23:35 / 22:53 | $0.547 / $0.485 | [#4981](https://github.com/fmtlib/fmt/pull/4981) |
| go-git/go-git | 96.25 | 96.25 | 96.25 | 42:32 / 48:46 | $1.408 / $1.597 | [#2538](https://github.com/go-git/go-git/pull/2538) |
| jqlang/jq | 100 | 100 | 82.5 | 64:07 / 66:09 | $1.106 / $0.939 | [#3694](https://github.com/jqlang/jq/pull/3694) |
| justinthelaw/maximize-github-runner-space | 96.25 | 90 | 52.5 | 9:32 / 10:06 | $0.339 / $0.362 | [#69](https://github.com/justinthelaw/maximize-github-runner-space/pull/69) |
| libarchive/libarchive | 96.25 | 0 (failed) | 77.5 | 96:12 / 128:28 | $3.402 / $3.135 | [#3737](https://github.com/libarchive/libarchive/pull/3737) |
| libexpat/libexpat | 60 | 100 | 33.75 | 15:58 / 22:18 | $0.485 / $1.111 | [#1439](https://github.com/libexpat/libexpat/pull/1439) |
| markedjs/marked | 0 (failed) | 0 (no PR) | 0 (failed) | 13:31 / 20:42† | $0.525 / ≥$0.491 | [#4145](https://github.com/markedjs/marked/pull/4145) |
| pallets/werkzeug | 85 | 96.25 | 43.75 | 5:42 / 7:38 | $0.285 / $0.531 | [#3325](https://github.com/pallets/werkzeug/pull/3325) |
| prometheus/client_golang | 100 | 100 | 90 | 28:48 / 30:47 | $0.668 / $0.977 | [#2182](https://github.com/prometheus/client_golang/pull/2182) |
| psf/black | 0 (failed) | 0 (no PR) | 81.25 | 9:15 / 20:40† | $0.467 / ? | [#5620](https://github.com/psf/black/pull/5620) |
| pypa/packaging | 66.25 | 96.25 | 0 (failed) | 6:45 / 7:07 | $0.279 / $0.502 | [#1457](https://github.com/pypa/packaging/pull/1457) |
| pytest-dev/pytest | 75 | 96.25 | 0 (failed) | 7:10 / 10:45 | $0.266 / $0.644 | [#15193](https://github.com/pytest-dev/pytest/pull/15193) |
| rspec/rspec | 96.25 | 96.25 | 83.75 | 4:43 / 5:54 | $0.217 / $0.308 | [#353](https://github.com/rspec/rspec/pull/353) |
| sharkdp/fd | 96.25 | 96.25 | 86.25 | 43:05 / 49:19 | $0.703 / $1.323 | [#2196](https://github.com/sharkdp/fd/pull/2196) |
| sympy/sympy | 100 | 0 (no PR) | 58.75 | 8:20 / 20:40† | $0.310 / ≥$0.353 | [#30827](https://github.com/sympy/sympy/pull/30827) |
| tj/commander.js | 100 | 100 | 56.25 | 2:13 / 3:37 | $0.080 / $0.136 | [#2653](https://github.com/tj/commander.js/pull/2653) |

The four adjudicated findings have executable reproduction receipts in the two run manifests. Stock Black raises an exception on a valid skipped unary expression. The merged Packaging change accepts invalid replacements. Develop SymPy breaks coordinate tuples. Develop libarchive reports success after dropping a 4,096-byte sparse hole, while stock and the merge preserve all 8,199 output bytes.

## Paired time and usage

| Across complete pairs | Stock Codex | Develop |
| --- | ---: | ---: |
| Setup time | 8m 22s | 10m 58s |
| Prompt to terminal | 6h 16m 19s | 7h 37m 24s |
| Checkout to PR | 6h 25m 16s | 7h 48m 58s |
| Executable grading | 13m 40s | 13m 34s |
| Checkout through grading | 6h 39m 21s | 8h 02m 57s |
| Uncached input | 1,207,205 | 2,048,876 |
| Cached input | 64,184,832 | 72,282,368 |
| Output, including reasoning | 239,316 | 286,762 |

These time and token sums use the same 17 pairs. Across all 20 attempts, total checkout time was 6h 56m 22s for stock and 8h 51m 00s for Develop. The 95% repository-bootstrap intervals were -24.19 to 6.44 points for the Develop minus stock quality difference, 1.12× to 1.33× for checkout time and 1.07× to 1.63× for proposal cost.

## Run scope and comparison

Both arms started on GPT-6.1 Sol Medium and could delegate. Stock loaded no optional plugins, apps, MCP servers or task-specific global instructions. Develop loaded one fixed package with the pinned Superpowers 6.3.0 companion. These 20 tasks were previously exposed. The 12- and 8-repository runs had separate qualifications and disjoint selections. They used identical task references, fixtures, model settings, treatment, rubric and seeded order. [Treatment lock](../../treatments/composite-0fc66bb5a2e2e81926cd8357158d80056d8bc995d5236cfec4a4e609017c7a63/treatment.json)

| Batch | Cases | Blind reviews | Start to freeze | Freeze to last measurement | Qualification | Judges |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Tuning](iterate-entry-tuning-01-92e6c13f504c/run.json) | 12 | 36 | 3m 35s | 5h 33m 26s | $0.08 | $5.16 |
| [Historical remainder](iterate-entry-historical-rest-01-00f8ed9d08e7/run.json) | 8 | 24 | 3m 34s | 4h 59m 49s | $0.08 | $2.80 |

The two operators took 10h 43m 20s from the first start to the last review, including the gap between batches. The 60 judge receipts total $7.95. The four qualification probes total $0.16. Both are separate from proposal spend.

| Historical full-panel result | Earlier primary | Current |
| --- | ---: | ---: |
| Mean stock / Develop / merge quality, all 20 | 70.88 / 66.50 / 63.06 | 82.50 / 75.19 / 59.88 |
| Functional stock / Develop / merge PRs | 15 / 15 / 17 | 18 / 16 / 17 |
| Develop / stock proposal cost | 1.71× (14 pairs) | 1.26× (17 pairs) |
| Develop / stock checkout time | 1.38× (15 pairs) | 1.22× (17 pairs) |

The current run added the Pytest console-entry check and corrected the Runner Space ledger check. The older Runner Space grader rejected stock's wrapped Markdown. The earlier five-pair capacity recovery is a separate cohort. The changes in package, graders and metered subsets limit attribution across runs. [Earlier primary and recovery](../pr-quality-panel-v2/README.md) · [Common-repository comparisons](comparison.json)

From the repository root, verify the native bundles and recompute the quality, cost, token and time comparisons. [Reader setup](../../README.md#read-results-offline)

```sh
python3 -B docs/evaluations/benchmark.py check
python3 -B docs/evaluations/benchmark.py report iterate-entry-tuning-01
python3 -B docs/evaluations/benchmark.py report iterate-entry-historical-rest-01
python3 -B docs/evaluations/runs/pr-quality-pytest-entry-natural-v1/verify.py
```

The measured evaluator is commit `dce3d69307fc579dbbdf7f18cdc1dd3834512fad`. The first launcher stopped before allocating a proposal. It resumed the same plan with `PYTHONPATH` set to the evaluator's panel directory on the host. The worker VMs supplied their own paths. During export, the finalizer used the companion directories recorded at release. Their package, catalog and all 40 original profile configuration hashes were verified. [Setup and operator commands](../../README.md)
