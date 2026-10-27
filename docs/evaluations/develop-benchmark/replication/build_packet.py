"""Rebuild the source packet for a frozen benchmark case from its public base archive."""
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

CAP = 90_000
TILE = 36
HALO = 12
TEST_SHARE = 0.30
STOP = set("a an and are as at be by for from in into is it its of on or our same should than that the their through to using with while".split())
CPP = set(".c .cc .cpp .cxx .cu .h .hh .hpp .hxx .inc .inl".split())
WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
Q = 8  # decimal places in deterministic score tie groups

JS = set(".js .jsx .mjs .cjs .ts .tsx .svelte".split())
SHELL = set(".sh .bash .zsh .py".split())
LANGUAGES = {"shell-v2": SHELL, "js-v2": JS, "rust-v2": {".rs"}}
CODE_ROOTS = {"src", "lib", "app", "components", "hooks", "scripts"}


def source_files(archive_path, case):
    if sha256(archive_path.read_bytes()).hexdigest() != case["base_archive_sha256"]:
        raise ValueError("Archive differs from the frozen public base")
    mode = case["packet_method"]
    files = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or len(path.parts) < 2:
                raise ValueError("Unexpected archive path")
            rel = PurePosixPath(*path.parts[1:])
            raw = archive.extractfile(member).read()
            if mode == "cpp-v1":
                include = rel.suffix.lower() in CPP
            else:
                code = rel.suffix.lower() in LANGUAGES[mode]
                code = code or (not rel.suffix and raw.startswith(b"#!"))
                eligible_path = (len(rel.parts) == 1 or CODE_ROOTS.intersection(rel.parts[:-1])
                                 or is_test(str(rel)))
                include = (str(rel) == "README.md" and len(raw) <= 8192) or (
                    code and len(raw) <= 262144 and eligible_path)
            if include:
                raw.decode("utf-8")
                chunks = raw.split(b"\n")
                lines = [line + b"\n" for line in chunks[:-1]]
                if chunks[-1]:
                    lines.append(chunks[-1])
                files[str(rel)] = lines
    return files


def forms(word):
    """Index symbols, their word parts and common suffix variants."""
    out = {word.lower()}
    for part in CAMEL.sub("_", word).lower().split("_"):
        if not part:
            continue
        out.add(part)
        if len(part) > 4 and part.endswith("s") and not part.endswith("ss"):
            out.add(part[:-1])
        if len(part) > 5 and part.endswith("ed"):
            out.update((part[:-2], part[:-1]))
        if len(part) > 6 and part.endswith("ing"):
            base = part[:-3]
            out.update((base, base + "e", base[:-1] if len(base) > 1 and base[-2] == base[-1] else base))
    return out


def words(text):
    return [w for w in WORD.findall(text) if w.lower() not in STOP and len(w) > 1]


def is_test(path):
    return any(re.search(r"(^|[-_.])tests?($|[-_.])", p.lower()) for p in PurePosixPath(path).parts)


def index(source, req, primary_readme):
    concepts = sorted({w.lower() for w in words(req)})
    term_forms = {w: forms(w) for w in concepts}
    inverted = defaultdict(set)
    for term in concepts:
        for variant in term_forms[term]:
            inverted[variant].add(term)

    def hits(s):
        freq = Counter()
        for w in words(s):
            found = set()
            for variant in forms(w):
                found.update(inverted.get(variant, ()))
            freq.update(found)
        return freq

    tiles = []
    path_terms = {}
    doc_freq = Counter()
    for p, lines in sorted(source.items()):
        path_terms[p] = hits(p)
        for start in range(0, len(lines), TILE):
            freq = hits(b"".join(lines[start:start + TILE]).decode())
            doc_freq.update(freq.keys())
            tiles.append((p, start, freq))
    weights = {t: math.log(1 + (len(tiles) + 1) / (1 + doc_freq[t])) * (2.4 if "_" in t else 1.0) for t in concepts}

    def score(freq):
        return sum(weights[t] * (1 + math.log1p(min(freq[t], 6)) / 2) for t in sorted(freq))

    path_scores = {p: score(f) for p, f in path_terms.items()}
    best = defaultdict(float)
    for p, _, f in tiles:
        best[p] = max(best[p], score(f))
    ranked = []
    for p, start, f in tiles:
        if not f and not (primary_readme and p == "README.md"):
            continue
        value = score(f) + 0.55 * path_scores[p] + 0.13 * best[p]
        if primary_readme and p == "README.md":
            value = 1e9
        ranked.append((round(value, Q), p, start))
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))
    return ranked


def groups(chosen):
    for p in sorted(chosen):
        seq = sorted(chosen[p])
        if not seq:
            continue
        start = prev = seq[0]
        for n in seq[1:]:
            if n != prev + 1:
                yield p, start, prev
                start = n
            prev = n
        yield p, start, prev


def excerpts(chosen, source):
    for p, a, b in groups(chosen):
        lines = source[p]
        yield (f"\n--- {p} | lines {a + 1}-{b + 1} of {len(lines)} ---\n".encode()
               + b"".join(f"{i + 1:>5} | ".encode() + lines[i].rstrip(b"\r\n") + b"\n" for i in range(a, b + 1)))


def choose(ranked, source, room):
    chosen = defaultdict(set)
    used = {False: 0, True: 0}

    def phase(pool, budgets):
        for _, p, begin in ranked:
            typ = is_test(p)
            if pool is not None and pool != typ:
                continue
            full = source[p]
            a = max(0, begin - HALO)
            b = min(len(full), begin + TILE + HALO)
            new = set(range(a, b)) - chosen[p]
            if not new:
                continue
            # Only the changed file's serialized contribution needs recomputation.
            before = sum(map(len, excerpts({p: chosen[p]}, source)))
            after = sum(map(len, excerpts({p: chosen[p] | new}, source)))
            delta = after - before
            if used[typ] + delta > budgets[typ] or sum(used.values()) + delta > room:
                continue
            chosen[p].update(new)
            used[typ] += delta

    limits = {True: round(room * TEST_SHARE), False: room - round(room * TEST_SHARE)}
    phase(False, limits)
    phase(True, limits)
    phase(None, {False: room, True: room})
    return chosen


def main():
    cases = json.loads(Path(__file__).with_name("inputs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=cases)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    case = cases[args.case]
    source = source_files(args.archive, case)
    requirement = case["requirement"]
    ranked = index(source, requirement, case["packet_method"] != "cpp-v1")
    header = ("BASE SOURCE PACKET\n\nFrozen requirement\n" + requirement
              + "\n\nPaths are relative to the archive root. Each excerpt uses original one-based line numbers. "
                "Outside each printed range, source lines have been omitted. Strip the number and its ' | ' "
                "separator to recover each displayed source line.\n").encode()
    chosen = choose(ranked, source, CAP - len(header))
    packet = header + b"".join(excerpts(chosen, source))
    if len(packet) != case["packet_bytes"] or sha256(packet).hexdigest() != case["packet_sha256"]:
        raise ValueError("Rebuilt packet differs from the frozen input")
    sys.stdout.buffer.write(packet)


if __name__ == "__main__":
    main()
