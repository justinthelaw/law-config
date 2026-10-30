# Develop evaluations

The historical 20-repository panel found 15 ready proposals each for Codex and Develop, and 17 for the merged PRs. Develop cost 1.71× as much on 14 completely metered pairs and took 1.38× as long from checkout to proposal on 15 completed pairs; the five capacity-recovery pairs are a separate cohort. The primary campaign took 10h 23m through the last assessment, including interruptions; recovery took 2h 52m. [Results and case evidence](runs/pr-quality-panel-v2/README.md)

## Read results offline

From the repository root, install the [pinned reader dependencies](requirements.txt), then validate and inspect a published run. Python 3.11+ is required. If the packages are already installed, start with `check`.

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

Published `status NAME` output for a pilot shows proposal and judge costs separately, token totals, time to proposal and time through grading. It reports readiness and the three judges’ paired full-PR verdict. Its joint result requires a ready proposal, a blind PR win and complete cost at or below stock. Missing evidence is `null`. See the linked results for panel measures. `report NAME` verifies a published bundle offline. Each bundle has a `run.json` manifest and `submissions.jsonl` with patches, PR text, gates, judge evidence and usage. Missing artifacts are `null`; observed empty artifacts are `""`. [Record schema](schemas/panel-v1.json) · [Offline comparison tools](develop-benchmark/panel/README.md#adjudicate-and-export)

## Run a native benchmark

Prepare a Linux host and pinned Codex executable as described in the [panel runbook](develop-benchmark/panel/README.md#prepare-the-host). From the repository root:

```sh
e=docs/evaluations
export BENCHMARK_CODEX=/absolute/path/to/pinned/bin/codex
python3 -B "$e/benchmark.py" run trial-01
python3 -B "$e/benchmark.py" status trial-01
```

By default, this command uses the 20 historical tasks. It compares stock Codex with the reference Develop package and pinned Superpowers 6.3.0. Both arms can plan and delegate. Historical tasks authorize unattended implementation. Hypothesis pilots and fresh confirmation tasks also waive interactive plan review and retain required independent review. The operator freezes, grades and exports each run. Reuse its name to resume. Preparation and cold builds can take hours. [Treatment selection and host requirements](develop-benchmark/panel/README.md#choose-a-treatment)

| Goal | Path |
| --- | --- |
| Test one change on a tuning case | [Matched efficiency pilot](develop-benchmark/panel/README.md#run-a-matched-efficiency-pilot) · [Published tuning results](runs/tuning/) |
| Test a fixed package on fresh cases | Set `DEVELOP_EVAL_COHORT=pr-quality-confirmation-v1` and `PANEL_TREATMENT_LOCK` to the candidate’s `treatment.json`, then run a newly named full panel. Inspect progress with `status NAME`. |
| Freeze a candidate | `python3 -B "$e/benchmark.py" capture-treatment --previous RECIPE --label NAME`; add `--source CHECKOUT` for another checkout. |
| Replay a published caller check | `python3 -B "$e/tools/replay_caller.py" caller-werkzeug-01 public-warnings`; add `--run NAME` for another published pilot on the same task. |
| Recover primary capacity failures | `python3 -B "$e/benchmark.py" recover PRIMARY NEW_NAME`; report these fresh pairs separately. |

The baseline exposed its tuning and confirmation cases; use them for tuning and regression checks. A promotion claim needs fresh confirmation cases. Use `status NAME` to inspect a run; the [catalog](catalog.json) lists result locations and the [tuning records](runs/tuning/) contain published pilots. [Hypotheses and promotion criteria](runs/pr-quality-panel-v2/tuning.json)

## How scoring works

Each case compares stock Codex, Develop and the merged PR. Both proposal arms start on GPT-6.1 Sol Medium with the same tree, task, tools, resources and deadline. Stock chooses its workflow with native planning and subagents. New trials verify its clean profile. Some historical receipts are missing. Three fresh plugin-free judges assess all three submissions with rotated display positions. [Panel settings](develop-benchmark/panel/panel.json) · [Runbook](develop-benchmark/panel/README.md#operate-a-run)

Hard gates take precedence over scores: a nonempty eligible patch and PR, build and existing behavior, requested public behavior, and integrity and safety. A confirmed critical defect vetoes readiness; a judge flag requires adjudication. [Rubric](develop-benchmark/panel/rubric.md)

| Score | Components |
| --- | --- |
| Diff /85 | Contract and compatibility 35, regression protection 25, design and scope 25 |
| Full PR /100 | Diff plus PR communication 15 |

Displayed diff scores use median axis anchors; paired differences use the median of the three rotation differences. A soft PR preference requires three valid rotations, at least two judges agreeing on direction and a median paired weighted difference of at least five points. The separate strict efficiency target requires a ready candidate, higher full-PR quality and complete metered proposal cost at or below stock Codex; a tie misses it. Cost and time comparisons require complete comparable measurements, and assessor cost is separate. A simultaneous cost-and-time win uses equal-or-better quality with lower cost and shorter wall time. [Rubric](develop-benchmark/panel/rubric.md) · [Pilot criteria](develop-benchmark/panel/README.md#run-a-matched-efficiency-pilot)

## Other protocols

The [catalog](catalog.json) identifies each protocol and its denominator. Keep the [historical study](develop-benchmark/README.md), [source-packet replication](develop-benchmark/replication/README.md), [six-repository workflow](develop-benchmark/workflow/README.md), PR panel and capacity recovery separate. The marketplace installs `plugins/develop/`; evaluator assets and portable records live here. Private profiles, logs, caches and workspaces stay in ignored `tmp/` task directories; Docker manages its own image layers. [Maintenance rules](AGENTS.md)
