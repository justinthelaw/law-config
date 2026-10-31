"""Capture a replayable Develop package and its native hook digest."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import native_panel as N


def capture(args):
    cli = N.pinned_cli()
    prior = N.B.read(args.previous.resolve(strict=True))
    if prior["scope"] != "plugins/develop":
        raise ValueError("choose a Develop package recipe")
    scope = prior["scope"]
    root = args.source.resolve(strict=True)
    if Path(os.fsdecode(N.git(root, "rev-parse", "--show-toplevel")).strip()) != root:
        raise ValueError("choose the Git checkout root containing plugins/develop")
    listing = N.git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", scope)
    files = sorted({root / os.fsdecode(p) for p in listing.split(b"\0") if p and (root / os.fsdecode(p)).is_file()})
    pin = N.E.host.package_hash(root / scope, files)
    snapshot = N.stage_source(root, pin)
    target = N.B.HERE / "treatments" / pin[:12]
    published = target.exists()
    if published:
        recipe = N.B.read(target / "recipe.json")
    else:
        recipe = dict(prior, format="law-config.treatment-recipe/v3",
                      base_package_sha256=prior.get("base_package_sha256", prior["package_sha256"]))
    if "base_package_sha256" in recipe:
        base = N.restore_source(N.full_recipe(recipe["base_package_sha256"]))
        reference = N.git(base, "write-tree").decode().strip()
        (snapshot / ".git/objects/info/alternates").write_text(str(base / ".git/objects") + "\n")
    else:
        reference = recipe["git_base"]
        N.git(snapshot, "fetch", "--quiet", "--depth=1", root, reference)
    omitted = [":(exclude)" + scope + "/" + p.as_posix() for p in N.omissions(recipe)]
    patch = N.git(snapshot, "diff", "--cached", "--binary", "--no-ext-diff", reference, "--", scope, *omitted)
    N.E.host.ROOT = snapshot
    N.E.host.PACKAGE_SHA256 = pin
    scratch = Path(tempfile.mkdtemp(prefix="hook-discovery-"))
    profile = scratch / "profile"
    work = scratch / "work"
    profile.mkdir()
    work.mkdir()
    (profile / "config.toml").write_text('[features]\napps = false\nremote_plugin = false\n[plugins._default]\nenabled = false\n')
    N.E.host.install(profile, cli)
    server = N.C.controller.STOCK(cli, profile, work, time.monotonic() + 90)
    try:
        groups = server.rpc("hooks/list", {"cwds": [str(work)]})["data"]
        hooks = [h for group in groups for h in group["hooks"] if h.get("pluginId") == N.E.host.PLUGIN]
        definitions = {}
        packages = set()
        for hook in hooks:
            definition, package = hook["currentHash"].split("/")
            definitions[hook["key"].split(":")[-3]] = definition.removeprefix("sha256:")
            packages.add(package.removeprefix("sha256:"))
        if len(hooks) != 2 or set(definitions) != {"pre_tool_use", "post_tool_use"} or len(packages) != 1:
            raise ValueError("unexpected native hook inventory")
    finally:
        server.close()
    lock = {"label": args.label, "package_sha256": pin, "plugin_hook_sha256": packages.pop(), "hook_sha256": definitions}
    recipe.update(package_sha256=pin, patch_sha256=hashlib.sha256(patch).hexdigest(), files=len(files))
    suffix = {"package.patch": patch, "recipe.json": (json.dumps(recipe, indent=2) + "\n").encode(),
              "treatment.json": (json.dumps(lock, indent=2) + "\n").encode()}
    if published:
        if any((target / k).read_bytes() != v for k, v in suffix.items()):
            raise ValueError("a different recipe already owns this package hash")
    else:
        stage = Path(tempfile.mkdtemp(prefix="recipe-"))
        for name, contents in suffix.items():
            (stage / name).write_bytes(contents)
        N.git(base, "apply", "--index", stage / "package.patch")
        N.verify(base, stage / "recipe.json")
        stage.rename(target)
    restored = N.restore_source(target / "recipe.json")
    print("Restored", pin, "from", target.relative_to(N.B.ROOT), "into", restored)
    return 0
