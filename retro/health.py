"""Print retro store metrics. Never edits anything. Exit 0 always.

Usage: python health.py [--claude-dir PATH] [--store SLUG]
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_dir  # noqa: E402

GOTCHAS_BUDGET = 350
STORE_CAP = 20
DATED = re.compile(r"20[0-9]{2}-[0-9]{2}")


def gotchas_words(claude_md: Path):
    if not claude_md.exists():
        return None
    lines = claude_md.read_text(encoding="utf-8", errors="replace").splitlines()
    inside = False
    words = 0
    found = False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip() == "Machine gotchas"
            found = found or inside
            continue
        if inside:
            words += len(line.split())
    return words if found else None


def store_stats(projects_dir: Path):
    out = []
    if not projects_dir.exists():
        return out
    for slug_dir in sorted(projects_dir.iterdir()):
        mem = slug_dir / "memory"
        if not mem.is_dir():
            continue
        files = [p for p in mem.glob("*.md") if p.name != "MEMORY.md"]
        if not files:
            continue
        out.append((slug_dir.name, len(files), sum(1 for p in files if DATED.search(p.name))))
    return out


def findings_status(findings: Path):
    if not findings.exists():
        return None
    lines = findings.read_text(encoding="utf-8", errors="replace").splitlines()
    age = float("inf")
    if lines and lines[0].startswith("# last-scan:"):
        stamp = lines[0].split(":", 1)[1].strip()
        try:
            age = (datetime.now() - datetime.fromisoformat(stamp)).total_seconds() / 86400
        except ValueError:
            pass
    open_rows = sum(1 for l in lines[1:] if l.split("\t")[8:9] == ["open"])
    return open_rows, age


def ledger_bad_stores(ledger: Path, slugs):
    if not ledger.exists():
        return []
    bad = []
    for line in ledger.read_text(encoding="utf-8", errors="replace").splitlines():
        cols = line.split("\t")
        if len(cols) > 1 and cols[1] and cols[1] != "global" and cols[1] not in slugs and cols[1] not in bad:
            bad.append(cols[1])
    return bad


def report(cfg: Path, store=None) -> str:
    lines = []
    w = gotchas_words(cfg / "CLAUDE.md")
    lines.append("Machine gotchas: section absent" if w is None else f"Machine gotchas: {w} of {GOTCHAS_BUDGET} words")
    stats = store_stats(cfg / "projects")
    for slug, n, d in stats:
        if store is None or slug == store:
            lines.append(f"{slug}: {n} of {STORE_CAP} entries, {d} dated files")
    fs = findings_status(cfg / "retro" / "findings.tsv")
    if fs is None:
        lines.append("Findings: no file; scan has never run")
    else:
        age = "unknown age" if fs[1] == float("inf") else f"scan {fs[1]:.0f} days old"
        lines.append(f"Findings: {fs[0]} open, {age}")
    bad = ledger_bad_stores(cfg / "retro" / "retro-log.tsv", {s for s, _, _ in stats})
    lines.append(f"Ledger: {len(bad)} rows whose store is not a memory folder slug" + (": " + ", ".join(bad) if bad else ""))
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    ap.add_argument("--store", default=None)
    a = ap.parse_args()
    print(report(a.claude_dir or claude_dir(), a.store))
