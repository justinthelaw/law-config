# Run the twenty-repository PR panel

From the repository root, set `BENCHMARK_CODEX` to the pinned Linux executable. Give the run a new name. The same command resumes an interrupted run.

```sh
e=docs/evaluations
export BENCHMARK_CODEX=/absolute/path/to/pinned/bin/codex
python3 -B "$e/benchmark.py" run trial-01
```

## Prepare the host

Use Linux/amd64, Python 3.11+, Git, Docker and `taskset`. Install the [pinned reader dependency](../../requirements.txt). The default three lanes need six available CPUs. Each lane receives its own two CPUs. Set `--jobs 1` or `--jobs 2` on the first release to use fewer CPUs. Resume with the original layout.

Install the frozen Codex Linux distribution and its adjacent `codex-resources/bwrap`. The [host adapter](../workflow/host.py) lists both SHA-256 hashes. The host must be able to run authenticated model turns from fresh Codex profiles. Workers have no network interface beyond loopback. Only the controller prepares dependencies and holds reference objects, hidden checks and credentials. If the TLS proxy requires a public CA bundle, set `BENCHMARK_CA_FILE` to its path.

On a new name, the operator checks the native executable, sandbox helper and selected package. It verifies the installed marketplace bytes before the first model call. Preparation fetches pinned public source and dependencies. It calibrates missing fixtures, measures cold builds and probes both arms. Long first builds can take hours. Private files use `tmp/pr-quality-panel/`. Docker stores its own layers.

## Choose a treatment

New runs install the 106-file reference Develop package with official Superpowers 6.3.0. Its four maintenance skills require explicit selection. Stock and judges use clean profiles. The historical baseline and recovery used a 205-file Develop package alone. [Default lock](../../treatments/composite-6885dd085133250a524251e7dd0bfbb0302a841e5d08464c580890c9055f71aa/treatment.json) · [Develop recipe](../../treatments/3b0bd70d20a6/recipe.json) · [Historical lock](treatment.json)

| Run | Selection |
| --- | --- |
| Default treatment | Run without overrides to restore the package pinned in the catalog. |
| Reference Develop alone | Set `PANEL_TREATMENT_LOCK` to the [106-file lock](../../treatments/3b0bd70d20a6/treatment.json). Leave `PANEL_PLUGIN_CHECKOUT` unset to restore its source. |
| Historical Develop treatment | Set `PANEL_TREATMENT_LOCK` to the absolute path of `treatment.json`. The operator reconstructs the package from the [recipe](../../treatments/c619be0cc266/recipe.json) and its Git base. |
| New candidate | Set `PANEL_PLUGIN_CHECKOUT` to the candidate checkout. Set `PANEL_TREATMENT_LOCK` to its reviewed lock. Choose a new run name. |
| Historical report with raw receipts | Use `report NAME`. The operator selects the plan’s historical treatment automatically. |

The operator reconstructs each package in the ignored task directory. New recipes store the difference from one verified full package. Restoration checks both package hashes. Changes to the hook command boundary need a separate isolation review.

## Operate a run

| Command after `python3 -B "$e/benchmark.py"` | Result |
| --- | --- |
| `check` | Run model-free tests, check the package boundary and validate portable results. |
| `status NAME` | Read the frozen scope, proposal counts, pending assessments and flagged roles. |
| `run NAME` | Prepare and freeze all 20 cases, collect proposals, judge them and export. |
| `run NAME --split tuning` | Freeze all controls and select the 12 tuning cases before release. |
| `run NAME --split confirmation` | Select the eight assigned confirmation cases before release. |
| `report NAME` | Regenerate the results after adjudication. A published result verifies offline. |
| `recover PRIMARY NEW_NAME` | Run fresh pairs only for primary service-capacity failures. |

Before proposal or assessor calls, the operator checks the reader package versions. Each case receives one native proposal from pure Codex and one from Develop. Each arm uses the same starting tree, task, tools, resources and deadline. Develop adds its installed skills and trusted hooks. Pure uses five stock skills. Both arms inherit the same two organization-managed protections and disable optional repository skills. Built-in repository instructions remain available.

The plan fixes each arm’s order. Each lane runs both arms consecutively on one CPU pair. The operator serializes runs that share cache and CPU lanes. It preserves every allocation, including empty submissions and service failures. After a technical stop, inspect `status NAME`. Rerun the same name to requalify the service and release only remaining slots.

Three fresh, plugin-free judges each see all three submissions. The display order rotates. A primary rotation allows one technical repair. Recovery allows one assessor call per rotation and one fresh pair per affected case. It uses the original CPU pairs and records its parent plan. A named recovery pauses new releases if a proposal is blocked. In-flight proposals finish. Resume the same name to qualify the service before spending the remaining calls. The bundle records the release policy and any slots allocated before it took effect.

If every attempt for a rotation is allocated and no terminal record exists, status lists it under `stranded_assessments`. Repeating the name preserves that evidence.

A command exits with code 0 when the report has complete assessments. Code 2 indicates a setup, input or integrity error. Code 3 indicates remaining work or a report with missing evidence. Inspect the named status and raw receipts. A reported comparison can include a failed gate or a capacity-stopped proposal.

## Run a matched efficiency pilot

Select a tuning case and both treatment locks. Use `--hypothesis ID` for a case in the published tuning policy or the candidate’s `hypothesis.json`. The latter binds the previous package and is hashed at registration. Each arm receives the same waiver of interactive plan review. All three proposal slots share the CPU pair, task, deadline, grader and prices. Pure Codex exposes only stock skills and organization protections inside the common offline boundary.

```sh
e=docs/evaluations
python3 -B "$e/benchmark.py" pilot intent-go-git-01 --case go-git \
  --prior "$e/treatments/579bba8e795d/treatment.json" \
  --candidate "$e/treatments/50e517f82dce/treatment.json"
```

Three blinded judges compare the candidate, pure Codex and the merge. A strict win requires a ready candidate, higher full-PR quality and complete proposal cost at or below pure. A tie misses the target. Compare prior Develop on verified behavior, required reviews, cost and checkout-to-proposal time. Its soft PR quality stays unknown. The pilot records every allocation under `tmp/pr-quality-panel/`. Resume the same name after interruption.

After grading, run the candidate hypothesis’s `measure_with` command if present. Keep its JSON receipt under `tmp/pr-quality-panel/pilots/NAME/sensitivity/MEASURE/receipt.json`. Then run `python3 -B "$e/benchmark.py" report NAME` to export all four submissions, the three proposal costs and separate assessor costs. The same command verifies `runs/tuning/NAME/result.json` offline in a fresh checkout.

## Prospective runner protocol

Select `pr-quality-runner-v3` for a newly named historical runner pilot; repeat the exact command and locks to resume, and retain the same cohort for reports:

```sh
DEVELOP_EVAL_COHORT=pr-quality-runner-v3 python3 -B "$e/benchmark.py" pilot NAME --case runner-space --prior PRIOR/treatment.json --candidate CANDIDATE/treatment.json --hypothesis ID
```

This opt-in uses a read-only [loopback hosts fixture](../workflow/vm/loopback.hosts) in the same worker transport and a [structural checker](../workflow/checks/runner_lint_ledger_v3.mjs) for the exact configured pin, recognized static false guards, preserved files and a changed nonempty regular Markdown ledger. Other hosted conditions remain unverified and subject to patch review. The identical blind scope note asks all labels and rotations to assess ledger accuracy under the existing contract axis. The [catalog](../../catalog.json) identifies its full-panel archive; no new outcome is claimed. Default v2 source is preserved locally at `f9f34ce8f9ed2d19c2e68df49a6e1ad8644e78dc`. Reproducing an older full local run requires its exact old source and private frozen state; portable published records remain readable offline.

## Adjudicate and export

Read `tmp/pr-quality-panel/runs/NAME/report/results.json`. For each flagged role, reproduce the exact behavior on the captured patch. Save the ruling under `adjudications/CASE.json` in that run.

```json
{
  "develop": {
    "resolution": "confirmed",
    "evidence": "Name the affected file, observed behavior, runnable check and result."
  }
}
```

Use `cleared` when the reproduction clears the finding. Every flagged role needs a ruling and nonempty evidence. Then run `report NAME`. The exporter verifies patches, PR text, grades, judge rotations, usage and plan hashes. It writes one manifest and one JSONL file under `docs/evaluations/runs/pr-quality-panel-v2/`. Existing published bytes are immutable. [Offline reader and comparator](../../README.md)

## Interpret the comparison

| Measure | Evidence |
| --- | --- |
| Readiness | Patch application, build, selected regressions, public-interface checks, preservation controls and confirmed critical defects |
| Diff quality | Contract and compatibility, regression tests, design and scope. Maximum 85 points. |
| Full PR quality | Diff quality plus 15 points for PR communication. Executable failures take precedence. |
| Cost and tokens | Final counters per distinct root and descendant. The frozen Standard rates estimate USD. Partial receipts stay separate. |
| Wall time | Checkout through sealed submission, with model time, setup, grading and total campaign time recorded separately. Human open-to-merge time includes queues and review. |

The panel covers 19 external repositories and one owner project in ten languages or language combinations. The pinned trees contain 60 to 7,089 files. Each case records its revisions, dates, domain, source size and test commands. The PR statistics count changed files, added lines and removed lines. Six cases also have a descriptive complexity note. First commits fall between October 9 and 26, 2026. Training-set membership and human labor are unknown. [Case manifest](panel.json)

Each arm has one attempt per repository. Check authors saw the merged PRs. CLI11, Commons Lang and RSpec use narrow smoke tests. Marked excludes machine-speed-sensitive tests from its worker command and retains them in the independent grader. A merged PR can fail a specification-based check. [Rubric and research](rubric.md) · [Observed upstream descriptions](upstream.json) · [Issue 71](https://github.com/justinthelaw/law-config/issues/71) · [PR 74](https://github.com/justinthelaw/law-config/pull/74)

Use the tuning cases to choose one skill, hook or script change. Record its predicted effect and rejection criteria before release. Compare the same eligible cases, treatment controls and split. The baseline exposed all eight confirmation cases. Use fresh confirmation tasks for any promotion claim. [Tuning hypotheses](../../runs/pr-quality-panel-v2/tuning.json)

## Compare Develop with Superpowers

Compose a separate lock for each frozen Develop recipe, then preflight it before a named pilot. The companion is the official Codex Superpowers 6.3.0 at `openai/plugins` commit `0722921d5542fc593105c27bd52630babd8b8c2a`; its package digest is `819308376b259ec99111ff44593b7196d9bf08666be5bc6b6f8124b100a5642c`. The operator fetches once into the ignored cache and generates an isolated local marketplace from that commit. A fresh checkout with an empty task cache exercises the cold path. Keep the returned lock paths.

```sh
python3 -B "$e/benchmark.py" compose-treatment --develop PRIOR/treatment.json --label prior-superpowers
python3 -B "$e/benchmark.py" compose-treatment --develop CANDIDATE/treatment.json --label candidate-superpowers
python3 -B "$e/benchmark.py" preflight --treatment COMPOSITE/treatment.json
python3 -B "$e/benchmark.py" pilot NAME --case CASE --prior PRIOR_COMPOSITE/treatment.json --candidate CANDIDATE_COMPOSITE/treatment.json --hypothesis ID
```

For a shared-companion hypothesis, set `common_companion` to the pinned `source_commit` and `package_sha256`; registration rejects missing or mismatched components before release. A resumed run selects the composite lock from its frozen plan. Check the run's `inventory.json`, `qualification.json` and stored lock for package, skill and hook evidence. Stock and judge profiles remain plugin-free.
