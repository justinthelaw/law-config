"""Report the three code axes from a finished panel, independently of PR prose."""
import argparse
import csv
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "panel"))
import results as R

AXES = {k: R.J.AXES[k] for k in ("contract", "tests", "design")}
MAX_POINTS = sum(AXES.values())


def points(scores):
    if any(scores[k] is None for k in AXES):
        return None
    return sum(weight * scores[k] / 4 for k, weight in AXES.items())


def diff(row):
    review = row["review"]
    rotations = {j["rotation"]: points(j["scores"]) for j in review["judgments"]}
    full = set(rotations) == {0, 1, 2} and all(s is not None for s in rotations.values())
    return {"axes": review["axes"], "points": points(review["axes"]) if full else None, "rotations": rotations}


def compare(case, first, second):
    if any(case[role]["state"] not in ("completed", "merged") for role in (first, second)):
        return None
    left, right = (diff(case[role]) for role in (first, second))
    if left["points"] is None or right["points"] is None:
        return None
    differences = [left["rotations"][i] - right["rotations"][i] for i in range(3)]
    return {"delta": statistics.median(differences), "reversal": min(differences) < 0 < max(differences)}


def render(name):
    root = R.C.run_dir(name)
    target = root / "report"
    rows = R.E.read(target / "results.json")["cases"]
    lines = ["# Diff quality", "",
        "Contract and compatibility contribute 35 points, regression protection 25, and design and scope 25. "
        "Each displayed score uses the median anchor on each axis and requires three rotations with all three code axes scored. "
        "The PR communication score is separate. A hard failure vetoes readiness regardless of the score. "
        "An interrupted patch can be inspected but is excluded from matched comparisons.", "",
        "| Repository | Pure /85 | Develop /85 | Merge /85 | Develop − pure, median paired points | Reversal |",
        "| --- | ---: | ---: | ---: | ---: | --- |"]
    def fmt(value):
        return "—" if value is None else f"{value:.2f}"
    with (target / "diff-quality.csv").open("w", newline="") as summary, (target / "diff-evidence.csv").open("w", newline="") as evidence:
        summary_csv, evidence_csv = csv.writer(summary), csv.writer(evidence)
        summary_csv.writerow(["repository", "pr", "role", "state", "readiness", "hard_gates", "judges", *AXES,
                              "diff_points_of_85", "min_rotation", "max_rotation", "pr_communication_anchor", "proposal_points_of_100"])
        evidence_csv.writerow(["repository", "role", "rotation", "position", "axis", "anchor", "cited_evidence"])
        for case in rows:
            scores = []
            for role in R.ROLES:
                row = case[role]
                score = diff(row)
                scores.append(fmt(score["points"]))
                known = [x for x in score["rotations"].values() if x is not None]
                summary_csv.writerow([case["repo"], case["pr"], role, row["state"], row["status"],
                    row["executable_pass"], len(score["rotations"]), *(score["axes"][k] for k in AXES),
                    score["points"], min(known, default=None), max(known, default=None), score["axes"]["proposal"], row["review"]["score"]])
                for j in row["review"]["judgments"]:
                    for axis in AXES:
                        evidence_csv.writerow([case["repo"], role, j["rotation"], j["label"], axis, j["scores"][axis], j["evidence"][axis]])
            pair = compare(case, "develop", "control")
            cells = [case["repo"], *scores, fmt(pair["delta"] if pair else None),
                     "yes" if pair and pair["reversal"] else "no" if pair else "—"]
            lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "The delta is the median of the three within-rotation differences. A reversal means that "
                  "different rotations favored opposite submissions. The table below includes completed or merged submissions "
                  "with complete code scores, including submissions with a failed gate.", "",
                  "| Comparison | Matched repositories | Mean paired delta /85 | Repositories with reversals |",
                  "| --- | ---: | ---: | ---: |"])
    for first, second in (("develop", "control"), ("develop", "upstream"), ("control", "upstream")):
        pairs = [p for case in rows if (p := compare(case, first, second)) is not None]
        avg = statistics.mean(p["delta"] for p in pairs) if pairs else None
        lines.append(f"| {first} − {second} | {len(pairs)} | {fmt(avg)} | {sum(p['reversal'] for p in pairs)} |")
    lines.extend(["", "[Axes and readiness for every patch](diff-quality.csv) · [Per-rotation evidence](diff-evidence.csv)", ""])
    (target / "diff-quality.md").write_text("\n".join(lines))
    print(target / "diff-quality.md")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    render(parser.parse_args().name)
