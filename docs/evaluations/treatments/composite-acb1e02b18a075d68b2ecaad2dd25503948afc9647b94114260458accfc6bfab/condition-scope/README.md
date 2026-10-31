# Werkzeug condition-scope replay

Replay a sealed pilot from the repository root:

```sh
export OAIPKG_DISABLE_META_MISSING=1 PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 -B docs/evaluations/treatments/composite-acb1e02b18a075d68b2ecaad2dd25503948afc9647b94114260458accfc6bfab/condition-scope/replay.py docs/evaluations/runs/tuning/observable-werkzeug-01/result.json historical
```

For another sealed result, replace the result path and use a new name. The command verifies the frozen inputs and original base test bytes, reconstructs the positive control, then replays the stream and warning probes, two original consumers and both full original modules. It prints the new workspace and output directories. Outputs are diagnostic and do not change pilot scores.

Prepare the [native panel runtime](../../../develop-benchmark/panel/README.md#prepare-the-host) first, including the pinned Werkzeug objects, dependencies and Docker image. CPUs 0 and 1 must be available. The existing assessor uses `tmp/pr-quality-panel` for cache and temporary state; Docker manages image layers. Keep the fixtures out of participant workspaces.

After the historical replay, set `WORKSPACE` to the printed workspace and run this calibration check:

```sh
WORKSPACE="<printed replay workspace>"
cd "$WORKSPACE"
check=docs/evaluations/treatments/composite-acb1e02b18a075d68b2ecaad2dd25503948afc9647b94114260458accfc6bfab/condition-scope/checker
out=tmp/pr-quality-panel/condition-scope-measure
/usr/bin/python3 -B "$check/decision_check.py" \
  --target docs/evaluations/runs/tuning/observable-werkzeug-01/result.json \
  --descriptor docs/evaluations/treatments/composite-7ed91df07062b0a88cab8cd5b5e74ee8a7c7e258afa2a42645b60e793ea68791/hypothesis.json \
  --expect "$check/historical-decision-expect.json" \
  --expect-sha256 91f03b8c05912ccbddf1bd242b070ca98d9f18c0c9015fc3a3874985f79f3405 \
  --policy "$check/decision-policy-bound.json" \
  --v2 "$out/historical-assessed.json" --modules "$out/historical-modules.json" \
  --behavior "$out/historical-replay.json" --output "$out/historical-decision.json"
cat "$out/historical-decision.json"
```

For a new pilot, replace the historical target, descriptor and expectation with the sealed result, its preregistered hypothesis, and a trusted expectation built from the actual frozen plans and registration plus the exact post-score result hash. The expectation uses the same fields as the packaged example: name, registration hash, treatment identities, case, base, merge, prompt hash, target hash and descriptor hash. Supply its SHA-256 and the three replay outputs for that run. The checker reports mechanical criteria only; chronology, required review and confirmation need separate evidence.
