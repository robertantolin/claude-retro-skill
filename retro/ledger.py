"""Retro ledger v3: one row per proposal in ~/.claude/retro/retro-log.tsv. Standard library only.

Usage: python ledger.py [--claude-dir PATH] append --run-id R --project P --proposal N
           --finding-id F --kind K --decision D [--refine-count N] [--applied y|n] [--verified y|n|na]
       python ledger.py validate | recent --project P [--hours 24] | pending --project P
"""
import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings  # noqa: E402
from llm import claude_dir  # noqa: E402

COLS = ["run_id", "timestamp", "project", "proposal", "finding_id", "kind", "decision",
        "refine_count", "applied", "verified"]
DECISIONS = ("approve-once", "approve-always", "deny", "no-decision", "auto", "none", "reverted")
RAISED_AFTER = 3


def path(cfg: Path) -> Path:
    return cfg / "retro" / "retro-log.tsv"


def _migrate(cfg: Path):
    p = path(cfg)
    # An empty file carries no header and is not a pre-v3 ledger, so it never displaces one.
    if not p.exists() or p.stat().st_size == 0:
        return
    first = p.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    if first == "\t".join(COLS):
        return
    v2 = p.with_name("retro-log.v2.tsv")
    if v2.exists():
        # a pre-v3 ledger is the only copy of that history; date the earlier one rather than
        # overwrite it
        os.replace(v2, v2.with_name(f"retro-log.v2.{datetime.now().strftime('%Y%m%d-%H%M%S')}.tsv"))
    os.replace(p, v2)


def load_rows(cfg: Path):
    _migrate(cfg)
    p = path(cfg)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) == len(COLS):
            rows.append(dict(zip(COLS, cols)))
    return rows


def validate(cfg: Path):
    _migrate(cfg)
    p = path(cfg)
    if not p.exists():
        return []
    bad = []
    for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines()[1:], start=2):
        cols = line.split("\t")
        if len(cols) != len(COLS):
            bad.append(f"line {n}: {len(cols)} columns")
            continue
        r = dict(zip(COLS, cols))
        if r["kind"] not in settings.KINDS + ("none",) or r["decision"] not in DECISIONS:
            bad.append(f"line {n}: kind {r['kind']!r} decision {r['decision']!r}")
    return bad


def append_row(cfg: Path, run_id, project, proposal, finding_id, kind, decision,
               refine_count=0, applied="n", verified="na", timestamp=None):
    if kind not in settings.KINDS + ("none",):
        raise ValueError(f"bad kind {kind!r}")
    if decision not in DECISIONS:
        raise ValueError(f"bad decision {decision!r}")
    if applied not in ("y", "n"):
        raise ValueError(f"bad applied {applied!r}")
    if verified not in ("y", "n", "na"):
        raise ValueError(f"bad verified {verified!r}")
    _migrate(cfg)
    row = {"run_id": run_id, "timestamp": timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M"),
           "project": project, "proposal": int(proposal), "finding_id": finding_id, "kind": kind,
           "decision": decision, "refine_count": int(refine_count), "applied": applied, "verified": verified}
    p = path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists() or p.stat().st_size == 0
    with p.open("a", encoding="utf-8") as f:
        if new:
            f.write("\t".join(COLS) + "\n")
        f.write("\t".join(str(row[c]) for c in COLS) + "\n")
    # Denials count per kind within one project. A kind declined in one project can be the right
    # one in another: on 2026-09-17 one denial in project A plus two in project B switched
    # lesson files off everywhere. Approve-always stays per kind across projects.
    if kind in settings.KINDS and decision in ("approve-once", "approve-always", "deny"):
        judged = [r for r in load_rows(cfg) if r["kind"] == kind and r["project"] == project
                  and r["decision"] in ("approve-once", "approve-always", "deny")]
        tail = judged[-RAISED_AFTER:]
        if len(tail) == RAISED_AFTER and all(r["decision"] == "deny" for r in tail):
            settings.set_bar(cfg, kind, True, project)
    return row


def _within(r, hours):
    try:
        return datetime.fromisoformat(r["timestamp"]) >= datetime.now() - timedelta(hours=hours)
    except ValueError:
        return False


def recent(cfg: Path, project: str, hours: int = 24):
    return [r for r in load_rows(cfg) if r["project"] == project and _within(r, hours)
            and r["decision"] in ("approve-once", "approve-always", "auto", "no-decision")]


def pending(cfg: Path, project: str):
    return [r for r in load_rows(cfg) if r["project"] == project and r["decision"] == "no-decision"]


def mark_reverted(cfg: Path, run_id: str) -> int:
    """Flip the decision column to 'reverted' for a run, leaving every other line byte-for-byte."""
    _migrate(cfg)
    p = path(cfg)
    if not p.exists():
        return 0
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    col = COLS.index("decision")
    out, n = lines[:1], 0
    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) == len(COLS) and cols[0] == run_id and cols[col] != "reverted":
            cols[col] = "reverted"
            line = "\t".join(cols)
            n += 1
        out.append(line)
    if n:
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(tmp, p)
    return n


def title_of(cfg: Path, run_id: str, proposal) -> str:
    p = cfg / "retro" / "proposals" / run_id / f"{proposal}.md"
    if not p.exists():
        return ""
    first = p.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    first = re.sub(r"^#+\s*", "", first)
    return re.sub(r"^Proposal\s+\d+\s+of\s+\d+:\s*", "", first).strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("append")
    for opt in ("--run-id", "--project", "--proposal", "--finding-id", "--kind", "--decision"):
        a1.add_argument(opt, required=True)
    a1.add_argument("--refine-count", default=0)
    a1.add_argument("--applied", default="n")
    a1.add_argument("--verified", default="na")
    sub.add_parser("validate")
    a3 = sub.add_parser("recent")
    a3.add_argument("--project", required=True)
    a3.add_argument("--hours", type=int, default=24)
    a4 = sub.add_parser("pending")
    a4.add_argument("--project", required=True)
    a = ap.parse_args(argv)
    cfg = a.claude_dir or claude_dir()
    if a.cmd == "append":
        raised_before = a.kind in settings.KINDS and settings.is_raised(cfg, a.kind, a.project)
        try:
            r = append_row(cfg, a.run_id, a.project, a.proposal, a.finding_id, a.kind, a.decision,
                           a.refine_count, a.applied, a.verified)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print("\t".join(str(r[c]) for c in COLS))
        if a.kind in settings.KINDS and not raised_before and settings.is_raised(cfg, a.kind, a.project):
            print(f"bar raised: {a.kind} proposals in {a.project} are logged as candidates from now on "
                  f"({RAISED_AFTER} denials in a row); turn them back on with: "
                  f"python settings.py reset-bar {a.kind} {a.project}")
    elif a.cmd == "validate":
        bad = validate(cfg)
        print("ledger OK" if not bad else "\n".join(bad))
        return 1 if bad else 0
    elif a.cmd in ("recent", "pending"):
        rows = recent(cfg, a.project, a.hours) if a.cmd == "recent" else pending(cfg, a.project)
        for r in rows:
            print(f"{r['run_id']}\t{r['proposal']}\t{r['finding_id']}\t{r['kind']}\t{r['decision']}\t{title_of(cfg, r['run_id'], r['proposal'])}")
        if not rows:
            print("none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
