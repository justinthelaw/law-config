"""Check the benchmark catalog and the marketplace package boundary."""
import argparse
import json
from pathlib import Path

EVALS = Path(__file__).resolve().parents[1]


def check_layout(checkout, evals=EVALS):
    catalog = json.loads((evals / "catalog.json").read_text())
    marketplace = json.loads((checkout / ".agents/plugins/marketplace.json").read_text())
    source, = [p["source"] for p in marketplace["plugins"] if p["name"] == "develop"]
    package = checkout / catalog["package_root"]
    if (source != {"source": "local", "path": "./plugins/develop"} or
            package != checkout / "plugins/develop" or package.resolve(strict=True) != package):
        raise ValueError("Develop must install from the repository's plugins/develop directory")
    if evals.is_relative_to(package) or package.is_relative_to(evals):
        raise ValueError("the eval root and installed package overlap")

    for path in sorted(package.rglob("*")):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(package):
            raise ValueError(f"package link escapes its root: {path.relative_to(package)}")
        if path.name in {"evaluations", "evals", "benchmarks", "evaluation.py", "compare_evaluations.py"}:
            raise ValueError(f"evaluator assets in package: {path.relative_to(package)}")

    if (evals / catalog["operator"]).resolve(strict=True) != evals / "benchmark.py":
        raise ValueError("the catalog must point to the public benchmark operator")
    if not (evals / catalog["current_treatment"]).resolve(strict=True).is_relative_to(evals / "treatments"):
        raise ValueError("the current treatment lock must be under the evaluation treatments directory")
    if not (evals / catalog["artifact_root"]).resolve(strict=True).is_relative_to(evals):
        raise ValueError("record directory escapes the eval root")
    ids = set()
    for protocol in catalog["protocols"]:
        if protocol["id"] in ids:
            raise ValueError(f"duplicate protocol: {protocol['id']}")
        ids.add(protocol["id"])
        for field in ("guide", "cases", "results", "environment", "record_schema", "rubric", "readout", "tuning_hypotheses"):
            if field in protocol and not (evals / protocol[field]).resolve(strict=True).is_relative_to(evals):
                raise ValueError(f"{protocol['id']}.{field} escapes the eval root")
    return len(ids)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=EVALS.parents[1])
    args = parser.parse_args()
    count = check_layout(args.checkout.resolve())
    print(f"Verified {count} benchmark protocols and the Develop marketplace package boundary")
