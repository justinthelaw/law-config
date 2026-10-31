# Develop tuning

Across the first 19 pilots on six repositories, Develop met the joint quality and cost target in zero of 15 measured comparisons. Four remain unresolved. Among 14 pairs where both proposals were ready and fully metered, Develop won blind full-PR quality six times, tied four and lost four. It cost more in all 14. In the remaining measured pair, Develop beat a failed stock proposal on quality and cost more.

Choose a released pilot by name. Run `python3 -B docs/evaluations/benchmark.py status NAME` from the repository root for readiness, quality, proposal cost, tokens and time. Each `result.json` binds the proposals to their task, treatment, checks and three rotated judge assessments. [How to run and score a pilot](../../README.md)

For all validated pilots, run `python3 -B docs/evaluations/tools/records.py tuning`. The JSON separates evaluation contexts and exclusions, with the strict joint target counted independently of the ready/ready table. Repeated tasks and changed treatments remain diagnostic.

## Lean workflow pilots

The seven-skill Develop revision lost the blind Commander comparison and failed Black's public behavior check. Both cases used the same Superpowers companion in prior and lean Develop. Stock had neither plugin.

| Case and measure | Stock | Lean Develop | Prior Develop |
| --- | ---: | ---: | ---: |
| Commander full PR /100 | 96.25 | 75.00 | Unscored |
| Commander checkout to PR | 3m 16s | 6m 34s | 6m 30s |
| Commander proposal cost | $0.109 | $0.340 | $0.464 |
| Black checkout to terminal | 20m 31s, timeout | 10m 51s, blocked | 13m 14s |
| Black proposal cost | Unknown | ≥$0.570 | $1.038 |

On Commander, stock and prior Develop preserved an existing option source that lean Develop lost. Lean Develop read six Superpowers skills and two references. Its one review worker cost $0.080 and missed the regression. The actual merge scored 56.25 and preserved the existing behavior. [Pilot](lean-commander-01/result.json) · [Public API replay](lean-commander-01/evidence.json) · [Companion reads](lean-commander-01/companion-reads.json)

On Black, stock timed out without a complete PR. A descendant hook in lean Develop timed out after five seconds. The runner blocked the attempt before grading. Replaying the identical patch passed build, native and preservation checks, but a valid formatter input produced invalid Python. Prior Develop passed all four checks. The actual merge scored 86.25. Neither measured participant qualified for a full-PR comparison. [Pilot](lean-black-01/result.json) · [Hook receipts](lean-black-01/hook-evidence.json) · [Supplemental check](lean-black-01/supplemental-grade.json)

The next revision handles a verifiable local edit directly and checks a previously accepted input when extending a condition. Its historical 20-repository comparison uses standalone Develop. A separate Commander pilot isolates the optional companion. [Frozen treatment and stopping rule](../../treatments/0085f2ad8d61/historical-tuning.json) · [Native context measurements](../../treatments/0085f2ad8d61/context.json)

## Practices under test

| Source | Practice to test in Develop | Scope of the evidence |
| --- | --- | --- |
| Effect | Exercise the caller's success, expected failure and cleanup when the change affects resource ownership. Distinguish a setup error from a behavioral failure. | Effect exposes error channels and resource lifetime explicitly. [Errors](https://effect.website/docs/v4/error-management/expected-errors) · [Resource scopes](https://effect.website/docs/v4/resource-management/scope) |
| fast-check and Hypothesis | Model the observable state independently. Vary a small sequence of operations, then retain the smallest reproducer. | Both libraries support stateful tests. A deterministic finite enumeration also produces a replayable witness. [fast-check](https://fast-check.dev/docs/advanced/model-based-testing/) · [Hypothesis](https://hypothesis.readthedocs.io/en/latest/stateful.html) |
| Superpowers and Cucumber | Plan around a concrete example. Watch the relevant test fail for the expected reason, make it pass, then simplify while it stays green. Delegate independent work when appropriate. | Superpowers supplies Codex skills for planning, tests and subagents. Cucumber describes specifying behavior through examples. [Codex distribution](https://github.com/openai/plugins/tree/0722921d5542fc593105c27bd52630babd8b8c2a/plugins/superpowers) · [Cucumber](https://cucumber.io/docs/bdd/) |
| Graphify | Use a dependency path to locate a caller. Verify the edge in source or by executing the operation. | The project's code benchmark measured answers to six ERPNext questions. A PR trial would also need to count index preparation and update costs. [Graphify benchmark](https://github.com/Graphify-Labs/graphify/blob/0a8cd4e1e342235fe53e881fb5d591bf0460071f/BENCHMARKS.md) |
| Ponytail | Start with the existing representation and change the smallest owner that satisfies the caller's contract. | Its author measured 26% lower cost across tasks on Opus 5.5 with the shell disabled. Our panel gives both arms build and test tools. [Skill](https://github.com/DietrichGebert/ponytail/blob/96608e078b2d5ea607c5c3b8b5a54d1c1fba6846/skills/ponytail/SKILL.md) · [Experiment](https://github.com/DietrichGebert/ponytail/blob/96608e078b2d5ea607c5c3b8b5a54d1c1fba6846/benchmarks/results/2026-10-07-agentic.md) |
| Mutation testing | Try one plausible wrong behavior and check whether the regression test catches it. | A study of 357 real faults found an association beyond code coverage. Google restricted mutation checks to selected changes to control their cost. Our packaging replay exposed a contract choice already encoded in a test. [Fault-detection study](https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014-abstract.html) · [Google study](https://research.google/pubs/practical-mutation-testing-at-scale-a-view-from-google/) · [Packaging replay](../pr-quality-panel-v2/packaging-noop-test-conflict.json) |

## What distinguishes the proposals

In the Werkzeug tuning case, a prior Develop proposal preserved the byte position after a multibyte write. Stock, a later Develop revision and the merged PR returned a character count. Replay the same write before and after normalizing the response body. Keep this diagnostic separate from the frozen rubric. [Werkzeug proposals and caller evidence](review-entry-werkzeug-01/result.json)

In the Expat tuning case, literal parameter-entity references in comments and processing instructions must remain literal. Actual entity expansion and cycles still need their protection. The eight-case replay found two violations in the base and historical Develop, and zero in stock and the merge. Changing parser context changes the expected behavior. [Historical results and parameter-entity replay](../pr-quality-panel-v2/README.md)

With the same Superpowers installation, revised Develop passed all 144 Werkzeug stream cases. Prior Develop, stock Codex and the merge each passed 12. Stock and revised Develop tied at 81.25/100 on the full PR. Revised Develop cost $0.550 and took 7m 54s, down from $0.675 and 9m 13s for prior Develop. Stock cost $0.345 and took 7m 05s. The cost and quality criteria ruled out the conditional Expat run. [Matched proposals, scores and caller replays](observable-werkzeug-01/result.json)

Werkzeug treats deprecation warnings as errors. Revised Develop failed two of 74 consumer tests, prior Develop failed one, and stock passed its edited tests. Stock changed one test to expect a warning and another to send bytes. With the two original tests restored, all three proposals failed both. All three warned on a response containing only strings. The merge passed both tests and warned only when strings and bytes were mixed. These post-score replays leave the blind scores unchanged. [Consumer suites](observable-werkzeug-01/warning-consumer-replay.json) · [Original tests and four public inputs](observable-werkzeug-01/warning-contract-replay.json)

On Black, prior Develop submitted in 12m 19s for $0.642. The revision that requested a runnable reviewer example timed out after spending at least $1.008. Stock also timed out. The judges scored their diffs at 48.75/85 and 25/85 respectively, and the merge at 85/85. Both Develop patches passed the four frozen gates but failed the same three of five additional formatter checks. [Black proposals, scores and replays](intent-example-black-01/result.json)

On the condition-scope Werkzeug pilot, revised Develop scored 96.25 versus stock's 75 but cost $0.788 versus $0.400. Revised and prior passed 144/144 stream cases; all three proposals passed 72/74 unchanged tests, failing the registered homogeneous-string warning-preservation check. The screen rejected the treatment. The original merge remains Pending at 43.75; separate adjudication confirms removed applicable tests while four targeted runtime cases pass. [Registered assay](condition-scope-werkzeug-01/condition-scope-assay.json) · [Process audit](condition-scope-werkzeug-01/process-audit.json) · [Merged readiness ruling](condition-scope-werkzeug-01/merged-readiness-adjudication.json)

## Authored test sensitivity

On Runner Space, all three judges preferred revised Develop to stock and the merged PR. Its median lead over stock was 6.25 points, and it cost $0.708 versus $0.241. Both Develop proposals caught the old lint pins in their tests. The revised dependency ledger misstated the retained Undici version, 6.29.1, as 6.29.0. [Blind scores](owner-config-runner-space-01/result.json) · [Test replay](owner-config-runner-space-01/owner-config-authored-tests/README.md) · [Ledger evidence](owner-config-runner-space-01/ledger-assessment.json) · [Cost and time](owner-config-runner-space-01/process-audit.json)

The Runner Space base and revised proposal produced identical bundles on a matched rebuild. Both failed the repository's distribution check. The original worker produced a different bundle, so the cause remains open. [Distribution replay](owner-config-runner-space-01/distribution-replay.json)

On the sealed pytest task, Develop's seven-case subset caught stock's tuple regression; stock's ten-case suite missed it. The complete Develop suite could not collect its 15 cases under the project's strict configuration because two factories shared generated IDs. Changing only those IDs produced 15 passes; deliberately repeated IDs still blocked collection. The participant's passing command used `-c /dev/null`. These post-score checks preserve the original scores. [Authored-test sensitivity](public-result-pytest-01/authored-test-sensitivity.json)

Two draws of the same earlier Develop package preserved tuple unpacking, internal-first imports, class annotation lookup and console startup. Both matched stock proposals lost all four behaviors. Both Develop draws cost more than stock. Only the first received a blind score. [Matched proposals](public-result-pytest-01/matched-repeat.json) · [Six-source caller checks](public-result-pytest-01/external-entry-controls.json)

On the matched configured-test pilot, all three judges tied revised Develop and stock at 81.25. Revised Develop cost $0.584, down from the parent's $0.691 and above stock's $0.483. Under the project configuration, all nine revised cases and all 12 stock cases passed. Duplicate IDs blocked all 14 parent cases. All three proposals lost tuple unpacking, internal-first imports and class annotation lookup. The revised reviewer finished before the passing configured output arrived. The merge scored 30, and its PR text claimed constructor and test changes absent from its patch. [Configured tests and public callers](configured-tests-pytest-01/configured-authored-tests-postscore.json) · [Review timing](configured-tests-pytest-01/process-audit.json) · [Merge adjudication](configured-tests-pytest-01/merged-pr-adjudication.json)

All 18 proposals from the first six pytest pilots passed their five executable gates. Six crashed before collecting an unchanged test through the `pytest` command, while all 18 passed it through `python -m pytest`. The failures affected three stock, two revised Develop and one prior Develop proposal. The base and merge passed both ways. [Console startup replay](configured-tests-pytest-01/public-cli-incidence.json)

| Pytest pilot | Blind full PR, Develop / stock / merge | Proposal cost, Develop / stock | Checkout to proposal, Develop / stock |
| --- | --- | --- | --- |
| Declared entry | 100 / 100 / 30 | $0.864 / $0.735 | 14m 33s / 8m 51s |
| External caller | 96.25 / 20 / 30 | $0.520 / $0.383 | 10m 50s / 8m 54s |

In the declared-entry pilot, both proposals passed five gates. Prior Develop cost $1.092, took 17m 03s and failed console startup. It passed nine focused tests through the module entry point but could not collect them through the callable declared by the checkout. Revised Develop ran the same 298 cases with identical outcomes through both routes. The bundled launcher pointed to an older entry point. [Blind scores and caller checks](declared-entry-pytest-01/result.json) · [Timing](declared-entry-pytest-01/process-audit.json) · [Launcher replay](declared-entry-pytest-01/entrypoint-replay.json)

In the external-caller pilot, revised Develop kept the tuple representation and passed all five gates. Stock and prior Develop replaced it with a dataclass and failed console startup. All three judges preferred revised Develop to both stock and the merge. Prior Develop cost $0.717 and took 13m 10s. The producer tested the original tuple behavior before editing. Its final reviewer finished before the configured tests, and only the assessor verified the declared entry. [Results](external-entry-pytest-01/result.json) · [Cost and timing](external-entry-pytest-01/process-audit.json) · [Producer evidence](external-entry-pytest-01/external-entry-uptake/)

On the exposed Go-git task, a post-score replay found that revised Develop masks a read error as malformed input when an invalid mode byte and an I/O error arrive together. Base, merge, prior Develop and stock preserve the error in that case; ordinary malformed and valid controls behave alike. This is an observed error-identity change, with production incidence unknown, and leaves scores unchanged. [Error precedence witness](intent-go-git-01/error-precedence-witness.json)

On the partial-result Go-git pilot, revised Develop tied stock and the merge at 96.25, costing $0.631 versus stock's $0.600. A separate witness found stock lost a read error that both Develop patches preserved. The prior proposal timed out; exact parent savings and a distinct treatment mechanism remain unestablished. [Results](partial-result-go-git-01/result.json) · [Witness](partial-result-go-git-01/partial-result-identity/supplement.json) · [Process audit](partial-result-go-git-01/process-audit.json)
