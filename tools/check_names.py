"""Check that no versioned file and no commit contains names from real projects.

  python tools/check_names.py <terms.json>

terms.json is a JSON list of strings kept OUTSIDE the repository (the names of tests, files, levels, models that must never
be published). The script searches the working tree and every object of every commit (files, messages, old versions) and
prints, for each place where something matches, the index of the term and never the term itself, so its output can be shared.
Exit code 1 if anything matches. Matching ignores case and treats space, underscore and hyphen as the same.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys


def norm(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", s.lower())


def main(path: str) -> int:
    terms = [t for t in json.load(open(path, encoding="utf-8")) if len(t) > 10]
    nt = [(i, norm(t)) for i, t in enumerate(terms)]
    hits: set[tuple[str, str, int]] = set()
    objs = subprocess.run(["git", "rev-list", "--all", "--objects"], capture_output=True, text=True, check=True).stdout.splitlines()
    cat = subprocess.Popen(["git", "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert cat.stdin and cat.stdout
    for line in objs:
        sha = line.split(" ")[0]
        cat.stdin.write((sha + "\n").encode())
        cat.stdin.flush()
        head = cat.stdout.readline().split()
        body = cat.stdout.read(int(head[2]))
        cat.stdout.read(1)
        text = norm(body.decode("utf-8", "ignore") + " " + (line.split(" ", 1)[1] if " " in line else ""))
        hits |= {(sha[:8], head[1].decode(), i) for i, t in nt if t in text}
    tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    for name in tracked:
        try:
            text = norm(open(name, encoding="utf-8", errors="ignore").read() + " " + name)
        except OSError:
            continue
        hits |= {("worktree", name, i) for i, t in nt if t in text}
    print(f"{len(objs)} objects and {len(tracked)} tracked files checked against {len(nt)} terms")
    for h in sorted(hits):
        print("MATCH", *h)
    print("CLEAN" if not hits else f"{len(hits)} matches")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
