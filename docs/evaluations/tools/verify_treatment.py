"""Verify the bytes of a reconstructed historical package without installing it."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess

def omissions(recipe):
    paths = recipe.get("omit", [])
    if any(not re.fullmatch(r"[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*", p)
           or any(part in (".", "..") for part in p.split("/")) for p in paths):
        raise ValueError("omissions must be literal package-relative paths")
    return [Path(p) for p in paths]


def verify(checkout, recipe_path):
    recipe = json.loads(recipe_path.read_text())
    patch = recipe_path.parent / recipe["patch"]
    if hashlib.sha256(patch.read_bytes()).hexdigest() != recipe["patch_sha256"]:
        raise ValueError("reconstruction patch differs")
    head = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
    if head != recipe["git_base"]:
        raise ValueError("checkout is not at the recipe's Git base")
    listing = subprocess.check_output(["git","-C",checkout,"ls-files","-z","--",recipe["scope"]])
    files = sorted((checkout / os.fsdecode(p) for p in listing.split(b"\0") if p),
                   key=lambda p:p.relative_to(checkout / recipe["scope"]).as_posix())
    dropped = [checkout / recipe["scope"] / rel for rel in omissions(recipe)]
    if any(p.exists() or p.is_symlink() for p in dropped):
        raise ValueError("a file excluded by the recipe is present")
    files = [p for p in files if not any(p.is_relative_to(d) for d in dropped)]
    h = hashlib.sha256()
    for path in files:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or unexpected linked package file: {path}")
        h.update(path.relative_to(checkout/recipe["scope"]).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    if len(files) != recipe["files"] or h.hexdigest() != recipe["package_sha256"]:
        raise ValueError("reconstructed package differs")
    print(f"{len(files)} files, package {h.hexdigest()}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("recipe", type=Path)
    args=parser.parse_args()
    verify(args.checkout.resolve(), args.recipe.resolve())
