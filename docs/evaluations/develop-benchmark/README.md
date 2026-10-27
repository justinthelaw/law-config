# Develop benchmark

[Read the illustrated report](report.pdf) · [Case manifest](cases.csv) · [Historical ledger](ledger.csv)

Does Develop 0.9.0 help Codex implement a bounded change more correctly, and what does it cost? In five completed historical pairs, both arms passed the task-specific acceptance checks. None demonstrated a production-behavior advantage for Develop. Across those five pairs, Develop used 9.6% more release-to-final time and 51.2% more total context tokens, including cache. Only Requests and Cobra count toward the final eight-case slate. [Results and assessments](https://github.com/justinthelaw/law-config/issues/71#evidence-g:~:text=final%20selected%20sources)

Roux chose the experimental setup and interpreted the historical results. The design warrants independent reassessment. This report distinguishes measurements, historical blind judgments, and a later executor qualification that produced no scored turns. [Continuation results](https://github.com/justinthelaw/law-config/issues/71#issuecomment-6434762307)

## Cases and gold references

The original target was 20 distinct cases and up to 80 trials. After some results existed, the scope changed to one valid pair on each of eight purposively selected cases. Five are external open-source projects. Three are user-owned and have possible prior-context exposure. Analyze those three separately. The five completed historical pairs cover Python and Go only.

Each link identifies the merged **gold** PR. In every selected case, gold's first parent is the frozen base. The manifest holds the full base and gold commit IDs, requirement SHA-256, stratum, difficulty, arm order and time limit. Verify those identities against the merged PR and its parents before reconstructing the case. A PR's current base reference can move. [Source identities](https://github.com/justinthelaw/law-config/issues/71#evidence-g:~:text=final%20selected%20sources)

| Gold PR | Requirement | Historical disposition | First arm / minutes per arm |
| --- | --- | --- | --- |
| [Requests #7505](https://github.com/psf/requests/pull/7505) | Accept readable file-like proxies in request bodies and multipart uploads. | Complete. Both arms passed 7/7 checks. | Control / 40 |
| [Cobra #2397](https://github.com/spf13/cobra/pull/2397) | Reject duplicate positional arguments with a composable validator. | Complete. Both passed 13 leaf subcases and the full Go suite. | Develop / 20 |
| [Tokio #8686](https://github.com/tokio-rs/tokio/pull/8686) | Add mutable access to a once-set value. | Prepared, no arms. Worker baselines passed 26/26. The new API failed to compile on base. | Control / 20 |
| [fmt #4993](https://github.com/fmtlib/fmt/pull/4993) | Format a null pointer consistently in compiled and runtime formatting. | Develop's partial patch passed 13/13 acceptance. Final review hit a service limit. Control never started. | Develop / 20 |
| [Svelte #19076](https://github.com/sveltejs/svelte/pull/19076) | Keep uncommitted fork state out of reactive observations. | Prepared, no arms. Independent acceptance passed 8/8 on base and gold. A separate gold-derived suite distinguished 0/2 from 2/2. | Develop / 75 |
| [Personal site #413](https://github.com/justinthelaw/justinthelaw/pull/413) | Restore arcade controls after iframe navigation and reopening. | Unadmitted. Offline install and base build passed. Five browser projects still needed runtime validation. | Control / 75 |
| [law-config #20](https://github.com/justinthelaw/law-config/pull/20) | Bound SQLite lock retries during orphan pruning. | Develop stopped before edits, control unattempted. Synthetic acceptance was 2/7 on base and 7/7 on gold. | Develop / 75 |
| [Runner-space #50](https://github.com/justinthelaw/maximize-github-runner-space/pull/50) | Detect target replacement and incomplete removal safely. | Prepared with limits, no arms. Behavioral checks passed 3/9 on base and 9/9 on gold. Six native permission failures affected both. | Control / 75 |

The three supplemental gold PRs are [Starlette #3718](https://github.com/Kludex/starlette/pull/3718), [Flask #6096](https://github.com/pallets/flask/pull/6096) and [Hugo #15474](https://github.com/gohugoio/hugo/pull/15474).

## Execution and isolation

1. **Freeze the inputs.** Use Codex CLI 0.159.2, executable SHA-256 `1748767b230ebfc3d4ab7e4e254920d0c0ad9691fd8c11f190e7d44511a4a92e`, with `gpt-6.1-sol` at medium effort. The exact provider model revision was unavailable. Develop 0.9.0 is commit `cd316824048d03e8ca1cefdf5d63a71b2f5b3021`, package tree `489905e4f5b9d931cdcde93a38450154a0feb801`. Freeze requirements, role prompts, verification code, toolchain and dependency identities before release. [Archive receipt and runbook](https://github.com/justinthelaw/law-config/issues/71#evidence-h:~:text=independent%20payload%20receipt)
2. **Separate evaluator and worker material.** Keep gold, hidden tests, upstream history and arm mapping in evaluator storage. Give each arm its own clean base snapshot with one synthetic commit, no upstream history or remotes, applicable repository guidance, and matched offline dependencies. Strip PR links, solution hints and patch content from worker prompts. Public downloads are preparation-only. Run base and gold checks offline and record any shared failure, nondiscriminating fixture or missing prerequisite.
3. **Isolate both arms and their descendants.** Restrict tools to the case workspace and role-specific scratch. Make toolchains read-only. Deny worker-command network access, sibling work, evaluator material and authentication paths. Develop receives the frozen instructions. Control must be unable to discover or read the package. Keep provider inference on a supported authenticated transport outside worker commands. Check direct and descendant processes, relative paths, symlinks, and process-filesystem escape paths. Historical reviewers could create new top-level entries in their own arm, a recorded limitation.
4. **Match execution.** Release fresh arms serially in the order above. Give each two CPUs, the same model, wall limit and tool access apart from Develop. Each arm in the five completed pairs had an implementation root, two planning reviewers and two final-evidence reviewers. Both arms used this review process, with up to three rounds per checkpoint. Start the clock before instruction loading and planning. Include reviews, waiting and repairs through final artifact receipt or enforced termination. Account for setup and grading separately.
5. **Retain all outcomes.** Stop at the first service-limit error, failed release gate or frozen deadline. Retain partial work and unknown usage. A resource-invalid attempt can receive at most one fresh complete-pair retry under the declared rules. fmt and law-config each have one left. Vue consumed its retry. Never pair a new arm with a surviving arm from an invalid attempt or replace cases after seeing quality outcomes. [Failures and deviations](https://github.com/justinthelaw/law-config/issues/71#evidence-d:~:text=preparation%20history)

To reconstruct a fixture, decode the harness and three-part selected-case archive from Evidence H into evaluator-only storage. Verify SHA-256 `3c104cb36a0341c253c238fcc761268ec2a1ff180ed645ff3084791baaca3e1f` for the harness and `1d0f71c4c4c313a01d8d5232f17792769dfceef4797a627520ab5284aa7c4344` for the selected cases. Inspect archive paths before extraction, verify the 178 manifest entries, then rebuild only that arm's allowed inputs. Prepare one case at a time, check free storage and preserve the 1 GiB reserve. Record relocated paths, effective configuration hashes, loaded instructions and usage coverage. Treat a changed environment as a versioned replication. [Payload receipt and reconstruction procedure](https://github.com/justinthelaw/law-config/issues/71#evidence-h:~:text=independent%20payload%20receipt)

## What is measured

**Correctness.** A successful arm meets the frozen requirement with no new relevant regression. Report each task's acceptance and applicable native checks. Distinguish a compile-negative reference, runtime failure, timeout, environmental failure and unknown. Do not pool heterogeneous test counts. Gold is a behavioral reference and can have defects of its own.

**Blind comparison.** Randomize anonymous patch labels using the frozen seed `362219`. Give fresh graders the requirement, anonymized patches, tests, known baseline failures and relevant evidence. Withhold identities and timing. Judge requirement coverage, regressions, security, maintainability and tests. Use *same*, *better*, *worse*, *mixed* or *uncertain* relative to the reference. Resolve material disagreements with a reproducer where possible. Acceptance authors had prior exposure to gold. Coding style can reveal authorship and public tasks may have been memorized. Historical tool-event auditing was retrospective, and unobserved channels remain unknown. [Methods and limits](https://github.com/justinthelaw/law-config/issues/71#evidence-a:~:text=historical%20partial%20report)

**Elapsed time and usage.** Pair at the task level. Aggregate the final cumulative native usage once per distinct root or reviewer and reconcile retries. Total context equals uncached input plus cached input plus output. Reasoning is a subset of output. Compute each percentage as the difference between the sums for the two arms, divided by the control sum. Coordination, grading and historical human time or usage are unavailable where the ledger says so. Context tokens are not billing figures.

**Ledger interpretation.** The CSV reproduces the 30-row public table from [Evidence F](https://github.com/justinthelaw/law-config/issues/71#evidence-f:~:text=final%20complete%2030-row%20metric%20ledger). It has 20 attempted arms and 10 gold rows. Fifteen arms have complete native usage and five have known lower bounds. Blank gold values are unknown. The two cost figures and charts use only the ten rows with `paired_eligible=True`, meaning the five historical pairs. The case manifest separately defines the final slate. Click's ambiguous pilot, both Vue attempts and unpaired FastAPI remain visible but outside the paired quality comparison.

| Historical paired subset | Control seconds | Develop seconds | Control context tokens | Develop context tokens |
| --- | ---: | ---: | ---: | ---: |
| Two selected cases | 565.510 | 733.058 | 1,443,032 | 2,247,213 |
| Three supplemental cases | 1,314.047 | 1,326.845 | 2,978,300 | 4,436,090 |
| All five completed pairs | 1,879.557 | 2,059.903 | 4,421,332 | 6,683,303 |

Across all 20 attempted arms, recorded elapsed time sums to 9,061.0 seconds and known native context usage to at least 25,060,839 tokens. These are workload totals across unequal numbers of attempted arms, including interrupted attempts. The paired table above uses completed pairs only.

## Why scoring stopped

The historical run paused for handoff after repeated service-limit errors and its scheduled restart was canceled. The continuation recovered both published archives, all 16 selected source snapshots, the frozen Develop package tree and the exact Linux CLI. Four representative Tokio role profiles passed 14 synthetic checks in each direct and descendant process. These checks established feasibility for that configuration. Other real cases still require admission.

Device sign-in was unavailable. The pinned app server initialized an ephemeral thread but reported no authenticated account. Desktop app servers used different builds. At the user's request execution stopped without a scored turn. No new quality or cost observation resulted. Missing historical diffs and a hash-referenced patch supplement limit independent regrading. [Continuation evidence](https://github.com/justinthelaw/law-config/issues/71#issuecomment-6434762307)

## Implications for Develop

- **Keep boundary tests tied to requirements.** Historical blind assessors modestly preferred Develop's Flask and Hugo regression coverage. Requests and Cobra showed mixed maintenance and test tradeoffs.
- **Instrument review costs before changing review depth.** Develop used more uncached input and output in every historical pair. A separately versioned comparison could test smaller review packets under the same quality criteria.
- **Prove each fixture measures the intended change.** Freeze independent test criteria before release. Label gold-derived regressions, preserve ambiguous attempts, and record cases where both reference versions pass.
- **Qualify a future executor with one complete matched pilot.** Verify same-account inference, role isolation, actual instruction loading and per-request usage. Preserve failures and lower bounds. Keep the three user-owned projects separate when interpreting results. [Historical recommendations](https://github.com/justinthelaw/law-config/issues/71#evidence-a:~:text=historical%20partial%20report)

## Rebuild the report

The report is an offline rendering of the adjacent CSVs. It requires Python 3.10 or newer and ReportLab 4.4.9. From the repository root, run:

```sh
uv run --no-project --with reportlab==4.4.9 python docs/evaluations/develop-benchmark/render_report.py
```

The renderer writes `report.pdf` beside its source. The issue retains the published source archives and full ledgers for verification. Neither the renderer nor the PDF launches benchmark trials.
