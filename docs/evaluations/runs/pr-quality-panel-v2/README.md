# Twenty-repository PR benchmark

Develop and the historical Codex control each delivered 15 ready proposals across 20 repositories. The merged changes produced 17. Develop cost more and took longer on the comparable pairs. Both arms used GPT-6.1 Sol Medium. Three plugin-free judges assessed each repository with rotated positions. [Run manifest](baseline-53a8bd549c93/run.json) · [60 submission records](baseline-53a8bd549c93/submissions.jsonl)

"Pure" labels the historical control in the tables below. All 20 primary control inventories and all five recovery inventories recorded zero plugins and MCP servers. They lack the app, global-instruction and exact-turn receipts used to verify stock Codex in the newer trials.

## Primary results

| Measure | Pure Codex | Develop | Merged PR | Denominator |
| --- | ---: | ---: | ---: | --- |
| Ready proposals | 15 | 15 | 17 | 20 each |
| Failed / unavailable | 3 / 2 | 2 / 3 | 3 / 0 | 20 each |
| Estimated proposal cost | $4.79 | $8.18 | Unknown | 14 completely metered pairs |
| Total tokens | 23.67M | 40.25M | Unknown | Same 14 pairs |
| Checkout-to-proposal time, summed | 2h 24m | 3h 19m | Unknown | 15 completed pairs |
| Checkout through independent grading, summed | 2h 32m | 3h 27m | Unknown | Same 15 pairs |

The frozen rubric gave Develop 2 wins, 4 losses and 9 ties. Five comparisons were unresolved. Its only win at lower cost was maximize-github-runner-space ($0.37545 vs. $0.37638, 25 seconds slower). The control failed on a wrapped Markdown line. A checker that reads the whole ledger entry accepts both proposals, and the judges saw the original failure. No completely measured pair favored Develop on quality, cost and time together. Packaging/Develop delivered a ready proposal despite a capacity error. Incomplete metering excludes its cost from the paired total. [Runner-space replay](#cases-that-distinguish-the-workflows)

Compared with pure Codex, Develop cost 1.71× as much (95% repository-bootstrap interval 1.41–2.04), used 1.70× the tokens (1.43–2.02) and took 1.38× as long (1.17–1.71). The 60 judge calls cost an estimated $8.10 separately. The campaign took 10h 23m from freeze through the last assessment, including service interruptions.

| Paired diff comparison | Pairs | Mean delta /85 | 95% bootstrap interval | Higher / equal / lower | Position reversals |
| --- | ---: | ---: | --- | ---: | ---: |
| Develop vs pure | 15 | -4.25 | -12.25 to +3.17 | 2 / 9 / 4 | 0 |
| Develop vs merge | 17 | +11.69 | +3.75 to +19.34 | 13 / 1 / 3 | 1 |
| Pure vs merge | 18 | +16.11 | +5.07 to +26.81 | 15 / 1 / 2 | 0 |

Against the merge, Develop won 13 full-proposal verdicts, lost 3, tied 1 and had 3 unresolved. Pure Codex won 13, lost 3, tied 1, had 2 unresolved and failed alongside the merge once. The full-proposal mean difference between Develop and pure Codex was −4.83/100 (95% interval −13.58 to +3.50).

Thirteen ready controls left less than the required five-point margin for a perfect proposal. Six scored 100 at the median rotation and seven scored 96.25. Two other ready controls left room on the rubric, three failed a hard gate and two had incomplete evidence. These bounds apply to these recorded proposals.

## Diff scores by repository

Contract and compatibility contribute 35 points, tests 25, and design and scope 25. PR communication contributes the remaining 15 points to the full-proposal comparison. Each displayed code score uses the three median axis anchors. The paired deltas above use the median difference within each rotation. An executable failure or confirmed critical defect takes precedence over the score. A partial score describes a patch captured from an interrupted attempt and is excluded from paired comparisons. [Scoring rubric](../../develop-benchmark/panel/rubric.md)

| Upstream PR | Split | Pure /85 | Develop /85 | Merge /85 | Develop vs pure proposal |
| --- | --- | ---: | ---: | ---: | --- |
| [BurntSushi/ripgrep #3578](https://github.com/BurntSushi/ripgrep/pull/3578) | tuning | 85 | 85 | 72.5 | Tie |
| [fmtlib/fmt #4981](https://github.com/fmtlib/fmt/pull/4981) | tuning | 85 | 85 | 78.75 | Tie |
| [go-git/go-git #2538](https://github.com/go-git/go-git/pull/2538) | tuning | 85 | 85 | 85 | Tie |
| [jqlang/jq #3694](https://github.com/jqlang/jq/pull/3694) | tuning | 85 | 37.5 partial | 78.75 | Unresolved |
| [justinthelaw/maximize-github-runner-space #69](https://github.com/justinthelaw/maximize-github-runner-space/pull/69) | tuning | 61.25 fail | 70 | 60 | Develop |
| [libexpat/libexpat #1439](https://github.com/libexpat/libexpat/pull/1439) | tuning | 85 | 61.25 | 45 | Pure |
| [markedjs/marked #4145](https://github.com/markedjs/marked/pull/4145) | tuning | 48.75 fail | 55 partial | 42.5 fail | Unresolved |
| [pallets/werkzeug #3325](https://github.com/pallets/werkzeug/pull/3325) | tuning | 85 | 63.75 | 36.25 | Pure |
| [psf/black #5620](https://github.com/psf/black/pull/5620) | tuning | 25 fail | 55 | 70 | Develop |
| [pypa/packaging #1457](https://github.com/pypa/packaging/pull/1457) | tuning | 85 | 85 | 42.5 fail | Tie |
| [pytest-dev/pytest #15193](https://github.com/pytest-dev/pytest/pull/15193) | tuning | 85 | 48.75 | 30 fail | Pure |
| [tj/commander.js #2653](https://github.com/tj/commander.js/pull/2653) | tuning | 85 | 85 | 48.75 | Tie |
| [apache/commons-lang #1840](https://github.com/apache/commons-lang/pull/1840) | confirmation | 78.75 | 78.75 | 48.75 | Tie |
| [CLIUtils/CLI11 #1479](https://github.com/CLIUtils/CLI11/pull/1479) | confirmation | 85 | 85 | 72.5 | Tie |
| [django/django #22169](https://github.com/django/django/pull/22169) | confirmation | 42.5 | 31.25 partial | 63.75 | Unresolved |
| [libarchive/libarchive #3737](https://github.com/libarchive/libarchive/pull/3737) | confirmation | 85 partial | 48.75 fail | 78.75 | Unresolved |
| [prometheus/client_golang #2182](https://github.com/prometheus/client_golang/pull/2182) | confirmation | 85 | 85 | 78.75 | Tie |
| [rspec/rspec #353](https://github.com/rspec/rspec/pull/353) | confirmation | 85 | 85 | 72.5 | Tie |
| [sharkdp/fd #2196](https://github.com/sharkdp/fd/pull/2196) | confirmation | 85 partial | 85 | 78.75 | Unresolved |
| [sympy/sympy #30827](https://github.com/sympy/sympy/pull/30827) | confirmation | 85 | 55 fail | 57.5 | Pure |

## Cases that distinguish the workflows

- **Black.** Develop and the merge preserve a valid parenthesized `with` containing `fmt: skip`. Pure emits a standalone `with` that fails to parse. The merge scored 70/85 against Develop's 55/85.
- **fmt.** A [bounded sign-property assay](fmt-sign-property.json) detects both original regressions with fewer assertion lines, without establishing full test equivalence or lower PR cost.
- **pytest and Werkzeug.** Pure preserves `pytest.param()` tuple unpacking and reports a two-byte UTF-8 stream position after writing `ö`. Develop raises `TypeError` on tuple unpacking and returns a stream position of one. The original pytest implementation preserves unpacking but its merged change fails the direct-constructor warning contract.
- **Expat and Commander.** Pure and the Expat merge accept a valid parameter-entity comment that Develop rejects for amplification. All three reject genuine recursion. In Commander, both model patches return the parent's unknown option source in property-storage mode. The merge incorrectly returns the child's CLI source.
- **Runner Space.** The frozen checker rejects pure Codex's line-wrapped dependency ledger entry. A logical-entry checker accepts both proposals and the merge while continuing to reject the base. Holding the original votes fixed, Develop still leads by 8.75/100. Those judges saw the frozen grade. An [assertion replay](runner-space-owner-check.json) finds Develop's added test rejects an empty environment mapping while existing selectors preserve the pin checks.
- **libarchive and SymPy.** Develop's libarchive change passes the frozen Linux stages, but MinGW-target preprocessing rejects its two-argument call to a three-argument Windows macro. In SymPy, the frozen preservation gate rejects Develop's handling of tuple point inputs. Both were confirmation cases.
- **Packaging.** The merge fails equivalent-set identity and accepts invalid arguments that both proposals reject. Both proposals discard a nested prerelease policy change that alters batch filtering. A small change preserves both the required identity and the changed filter, but fails a test Develop wrote to require the opposite nested-policy behavior. The original task leaves that choice open. [Batch-filter replay](packaging-noop-replay.json) · [Conflicting test and exact results](packaging-noop-test-conflict.json)
- **Marked.** Every captured tree passed all 132 bundled emphasis examples. On 3,648 short inputs where two bundled parsers agreed, the merge produced 61 mismatches, recovery Codex 27 and recovery Develop 24. [Executable replay and per-tree results](marked-delimiter-replay.json)

## Fresh pairs after service interruptions

Five primary proposals stopped at provider capacity. Each affected repository received two fresh proposals and three fresh assessments under the original controls. All ten proposals finished and all 15 assessments were valid. This cohort selected cases by a prior terminal stop and has its own denominator. [Recovery manifest](capacity-recovery-10864a781080/run.json) · [15 submission records](capacity-recovery-10864a781080/submissions.jsonl)

| Repository | Diff /85, pure · Develop · merge | Develop vs pure PR | Estimated USD, pure · Develop | Tokens (M), pure · Develop | Time (m:ss), pure · Develop |
| --- | --- | --- | ---: | ---: | ---: |
| libarchive | 48.75 · 63.75 · 78.75 | Develop | 2.15 · 0.47 | 11.81 · 2.29 | 85:05 · 14:46 |
| Marked | 48.75 · 48.75 · 42.5 | Both failed | 0.89 · 0.59 | 4.38 · 2.85 | 17:51 · 16:29 |
| Django | 48.75 · 48.75 · 63.75 | Tie | 0.35 · 0.40 | 1.57 · 1.76 | 10:01 · 13:32 |
| fd | 85 · 85 · 78.75 | Tie | 1.09 · 0.93 | 7.05 · 5.55 | 69:51 · 49:40 |
| jq | 85 · 85 · 78.75 | Tie | 1.21 · 1.25 | 7.80 · 8.07 | 66:51 · 67:24 |

Develop, pure Codex and the merges produced 4, 3 and 4 ready proposals. Develop beat pure on libarchive, tied on three cases and failed alongside pure on Marked. Against the merge, Develop won fd and jq, lost libarchive and Django, and both failed Marked. The mean paired Develop advantage over pure was +4.25/85 on the diff (95% repository-bootstrap interval 0 to +12.75) and +3.00/100 on the full PR (0 to +9.00). Only libarchive had a nonzero paired diff advantage.

All five pairs had complete metering. Pure and Develop cost $5.68 and $3.64, used 32.61M and 20.52M tokens, and took 4h 10m and 2h 42m in summed checkout-to-proposal time. Including independent grading, the times were 4h 16m and 2h 49m. The Develop-to-pure ratios were 0.640 for cost (95% interval 0.349–1.003), 0.629 for tokens (0.322–0.982) and 0.648 for checkout-to-proposal time (0.321–1.040).

Develop combined equal-or-better proposal quality, lower cost and shorter time on libarchive and fd. Only fd also beat the merge. Libarchive accounted for $1.67 of the $2.04 in estimated savings. The recovery campaign took 2h 52m through the last assessment. Its assessors cost an additional $1.79.

- **libarchive.** Two judges flagged pure Codex's two-argument `fcntl` call. A Windows-target preprocessing replay confirms that the platform header requires three arguments. The base, merge and fresh Develop patch pass the same probe. In the primary run, Develop had the equivalent defect.
- **Marked.** Both proposals failed the same three mandatory delimiter cases. Two independent parsers agree on the expected outputs for all three. They differ on a separate emoji input that both proposals passed. [CommonMark emphasis rules](https://spec.commonmark.org/0.31.2/#emphasis-and-strong-emphasis)
- **Django.** Both proposals passed the frozen gates. In a separate SQLite replay, their negated XOR query used an inner join and dropped a row with a missing related object. The merge used a left outer join and returned the expected row. [Replay, SQL and patch hashes](django-recovery-diagnostic.json)

## What to test next

Test one plugin change at a time. Each hypothesis names the target files, tuning cases, predicted outcomes and rejection criteria. [Machine-readable hypotheses](tuning.json) The first candidate reuses a reviewed intent contract when scope is unchanged. On go-git, four child reviews cost about $0.234, while the Develop coordinator alone cost $0.955 versus $0.452 for the entire pure run. The second candidate asks for one executable public-boundary example when a representation or context changes. pytest, Werkzeug and Expat provide distinguishable cases.

The twelve tuning repositories and eight confirmation repositories were assigned before release. All are now exposed. A promotion claim needs fresh confirmation tasks. Each primary arm has one sample per repository, so the bootstrap describes variation across repositories and does not measure run-to-run model variance. Rate-card estimates use observed root and child counters. Open-to-merge time includes queues and review, and the historical submissions do not reveal author labor or spend.

The pinned PRs' first commits fall between October 9 and 26, 2026. Training-set membership and upstream authors' use of AI assistance are unknown. Both cohorts used the 205-file Develop package `c619be0cc266`. The cleaned 104-file package installed with ten enabled Develop skills and two trusted plugin hooks. It needs its own named campaign to measure its effect. [Measured treatment](../../treatments/c619be0cc266/recipe.json) · [Cleaned treatment](../../treatments/579bba8e795d/recipe.json) · [Native installation receipt](../../treatments/579bba8e795d/installation.json)
