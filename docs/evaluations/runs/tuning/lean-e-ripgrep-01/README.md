# E ripgrep transfer screen

E failed the preregistered screen: it cost **21.1% more** than D and produced **54 poll-only responses** versus D's 34. E and fresh stock were ready and tied at **100/100** in all three blind rotations. This exposed case is an efficiency and transfer screen, not a panel result.

| Measure | E | D | Fresh stock |
| --- | ---: | ---: | ---: |
| Build / native / contract / preserve | All pass | All pass | All pass |
| Blind full PR score /100 | 100 | Not assessed | 100 |
| Checkout to proposal | 680.04 s | 623.23 s | 615.97 s |
| Estimated proposal USD | 0.3756912 | 0.3102656 | 0.3332292 |
| Total tokens | 2,238,020 | 1,700,700 | 1,844,969 |
| Proven poll-only responses | 54 | 34 | 40 |

All proposal meters are complete. All three blind rotations tied E with stock, and both beat the merge at 83.75. No critical flags were raised. Assessor cost was $0.2633096, separate from proposals. Four qualification probes passed; their observed token counters estimate $0.1239248 using the frozen rates, but the probe records do not claim complete cost coverage. D's soft PR score was not assessed.

The [frozen counter](waits.json) counts only proven, exclusively polling model responses, including descendants. Ownership ambiguity was zero. D had 17 unproven-or-work responses, so even counting all of them as polling gives 51, below E's proven 54. The estimated polling-response costs are $0.2411444 for E, $0.1678320 for D and $0.2148980 for stock. These are classifications, not estimates of avoidable cost.

Both Develop attempts read their respective skills, ran a failing focused regression before the fix, then passed the 193-test `ignore` library suite and offline build. Both reported `git diff --check`; rustfmt was unavailable. Their production edits were identical, but D's regression also explicitly covered nested child paths and a walk starting at the containing tree, which E's added test did not. The gates do not establish identical explicit coverage.

E did not use the prescribed 300000 ms waits. It started checks with 1-second yields and repeatedly polled. D's reported Rust compilation phases were 4m 32s for the cold focused test, 1m 29s for the post-fix test and 1m 16s for the dev build. E's corresponding phases were 4m 46s, 1m 41s and 1m 31s, with build and test ordered differently. These phases account for much of the observed wall-time difference without establishing its cause.

The seeded order was D, E, then stock. Each started on GPT-6.1 Sol Medium with the same native task, resources, graders and frozen rates. Neither Develop arm had a companion. The screen and its criteria were registered before allocation. E is ineligible for the conditional historical 20-case run on this result.

[Portable result](result.json) · [Registration and hypothesis](../../../treatments/37296eded675/registration.md) · [Counter binding](../../../treatments/37296eded675/wait-counter.json)

Verify the portable record from the repository root:

```sh
/usr/bin/python3 -B docs/evaluations/benchmark.py report lean-e-ripgrep-01
```
