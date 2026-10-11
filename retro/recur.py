"""Recurrence check: does a lesson already exist in other words? Searches each of three content
words separately across every project memory store, the global CLAUDE.md, the rules folder and
the project's CLAUDE.md, and prints each file that holds at least two of the three. Standard
library only.

Usage: python recur.py [--claude-dir PATH] [--project-dir PATH] --words W1 W2 W3
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from candidates import _stem  # noqa: E402
from llm import claude_dir  # noqa: E402

NEEDED = 2


def files_to_search(cfg: Path, project_dir: Path | None):
    paths = sorted((cfg / "projects").glob("*/memory/*.md")) if (cfg / "projects").exists() else []
    paths.append(cfg / "CLAUDE.md")
    paths += sorted((cfg / "rules").rglob("*.md")) if (cfg / "rules").exists() else []
    if project_dir is not None:
        paths.append(project_dir / "CLAUDE.md")
    return [p for p in paths if p.is_file()]


def search(cfg: Path, words, project_dir: Path | None = None):
    """Return (path, matched words) for every file holding at least NEEDED of the words. A word
    matches any token that starts with its stem, so "attempts" also finds "attempt"."""
    pats = [(w, re.compile(r"\b" + re.escape(_stem(w.lower())), re.I)) for w in words]
    hits = []
    for p in files_to_search(cfg, project_dir):
        text = p.read_text(encoding="utf-8", errors="replace")
        found = [w for w, pat in pats if pat.search(text)]
        if len(found) >= NEEDED:
            hits.append((p, found))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    ap.add_argument("--project-dir", type=Path, default=None)
    ap.add_argument("--words", nargs=3, required=True)
    a = ap.parse_args(argv)
    hits = search(a.claude_dir or claude_dir(), a.words, a.project_dir)
    for p, found in hits:
        print(f"{p}\t{len(found)} of 3\t{' '.join(found)}")
    if not hits:
        print("none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
