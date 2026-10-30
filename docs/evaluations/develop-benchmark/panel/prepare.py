"""Prepare the reference-only caches and pinned workers for the twenty-repository panel."""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import environment as E


def provision(case, seen):
    family = case["image"]
    if family in seen:
        return
    image = E.PANEL["images"][family]
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode:
        if family == "java":
            E.lab.call("docker", "build", "--platform", "linux/amd64", "-t", image,
                       "-f", E.HERE/"Dockerfile.jdk", E.HERE)
        else:
            E.lab.call("docker", "pull", "--platform", "linux/amd64", image)
    if subprocess.run(["docker", "image", "inspect", E.guest.tag(case)], capture_output=True).returncode:
        E.guest.build(case)
    seen.add(family)


def prepare(cases):
    E.configure()
    seen = set()
    for case in cases:
        provision(case, seen)
        E.prepare(case)
        delta = E.lab.git(E.lab.objects(case), "diff", "--numstat", case["base"], case["gold"]).splitlines()
        counts = [s.split("\t")[:2] for s in delta]
        if [len(counts), *(sum(int(row[i]) for row in counts if row[i] != "-") for i in range(2))] != case["delta"]:
            raise ValueError("merged diff size changed: "+case["id"])
        entries=E.lab.tree_entries(E.lab.objects(case),case["base"])
        if len(entries) != case["base_files"]:
            raise ValueError("starting tree size changed: "+case["id"])
        print(case["id"], E.dependency_digest(case), E.worker_ids(case)["worker"], flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--case", choices=E.CASES)
    opts=parser.parse_args()
    prepare([E.CASES[opts.case]] if opts.case else E.CASES.values())
