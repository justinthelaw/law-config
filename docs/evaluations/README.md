# Develop evaluations

On the historical 20-repository panel, Codex and Develop each produced 15 ready proposals. Seventeen merged PRs passed the same gates. Develop cost 1.71× as much across 14 fully metered pairs and took 1.38× as long from checkout to proposal across 15 completed pairs. The primary campaign took 10h 23m through assessment, including interruptions. Five recovery pairs took 2h 52m. [Results and case evidence](runs/pr-quality-panel-v2/README.md)

## Read results offline

Use Python 3.11+ from the repository root. If the reader dependencies are installed, run the last two commands. [Pinned dependencies](requirements.txt)

```sh
e=docs/evaluations
state="$PWD/tmp/pr-quality-panel"
mkdir -p "$state/volatile"
export TMPDIR="$state/volatile" TMP="$state/volatile" TEMP="$state/volatile"
python3 -m venv "$state/reader"
. "$state/reader/bin/activate"
python3 -m pip --cache-dir "$state/pip-cache" install -r "$e/requirements.txt"
python3 -B "$e/benchmark.py" check
python3 -B "$e/benchmark.py" status baseline
```

Panels export `run.json` and `submissions.jsonl`. Pilots export `result.json`. These records contain the patches, PR text, gates, judge evidence and usage. Missing artifacts are `null` and observed empty artifacts are `""`. [Record schema](schemas/panel-v1.json) · [Comparison tools](develop-benchmark/panel/README.md#adjudicate-and-export)

`status NAME` and `check` read published records offline. Pilot status shows readiness, the paired verdict, proposal and judge costs, tokens and time. `report NAME` verifies a published panel. For a locally registered pilot it re-exports from the frozen state using the matching cohort and evaluator source. Otherwise it verifies the published pilot. [Runbook](develop-benchmark/panel/README.md#operate-a-run)

## Run a native benchmark

Prepare a Linux host and pinned Codex executable, then run from the repository root. [Host setup](develop-benchmark/panel/README.md#prepare-the-host)

```sh
e=docs/evaluations
export BENCHMARK_CODEX=/absolute/path/to/pinned/bin/codex
python3 -B "$e/benchmark.py" run trial-01
python3 -B "$e/benchmark.py" status trial-01
```

Default runs compare stock Codex with reference Develop and pinned Superpowers 6.3.0 on historical tasks. Both start on GPT-6.1 Sol Medium and may plan or delegate. Historical tasks authorize unattended implementation. Hypothesis pilots and fresh confirmation tasks waive interactive plan review and retain required independent review. Resume a run from its frozen evaluator source. The operator restores its cohort and rejects conflicting overrides. Preparation and cold builds can take hours. [Treatment selection](develop-benchmark/panel/README.md#choose-a-treatment)

| Goal | Path |
| --- | --- |
| Test one change on a tuning case | [Matched efficiency pilot](develop-benchmark/panel/README.md#run-a-matched-efficiency-pilot) · [Published tuning results](runs/tuning/) |
| Test a fixed package on fresh cases | Set `DEVELOP_EVAL_COHORT=pr-quality-confirmation-natural-v1` and `PANEL_TREATMENT_LOCK` to the candidate’s `treatment.json`, then run a newly named full panel. Inspect progress with `status NAME`. |
| Freeze a candidate | `python3 -B "$e/benchmark.py" capture-treatment --previous RECIPE --label NAME`. Add `--source CHECKOUT` for another checkout. |
| Replay a published caller check | `python3 -B "$e/tools/replay_caller.py" caller-werkzeug-01 public-warnings`. Add `--run NAME` for another pilot on the same task. |
| Recover primary capacity failures | `python3 -B "$e/benchmark.py" recover PRIMARY NEW_NAME`. Report recovery pairs separately. |

The baseline exposed both splits. Use those cases for tuning and regression checks. Use fresh cases for promotion. [Published pilots](runs/tuning/) · [Historical tuning policy](runs/pr-quality-panel-v2/tuning.json) · [Current promotion criteria](develop-benchmark/panel/rubric.md)

## How scoring works

Both arms start on GPT-6.1 Sol Medium with the same tree, task, tools, resources and deadline. New trials verify that stock has no plugins, apps, MCP servers or task-specific assistant configuration. Some historical inventory receipts are missing. Three plugin-free judges assess both proposals and the merged PR in rotated positions. [Panel settings](develop-benchmark/panel/panel.json) · [Runbook](develop-benchmark/panel/README.md#operate-a-run)

Hard gates cover an eligible nonempty patch and PR, build and existing behavior, requested public behavior, and integrity and safety. They take precedence over scores. A confirmed critical defect vetoes readiness. A judge flag requires adjudication. [Rubric](develop-benchmark/panel/rubric.md)

| Score | Components |
| --- | --- |
| Diff /85 | Contract and compatibility 35, regression protection 25, design and scope 25 |
| Full PR /100 | Diff plus PR communication 15 |

Displayed scores use median axis ratings. A blind full-PR win requires three valid rotations, at least two judges agreeing on direction and a median paired lead of five points or more. The strict target requires that win, a ready Develop PR and complete proposal cost at or below stock. A tie fails. Across the fresh 20, every case must pass under one fixed plan. A known miss gives `false`. With no known miss, missing evidence gives `null`. [Rubric](develop-benchmark/panel/rubric.md) · [Pilot criteria](develop-benchmark/panel/README.md#run-a-matched-efficiency-pilot)

Compare cost and time only on fully measured pairs. Report assessor cost separately. The historical simultaneous-win metric requires equal-or-better quality, lower cost and shorter wall time.

## Other protocols

Each protocol has its own denominator. [Catalog](catalog.json) · [Historical study](develop-benchmark/README.md) · [Source-packet replication](develop-benchmark/replication/README.md) · [Six-repository workflow](develop-benchmark/workflow/README.md)

The marketplace installs `plugins/develop/`. Evaluators and portable records live here. Private profiles, logs, caches and workspaces stay under ignored `tmp/`. Docker manages its image layers. [Maintenance rules](AGENTS.md)
