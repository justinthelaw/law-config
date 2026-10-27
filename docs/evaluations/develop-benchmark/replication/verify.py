"""Verify public source-packet results offline. Optionally replay edits on public base archives."""

import argparse
import csv
import difflib
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
METRICS = ("uncached_input", "cached_input", "output", "reasoning_output", "total_context")


def read(name):
    return json.loads((HERE / name).read_bytes())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def artifact(arm):
    return read(arm["artifact_file"])


def patch_bytes(proposal):
    return "".join(proposal.get("patch_lines", [])).encode("utf-8")


def replay(archive, proposal, arm, eligible_paths):
    paths = {edit["path"] for edit in proposal["edits"]}
    require(paths <= eligible_paths, "Edit path outside the worker packet")
    with tarfile.open(archive, "r:gz") as source:
        originals = {
            member.name.split("/", 1)[1]: source.extractfile(member).read().decode("utf-8")
            for member in source
            if member.isfile() and "/" in member.name and member.name.split("/", 1)[1] in paths
        }
    require(paths == originals.keys(), "Changed file missing from base")
    updated = dict(originals)
    for edit in proposal["edits"]:
        path, before, after = edit["path"], edit["before"], edit["after"]
        require(before and before != after and updated[path].count(before) == 1, "Invalid edit anchor")
        updated[path] = updated[path].replace(before, after, 1)
    changed = sorted(path for path in paths if originals[path] != updated[path])
    require(changed == arm["changed_files"], "Changed-file list differs")
    actual = {path: sha256(updated[path].encode()).hexdigest() for path in changed}
    require(actual == arm["after_file_sha256"], "Applied file digest differs")
    patch = []
    for path in changed:
        patch.append(f"diff --git a/{path} b/{path}\n")
        for line in difflib.unified_diff(originals[path].splitlines(keepends=True), updated[path].splitlines(keepends=True),
                                         fromfile="a/" + path, tofile="b/" + path):
            patch.append(line)
            if not line.endswith("\n"):
                patch.append("\n\\ No newline at end of file\n")
    require("".join(patch).encode() == patch_bytes(proposal), "Unified diff differs from the applied edit")
    edits = [{"path": path, "before": originals[path], "after": updated[path]} for path in changed]
    data = (json.dumps({"edits": edits}, ensure_ascii=False) + "\n").encode()
    require(sha256(data).hexdigest() == arm["submitted_json_sha256"], "Scorer transport differs")


def verify_judgment(record, case, requirement, facts, rubric):
    mapping = record["anonymous_key"]
    require(set(mapping) == {"A", "B"} and set(mapping.values()) == {"control", "develop"}, "Invalid blind labels")
    candidates = {}
    for label in ("A", "B"):
        arm = case["arms"][mapping[label]]
        diff = patch_bytes(artifact(arm)).decode() or "(No applicable implementation.)"
        candidates[label] = {"implementation_diff": diff, "observations": facts[label]}
    body = json.dumps({"requirement": requirement, "candidates": candidates}, ensure_ascii=False)
    require(sha256((body + "\n").encode()).hexdigest() == record["evidence_sha256"], "Blind evidence differs")
    prompt = rubric["rubric"] + "\nReview focus: " + rubric["lanes"][record["lane"]] + "\n\n" + body
    require(sha256(prompt.encode()).hexdigest() == record["input_sha256"], "Blind review prompt differs")
    preference = record["anonymous_preference"]
    require(mapping.get(preference, preference) == record["preference"], "Blind preference mapping differs")
    answer = json.dumps({**record["observations"], "preference": preference}, ensure_ascii=False, sort_keys=True, indent=2)
    require(sha256(answer.encode()).hexdigest() == record["answer_sha256"], "Blind review answer differs")


def verify(archives=None, develop_repo=None, case_fixtures=None):
    cases, inputs = read("results.json")["cases"], read("inputs.json")
    procedure = read("procedure.json")
    common = {k: v for k, v in procedure.items() if k not in ("blind", "treatment_source")}
    if develop_repo is not None:
        treatment = procedure["treatment_source"]
        parts = []
        for name in treatment["file_order"]:
            revision = f"{treatment['commit']}:{treatment['directory']}/{name}"
            data = subprocess.check_output(["git", "-C", str(develop_repo), "show", revision])
            require(sha256(data).hexdigest() == procedure["treatment_files"][name], "Develop file digest differs")
            parts.append(b"File " + name.encode() + b"\n" + data)
        delivery = b"\n\n".join(parts)
        require(len(delivery) == treatment["bytes_per_phase"] and
                sha256(delivery).hexdigest() == procedure["treatment_sha256"], "Develop delivery differs")
    with (HERE.parent / "cases.csv").open(newline="") as file:
        historical = {row["case"]: row for row in csv.DictReader(file)}
    qualifications = read("qualifications.json")
    require(set(qualifications) == set(inputs), "Missing qualification record")
    if case_fixtures is not None:
        archive_hash = sha256(case_fixtures.read_bytes()).hexdigest()
        with tarfile.open(case_fixtures, "r:gz") as archived:
            for record in qualifications.values():
                if "case_archive_members" in record:
                    require(record["case_archive_sha256"] == archive_hash, "Historical case archive digest differs")
                    for member, expected in record["case_archive_members"].items():
                        data = archived.extractfile(member).read()
                        require(sha256(data).hexdigest() == expected, "Recovered acceptance fixture differs")
    for case_id, qualification in qualifications.items():
        source = inputs[case_id]
        original = historical[source["case"]]
        require(sha256((source["requirement"] + "\n").encode()).hexdigest() == original["requirement_sha256"],
                "Requirement differs from historical manifest")
        require(source["base_archive_url"].endswith("/" + original["base_commit"]), "Base revision differs")
        fields = source["frozen_case_fields"]
        frozen = (json.dumps({**common, **fields}, sort_keys=True, indent=2) + "\n").encode()
        require(sha256(frozen).hexdigest() == source["protocol_sha256"], "Frozen protocol differs")
        require(fields["order"] == source["arm_order"] and fields["seconds_per_arm"] == 60 * source["minutes_per_arm"],
                "Release order or time limit differs")
        require(source["protocol_sha256"] == qualification["frozen_protocol_sha256"], "Protocol digest differs")
        require(source["packet_sha256"] == qualification["packet_sha256"], "Qualification packet differs")
        require(source["base_archive_sha256"] == qualification["base_archive_sha256"], "Qualification base differs")
        for filename, expected in qualification.get("published_fixture_files_sha256", {}).items():
            require(Path(filename).name == filename, "Unsafe fixture filename")
            fixture = HERE / "fixtures" / case_id / filename
            require(sha256(fixture.read_bytes()).hexdigest() == expected, "Published fixture digest differs")
    observations, judges, blind_facts = read("observations.json"), read("blind-judgments.json"), read("blind-facts.json")
    phase_order = procedure["phase_order"]
    with (HERE / "phase-usage.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    with (HERE / "attempts.csv").open(newline="") as source:
        attempts = list(csv.DictReader(source))
    ledger = {(r["case"], r["condition"]): r for r in attempts}
    expected = {(case_id, arm) for case_id, source in inputs.items() for arm in source["arm_order"]}
    require(set(ledger) == expected and len(ledger) == len(attempts), "Incomplete or duplicate arm ledger")
    for (case_id, condition), row in ledger.items():
        source = inputs[case_id]
        require(row["cohort"] == source["cohort"] and int(row["order"]) == source["arm_order"].index(condition) + 1,
                "Ledger cohort or arm order differs")
        require(int(row["minutes_per_arm"]) == source["minutes_per_arm"], "Ledger time limit differs")
    require(len(rows) == len(cases) * 2 * len(phase_order), "Unattributed phase rows")
    require(len(judges) == len(cases) * 2, "Unattributed blind judgments")
    case_ids = {case["id"] for case in cases}
    require(len(case_ids) == len(cases) and set(observations) == set(blind_facts) == case_ids,
            "Duplicate or missing case evidence")
    work = read("workload.json")
    require((work["new_scored_pairs"], work["measured_arm_phases"], work["measured_blind_assessments"]) ==
            (len(cases), len(rows), len(judges)), "Workload denominator differs")
    require(work["blind_assessment_context_tokens"] == sum(row["total_context"] for row in judges),
            "Blind-assessment usage differs")

    for case in cases:
        case_id = case["id"]
        require(set(case["arms"]) == {"control", "develop"}, "Missing arm")
        source = inputs[case_id]
        require(case["cohort"] == source["cohort"], "Result cohort differs")
        if archives is not None:
            archive = archives / (source["case"].replace("/", "--") + "-base.legacy.tar.gz")
            packet = subprocess.check_output([sys.executable, str(HERE / "build_packet.py"), case_id, str(archive)])
            require(sha256(packet).hexdigest() == source["packet_sha256"], "Packet digest differs")
            paths = set(re.findall(r"^--- (.*?) \| lines [0-9]+-", packet.decode(), re.M))
        for condition, arm in case["arms"].items():
            attempt = ledger[case_id, condition]
            require(attempt["state"] == "completed" and attempt["usage_status"] == "complete" and
                    int(attempt["completed_calls"]) == int(attempt["usage_receipts"]) == len(phase_order),
                    "Incomplete scored attempt")
            require(float(attempt["arm_seconds"]) == arm["seconds"] and
                    int(attempt["known_total_context"]) == arm["total_context"], "Ledger measurement differs")
            for metric in ("uncached_input", "cached_input", "output"):
                require(int(attempt["known_" + metric]) == arm[metric], "Ledger token class differs")
            phases = [r for r in rows if r["case"] == case_id and r["condition"] == condition]
            require([r["phase"] for r in phases] == phase_order, "Incorrect phase order or count")
            for row in phases:
                require(row["procedure_acknowledged"] == "True" and row["observed_tool_items"] == "0",
                        "Procedure or isolation evidence missing")
                parts = [int(row[key]) for key in ("uncached_input", "cached_input", "output")]
                require(sum(parts) == int(row["total_context"]), "Incorrect phase total")
                require(0 <= int(row["reasoning_output"]) <= int(row["output"]), "Invalid reasoning subset")
                require(float(row["seconds"]) >= 0 and all(x >= 0 for x in parts), "Invalid phase measurement")
            for metric in METRICS:
                require(arm[metric] == sum(int(row[metric]) for row in phases), "Incorrect arm total")
            facts = observations[case_id][condition]
            require(facts["implementation_pass"] == arm["implementation_pass"], "Implementation mismatch")
            proposal = artifact(arm)
            require(sha256(patch_bytes(proposal)).hexdigest() == arm["diff_sha256"], "Patch digest differs")
            if arm["artifact_applicable"]:
                require(bool(patch_bytes(proposal)) and bool(proposal["edits"]), "Missing applying edit")
                if archives is not None:
                    replay(archive, proposal, arm, paths)
            else:
                require(not arm["implementation_pass"] and facts["status"] == "invalid_artifact",
                        "Unapplied candidate disposition differs")
                require(proposal["application"]["ok"] is False, "Invalid-artifact receipt missing")
                require(arm["submitted_json_sha256"] == sha256(b'{"edits": []}\n').hexdigest(),
                        "Invalid-artifact scoring payload differs")
        case_judgments = [j for j in judges if j["case"] == case_id]
        for record in case_judgments:
            verify_judgment(record, case, source["requirement"], blind_facts[case_id], procedure["blind"])
        votes = {j["lane"]: j["preference"] for j in case_judgments}
        require(votes == case["blind"] and set(votes) == {"correctness", "maintainability"}, "Blind vote mismatch")
    return len(cases), len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, help="Directory containing frozen public legacy base archives")
    parser.add_argument("--develop-repo", type=Path, help="Local law-config clone containing the frozen Develop commit")
    parser.add_argument("--case-fixtures", type=Path, help="Original case tar.gz published in issue 71, Evidence H")
    parser.add_argument("--emit-patch", nargs=2, metavar=("CASE", "CONDITION"),
                        help="Write the exact submitted unified diff to stdout")
    args = parser.parse_args()
    if args.emit_patch:
        case_id, condition = args.emit_patch
        for case in read("results.json")["cases"]:
            if case["id"] == case_id and condition in case["arms"]:
                arm = case["arms"][condition]
                require(arm["artifact_applicable"], "This arm submitted no applicable patch")
                data = patch_bytes(artifact(arm))
                require(sha256(data).hexdigest() == arm["diff_sha256"], "Patch digest differs")
                sys.stdout.buffer.write(data)
                return
        parser.error("unknown case or condition")
    cases, calls = verify(args.archives, args.develop_repo, args.case_fixtures)
    print(f"Verified {cases} pairs, {calls} scored calls and both judgments per case.")


if __name__ == "__main__":
    main()
