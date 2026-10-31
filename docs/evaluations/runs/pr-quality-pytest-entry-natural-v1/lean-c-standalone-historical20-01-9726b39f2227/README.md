# Standalone Develop on 20 historical repositories

Standalone Develop scored **78.69/100**, versus **85.44/100** for fresh stock Codex. It took **23m 06s** versus **15m 16s** per attempt, including timeouts. The pre-registered stopping rule required at least two of quality, time and total cost to beat stock by 10%. Quality and time both missed. Total cost is unknown because one timeout in each arm has no usable meter.

| Measure | Stock | Standalone Develop | Coverage |
| --- | ---: | ---: | --- |
| Functional full-PR quality /100 | 85.44 | 78.69 | All 20, with failed and missing proposals scored zero |
| Functional PRs | 18 | 17 | All 20 |
| Checkout to submission or timeout | 15m 16s | 23m 06s | Mean across all 20 |
| Estimated proposal cost, complete pairs | $9.11 | $13.99 | 19 pairs, excluding the same unmetered timeout |
| Checkout to proposal, complete pairs | 15m 00s | 23m 14s | Mean across 19 pairs |

Develop's all-20 quality was 7.9% lower than stock and its mean elapsed time was 51.2% longer. On 19 fully metered completed pairs, Develop cost 53.5% more and took 1.55× as long. Those pairs used 48.66 million stock tokens and 81.75 million Develop tokens. The measured proposal costs establish lower bounds on all-attempt spend. The 20-case total-cost comparison remains unresolved. The 60 blind judge receipts total $7.41. Two [qualification probes](qualification.json) total an estimated $0.058. These are separate from proposal spend. Estimates use the frozen Standard rate card and differ from invoices. Human labor is unknown.

In the 19 priced pairs, model turns that only waited on running work cost $8.76 for Develop and $5.20 for stock. Most of that waiting overlapped commands already executing. On fd, Develop started two long Cargo commands that it later cancelled. On libarchive, it copied a toolchain and built multiple targets. Together those two repositories added 136 minutes and $4.96 versus stock. [Per-repository wait counts, costs and method](polling.json)

The three-rotation blind comparison favored Develop in 3 cases, stock in 6, tied in 10 and left one unresolved. Scores combine diff quality and PR communication. Executable gates and confirmed critical defects take precedence. The actual merged PRs averaged **62.69/100**, with 17 functional changes.

| Repository | Stock /100 | Develop /100 | Merge /100 | Time, stock / Develop | Cost, stock / Develop |
| --- | ---: | ---: | ---: | --- | --- |
| [BurntSushi/ripgrep](https://github.com/BurntSushi/ripgrep/pull/3578) | 100 | 100 | 83.75 | 10:24 / 12:14 | $0.353 / $0.313 |
| [CLIUtils/CLI11](https://github.com/CLIUtils/CLI11/pull/1479) | 96.25 | 96.25 | 80 | 6:12 / 8:52 | $0.259 / $0.300 |
| [apache/commons-lang](https://github.com/apache/commons-lang/pull/1840) | 90 | 75 | 56.25 | 10:28 / 7:39 | $0.445 / $0.291 |
| [django/django](https://github.com/django/django/pull/22169) | 53.75 | 96.25 | 50 | 12:36 / 14:38 | $0.383 / $0.459 |
| [fmtlib/fmt](https://github.com/fmtlib/fmt/pull/4981) | 100 | 100 | 78.75 | 16:45 / 23:28 | $0.413 / $0.648 |
| [go-git/go-git](https://github.com/go-git/go-git/pull/2538) | 100 | 100 | 96.25 | 39:03 / 38:14 | $1.233 / $1.706 |
| [jqlang/jq](https://github.com/jqlang/jq/pull/3694) | 100 | 100 | 86.25 | 66:28 / 65:33 | $1.726 / $1.074 |
| [justinthelaw/maximize-github-runner-space](https://github.com/justinthelaw/maximize-github-runner-space/pull/69) | 100 | 91.25 | 58.75 | 8:51 / 6:13 | $0.319 / $0.313 |
| [libarchive/libarchive](https://github.com/libarchive/libarchive/pull/3737) | 96.25 | 0 | 96.25 | 19:03 / 91:05 | $0.478 / $3.832 |
| [libexpat/libexpat](https://github.com/libexpat/libexpat/pull/1439) | 100 | 85 | 52.5 | 21:21 / 22:27 | $0.879 / $0.794 |
| [markedjs/marked](https://github.com/markedjs/marked/pull/4145) | 0 | 0 | 0 | 20:29 / 20:33 | ? / ? |
| [pallets/werkzeug](https://github.com/pallets/werkzeug/pull/3325) | 100 | 85 | 43.75 | 4:38 / 5:43 | $0.252 / $0.259 |
| [prometheus/client_golang](https://github.com/prometheus/client_golang/pull/2182) | 100 | 100 | 90 | 31:02 / 32:50 | $0.798 / $0.692 |
| [psf/black](https://github.com/psf/black/pull/5620) | 0 | 60 | 96.25 | 7:52 / 9:40 | $0.304 / $0.378 |
| [pypa/packaging](https://github.com/pypa/packaging/pull/1457) | 96.25 | 96.25 | 0 | 3:29 / 5:58 | $0.209 / $0.261 |
| [pytest-dev/pytest](https://github.com/pytest-dev/pytest/pull/15193) | 96.25 | 96.25 | 0 | 5:56 / 7:20 | $0.246 / $0.246 |
| [rspec/rspec](https://github.com/rspec/rspec/pull/353) | 96.25 | 96.25 | 83.75 | 4:49 / 4:55 | $0.181 / $0.195 |
| [sharkdp/fd](https://github.com/sharkdp/fd/pull/2196) | 87.5 | 96.25 | 90 | 2:20 / 66:10 | $0.102 / $1.711 |
| [sympy/sympy](https://github.com/sympy/sympy/pull/30827) | 96.25 | 0 | 55 | 11:15 / 16:04 | $0.465 / $0.430 |
| [tj/commander.js](https://github.com/tj/commander.js/pull/2653) | 100 | 100 | 56.25 | 2:26 / 2:19 | $0.070 / $0.083 |

Time is checkout to submission or timeout and includes setup. It excludes grading and judging. `?` denotes unmetered cost. Both Marked attempts timed out. Zeros include no proposal, failed required gates and confirmed critical defects. [Machine-readable comparison](comparison.json) · [Frozen run](run.json) · [Submissions and assessments](submissions.jsonl)

## Findings and limits

Four flagged roles were adjudicated against sealed evidence. SymPy Develop rejected a previously accepted tuple input. Its preservation probe failed while the Point3D controls passed. Libarchive Develop failed Windows-target preprocessing on the changed translation unit. The reproduction did not run a full Windows build or link. The Packaging merge accepted an invalid replacement field boundary. The Pytest merge's proposal claimed a guarded constructor and tests absent from its patch. The verified mismatch does not establish intent. [Reproduction evidence](evidence/).

The preceding 20-case run used Develop with Superpowers. Its stock / Develop quality means were 82.50 / 75.19, functional counts 18 / 16 and all-attempt mean times 20m 49s / 26m 33s. Its 17 complete pairs cost $11.23 / $14.19. Both runs used the historical natural protocol and the same rubric. They used different treatments and metered subsets. These exposed cases do not establish a fresh-case promotion or causality. [Prior report](../README.md)

This run used commit `72c2fda9e7e343e5d5ed73b474ad5f82e4dc5793`, standalone Develop package `0085f2ad8d61c0b153d7909f12b2e80f320676494e2bbe2fe83d1e6f07a7bd04`, stock Codex without optional plugins, Sol Medium, the unchanged historical evaluator and three rotated blind judges. The [portable recipe](../../../treatments/0085f2ad8d61/recipe.json) reconstructs the 84-file package. [Stopping rule and comparison method](compare.py).

Recompute the current comparison from the repository root.

```sh
python3 -B docs/evaluations/runs/pr-quality-pytest-entry-natural-v1/lean-c-standalone-historical20-01-9726b39f2227/compare.py \
  docs/evaluations/runs/pr-quality-pytest-entry-natural-v1/lean-c-standalone-historical20-01-9726b39f2227/run.json
```
