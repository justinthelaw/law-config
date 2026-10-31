# D matched fmt pilot

D failed its preregistered efficiency screen: it cost **8.18% more** than standalone C, although checkout-to-proposal time fell **1.24%**. D and fresh stock were both ready and tied at **96.25/100** in all three blind rotations. This exposed tuning case does not establish a panel outcome.

| Measure | D | Standalone C | Fresh stock |
| --- | ---: | ---: | ---: |
| Build / native / contract / preserve | All pass | All pass | All pass |
| Blind full PR score /100 | 96.25 | Not assessed | 96.25 |
| Checkout to proposal | 1,408.52 s | 1,426.22 s | 1,372.44 s |
| Estimated proposal USD | 0.7237960 | 0.6690920 | 0.5498268 |
| Total tokens | 4,802,702 | 4,369,362 | 3,385,855 |

All proposal meters are complete. Three valid rotations tied D and stock; both beat the merge, which scored 78.75. No critical flags were raised. Assessor cost was $0.3216552, separate from proposal costs. C's soft PR quality was not assessed.

D read the waiting example and moved most polling to the outer code cell. Its 92 outer waits cost $0.473. It requested ten seconds 86 times and one second six times. Including terminal polls, D spent $0.524 on wait-only responses, versus $0.508 for C and $0.425 for stock. [Response counts and prices](polling.json)

C and D produced identical production changes and passed the same frozen executable gates. Both reported passing all 41 `chrono_test.*` tests; Japanese and Spanish locales were unavailable, and neither reported running the broader suite. Their regression cases differ: C explicitly tested `%r` with infinity and other ordering and precision combinations; D added float, `%M`, and default-format infinity cases. Identical production changes support preservation of C's behavior, but explicit test coverage is not identical. D reported independent review and failing regressions before the fix.

The seeded order was C, fresh stock, then D. All started on GPT-6.1 Sol Medium; neither Develop arm had a companion. The registered hypothesis, acceptance criteria, package hashes, and evaluator binding were frozen before allocation. A single exposed case cannot support promotion or a full-panel conclusion.

[Portable result](result.json) · [D registration and treatment](../../../treatments/a848ecd8a72a/registration.md) · [C treatment](../../../treatments/0085f2ad8d61/treatment.json)

Verify the portable record from the repository root:

```sh
/usr/bin/python3 -B docs/evaluations/benchmark.py report lean-d-fmt-01
```
