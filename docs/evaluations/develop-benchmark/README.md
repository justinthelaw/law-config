# Develop benchmark

[Read the illustrated report](report.pdf) · [Frozen case manifest](cases.csv) · [Historical ledger](ledger.csv) · [New scored trials](replication/README.md)

**Develop completed zero tasks that Control missed.** Given the same starting code, task and model, `gpt-6.1-sol`, both arms passed Svelte, law-config and Tokio. Both failed fmt and runner-space. Personal site remained unresolved for both. Of the four tasks with recovered tests, each arm passed 2/4 (50%). With replacement tests, each passed 1/2 (50%). The observed change in verified completion was **0 percentage points in each group**. Each task ran once per arm. [Frozen grades and usage](replication/results.json)

## Scored source-packet trials

**How much of the implementation worked?** Base is the code before the change. Gold is the merged human PR. Each row uses that task's own acceptance evidence. A failed build leaves runtime behavior unmeasured.

| Task | Starting code | Control | Develop | Gold | What the model delivered |
| --- | --- | --- | --- | --- | --- |
| **Recovered fixtures** | | | | | |
| fmt · External | 5/13 | 7/13 | 7/13 | 13/13 | **Partial, failed overall.** Both fixed direct null formatting and conversion to a string. Both recovered 2 of the 8 missing checks. The other six paths still crashed, including surrounding text, bounded output and size calculation. |
| Svelte · External | 0/2 | 2/2 | 2/2 | 2/2 | **Passed.** Both kept speculative fork state out of reactive observations. The two distinguishing tests exercise one gold-derived regression in two rendering modes. The eight independent checks already passed on base. |
| law-config · User-owned | 2/7 | 7/7 | 7/7 | 7/7 | **Passed.** Both recovered all five missing SQLite contention scenarios, including default behavior, bounded retry exhaustion and recovery after lock release. |
| Personal site · User-owned | 0/5 browsers | 3/5 | 3/5 | 3/5 | **Unresolved.** Both restored controls in Chromium, Firefox and Mobile Chrome. Across 15 primary outcomes, each matched gold's 13 passes and two cross-origin failures. Both submitted-test stages timed out at 420 seconds. |
| **Replacement fixtures** | | | | | |
| Tokio · External | API missing | 4/4 | 4/4 | 4/4 | **Passed.** Both added exclusive mutable access to the stored value, passed four new runtime checks and all 26 existing tests, and rejected a shared borrow. Base could not compile the new API probe. |
| Runner-space · User-owned | 4/11 | Build failed | Build failed | 11/11 | **Failed before runtime.** Both patches failed compilation. Whether they protected a replaced target or detected incomplete removal remains unknown. |

The arms reached the same measured behavior on the five tasks that ran behavioral checks. Runner-space yielded no runtime comparison. These counts describe what the benchmark verified. They do not measure the fraction of a repository's total functionality implemented. [Requirements and gold PRs](cases.csv) · [Base and gold calibration](replication/qualifications.json) · [Check-by-check observations](replication/observations.json)

**Where did quality differ?** Blind correctness tied on all six tasks. Blind maintainability tied on five. On the personal site, the reviewer preferred Control's tests for child-initiated navigation, cleanup of an inaccessible frame and restored keyboard ownership. Develop separated host and frame subscriptions and guarded focus callbacks against stale documents. The preference came from reading the patches. On runner-space, both primary builds failed on an unused import. Logs checked after blind review showed four additional type errors in Develop's test code. [Blind judgments](replication/blind-judgments.json) · [Submitted patches](replication/candidates/) · [Compiler observations](replication/observations.json)

**What did it cost to reach those outcomes?** Develop finished sooner on three tasks and used more total tokens on all six. Time covers implementation and reviews. Total tokens include cached input. Billed dollars were unavailable.

| New fixture group | Control passed | Develop passed | Develop elapsed time | Develop total tokens |
| --- | ---: | ---: | ---: | ---: |
| Recovered · 4 tasks | 2/4 | 2/4 | 3.8% slower | 23.5% more |
| Replacement · 2 tasks | 1/2 | 1/2 | 2.9% slower | 25.7% more |

The earlier experiment let agents use repository tools. Both arms passed all five completed historical pairs. Only Requests and Cobra counted toward the frozen eight-case slate. Reviewers modestly preferred Develop's Flask and Hugo regression tests. No historical pair demonstrated better production behavior with Develop. Across the five pairs, Develop took 9.6% more time and used 51.2% more total context. Roux chose that setup and interpreted the historical results. [Historical assessments](https://github.com/justinthelaw/law-config/issues/71#evidence-g:~:text=final%20selected%20sources) · [New trial method and per-call usage](replication/README.md)

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

## Historical execution and isolation

1. **Freeze the inputs.** Use Codex CLI 0.159.2, executable SHA-256 `1748767b230ebfc3d4ab7e4e254920d0c0ad9691fd8c11f190e7d44511a4a92e`, with `gpt-6.1-sol` at medium effort. The exact provider model revision was unavailable. Develop 0.9.0 is commit `cd316824048d03e8ca1cefdf5d63a71b2f5b3021`, package tree `489905e4f5b9d931cdcde93a38450154a0feb801`. Freeze requirements, role prompts, verification code, toolchain and dependency identities before release. [Archive receipt and runbook](https://github.com/justinthelaw/law-config/issues/71#evidence-h:~:text=independent%20payload%20receipt)
2. **Separate evaluator and worker material.** Keep gold, hidden tests, upstream history and arm mapping in evaluator storage. Give each arm its own clean base snapshot with one synthetic commit, no upstream history or remotes, applicable repository guidance, and matched offline dependencies. Strip PR links, solution hints and patch content from worker prompts. Public downloads are preparation-only. Run base and gold checks offline and record any shared failure, nondiscriminating fixture or missing prerequisite.
3. **Isolate both arms and their descendants.** Restrict tools to the case workspace and role-specific scratch. Make toolchains read-only. Deny worker-command network access, sibling work, evaluator material and authentication paths. Develop receives the frozen instructions. Control must be unable to discover or read the package. Keep provider inference on a supported authenticated transport outside worker commands. Check direct and descendant processes, relative paths, symlinks, and process-filesystem escape paths. Historical reviewers could create new top-level entries in their own arm, a recorded limitation.
4. **Match execution.** Release fresh arms serially in the order above. Give each two CPUs, the same model, wall limit and tool access apart from Develop. Each arm in the five completed pairs had an implementation root, two planning reviewers and two final-evidence reviewers. Both arms used this review process, with up to three rounds per checkpoint. Start the clock before instruction loading and planning. Include reviews, waiting and repairs through final artifact receipt or enforced termination. Account for setup and grading separately.
5. **Retain all outcomes.** Stop at the first service-limit error, failed release gate or frozen deadline. Retain partial work and unknown usage. A resource-invalid attempt can receive at most one fresh complete-pair retry under the declared rules. fmt and law-config each have one left. Vue consumed its retry. Never pair a new arm with a surviving arm from an invalid attempt or replace cases after seeing quality outcomes. [Failures and deviations](https://github.com/justinthelaw/law-config/issues/71#evidence-d:~:text=preparation%20history)

To reconstruct a fixture, decode the harness and three-part selected-case archive from Evidence H into evaluator-only storage. Verify SHA-256 `3c104cb36a0341c253c238fcc761268ec2a1ff180ed645ff3084791baaca3e1f` for the harness and `1d0f71c4c4c313a01d8d5232f17792769dfceef4797a627520ab5284aa7c4344` for the selected cases. Inspect archive paths before extraction, verify the 178 manifest entries, then rebuild only that arm's allowed inputs. Prepare one case at a time, check free storage and preserve the 1 GiB reserve. Record relocated paths, effective configuration hashes, loaded instructions and usage coverage. Treat a changed environment as a versioned replication. [Payload receipt and reconstruction procedure](https://github.com/justinthelaw/law-config/issues/71#evidence-h:~:text=independent%20payload%20receipt)

## Historical measurements

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

## Why the historical run stopped

The historical run paused for handoff after repeated service-limit errors and its scheduled restart was canceled. The first recovery effort found both published archives, all 16 selected source snapshots, the frozen Develop package tree and the exact Linux CLI. Four representative Tokio role profiles passed 14 synthetic checks in each direct and descendant process. These checks established feasibility for that configuration.

Device sign-in was unavailable. The pinned app server initialized an ephemeral thread but reported no authenticated account. The first recovery attempt ended before scoring. A later signed-in executor passed 224 boundary checks, but its process launcher could not start the nested execution environment. The new trials above used the separately qualified source-packet protocol. Missing historical diffs and a hash-referenced patch supplement still limit independent regrading of the October 26 results. [First recovery receipt](https://github.com/justinthelaw/law-config/issues/71#issuecomment-6434762307) · [Subsequent protocol and results](replication/README.md)

## Implications for Develop

- **Keep boundary tests tied to requirements.** Historical blind assessors modestly preferred Develop's Flask and Hugo regression coverage. Requests and Cobra showed mixed maintenance and test tradeoffs.
- **Instrument review costs before changing review depth.** Develop used more uncached input and output in every historical pair. A separately versioned comparison could test smaller review packets under the same quality criteria.
- **Test one compiler-feedback step.** Both runner-space patches left the same unused import, and Develop's new test also failed type checking. On fresh tasks, give both arms one identical compiler run and one bounded repair. Count how often the code builds, how many behavioral checks pass, and the time and tokens that repair adds. [Compiler diagnostics](replication/observations.json)
- **Test whether reviews trace all affected entry points.** Both fmt patches improved direct null-pointer formatting but still crashed on surrounding literals and bounded output. Compare the current review prompt with a shorter one that asks which other public formatting paths share the changed code. Freeze those probes before running the comparison. [fmt results](replication/results.json)
- **Prove each fixture measures the intended change.** Freeze independent test criteria before release. Label gold-derived regressions, preserve ambiguous attempts, and record cases where both reference versions pass.
- **Qualify a future executor with one complete matched pilot.** Verify same-account inference, role isolation, actual instruction loading and per-request usage. Preserve failures and lower bounds. Keep the three user-owned projects separate when interpreting results. [Historical recommendations](https://github.com/justinthelaw/law-config/issues/71#evidence-a:~:text=historical%20partial%20report)

## Rebuild the report

The report renders the historical CSVs and the continuation results in the replication directory offline. It requires Python 3.10 or newer and ReportLab 4.4.9. From the repository root, run:

```sh
uv run --no-project --with reportlab==4.4.9 python docs/evaluations/develop-benchmark/render_report.py
```

The renderer writes `report.pdf` beside its source. The issue retains the published source archives and full ledgers for verification. Neither the renderer nor the PDF launches benchmark trials.
