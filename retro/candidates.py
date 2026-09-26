"""Retro candidates: single-session observations that become findings when seen twice.
One TSV per project under ~/.claude/retro/candidates/. Standard library only.

Usage: python candidates.py [--claude-dir PATH] log --project P --category C --key K --summary S [--date D]
       | status --project P --category C --key K STATUS | list --project P | expire --project P [--days 60]
"""
import argparse
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_dir  # noqa: E402

CATEGORIES = ("repeat-manual", "revisited", "rework-loop", "tool-friction", "time-sink")
STATUSES = ("open", "proposed", "denied", "promoted")
COLS = ["date", "category", "key", "summary", "count", "last_seen", "status"]
CAP = 30
EXPIRE_DAYS = 60
STOP = {"the", "a", "an", "of", "by", "in", "on", "to", "and", "for", "with", "again", "was", "were", "is"}


def path(cfg: Path, project: str) -> Path:
    return cfg / "retro" / "candidates" / f"{project}.tsv"


def normalize(key: str) -> str:
    return re.sub(r"\s+", " ", (key or "").strip().lower())[:80]


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _words(key: str):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", normalize(key)) if w not in STOP}


def similar(a: str, b: str) -> bool:
    # Containment, not Jaccard: two writers describing one pattern agree on the nouns but not on
    # how many words they use, and a short key wholly inside a longer one is the same observation.
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return normalize(a) == normalize(b)
    shared = wa & wb
    # At least two shared words, so one common noun ("thing") cannot merge unrelated patterns.
    return len(shared) >= 2 and len(shared) / min(len(wa), len(wb)) >= 0.5


def validate(cfg: Path):
    """Check every candidates file the way ledger.validate checks the ledger: column count, known
    category, known status, integer count. Returns one line per problem."""
    bad = []
    cdir = cfg / "retro" / "candidates"
    if not cdir.exists():
        return bad
    for p in sorted(cdir.glob("*.tsv")):
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines()[1:], start=2):
            cols = line.split("\t")
            if len(cols) != len(COLS):
                bad.append(f"{p.stem} line {n}: {len(cols)} columns")
                continue
            r = dict(zip(COLS, cols))
            if r["category"] not in CATEGORIES or r["status"] not in STATUSES:
                bad.append(f"{p.stem} line {n}: category {r['category']!r} status {r['status']!r}")
            elif not r["count"].isdigit():
                bad.append(f"{p.stem} line {n}: count {r['count']!r}")
    return bad


def load(cfg: Path, project: str):
    p = path(cfg, project)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) == len(COLS):
            r = dict(zip(COLS, cols))
            r["count"] = int(r["count"])
            rows.append(r)
    return rows


def save(cfg: Path, project: str, rows):
    p = path(cfg, project)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = ["\t".join(COLS)] + ["\t".join(str(r[c]).replace("\t", " ").replace("\n", " ") for c in COLS) for r in rows]
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def _find(rows, category, key):
    for r in rows:
        if r["category"] == category and similar(r["key"], key):
            return r
    return None


def log(cfg: Path, project: str, category: str, key: str, summary: str, today: str):
    date.fromisoformat(today)
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}")
    rows = load(cfg, project)
    r = _find(rows, category, key)
    if r is None:
        r = {"date": today, "category": category, "key": normalize(key), "summary": (summary or "")[:200],
             "count": 0, "last_seen": today, "status": "open"}
        rows.append(r)
    r["count"] += 1
    r["last_seen"] = today
    confirmed = r["count"] >= 2 and r["status"] == "open"
    # The cap bounds open single-sighting rows only. Confirmed rows, and denied, proposed
    # and promoted rows at any count, are never evicted or expired, so a denial or a
    # promotion is remembered and the same pattern is never raised again.
    if len(rows) > CAP:
        singles = sorted((x for x in rows if x["count"] == 1 and x["status"] == "open" and x is not r),
                         key=lambda x: x["last_seen"])
        for x in singles[: len(rows) - CAP]:
            rows.remove(x)
    save(cfg, project, rows)
    return r, confirmed


def set_status(cfg: Path, project: str, category: str, key: str, status: str) -> bool:
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    rows = load(cfg, project)
    r = _find(rows, category, key)
    if r is None:
        return False
    r["status"] = status
    save(cfg, project, rows)
    return True


def expire(cfg: Path, project: str, today: str, days: int = EXPIRE_DAYS) -> int:
    rows = load(cfg, project)
    t = date.fromisoformat(today)
    keep = [r for r in rows
            if not (r["count"] == 1 and r["status"] == "open"
                    and (t - date.fromisoformat(r["last_seen"])).days > days)]
    if len(keep) != len(rows):
        save(cfg, project, keep)
    return len(rows) - len(keep)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("log")
    for opt in ("--project", "--category", "--key", "--summary"):
        lg.add_argument(opt, required=True)
    lg.add_argument("--date", default=None)
    s = sub.add_parser("status")
    for opt in ("--project", "--category", "--key"):
        s.add_argument(opt, required=True)
    s.add_argument("status")
    li = sub.add_parser("list")
    li.add_argument("--project", required=True)
    e = sub.add_parser("expire")
    e.add_argument("--project", required=True)
    e.add_argument("--days", type=int, default=EXPIRE_DAYS)
    a = ap.parse_args(argv)
    cfg = a.claude_dir or claude_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        if a.cmd == "log":
            r, ok = log(cfg, a.project, a.category, a.key, a.summary, a.date or today)
            print(f"{r['category']}\t{r['key']}\tcount={r['count']}\tstatus={r['status']}\tconfirmed={'yes' if ok else 'no'}")
        elif a.cmd == "status":
            if not set_status(cfg, a.project, a.category, a.key, a.status):
                print("not found")
                return 1
            print("updated")
        elif a.cmd == "list":
            rows = load(cfg, a.project)
            for r in rows:
                print("\t".join(str(r[c]) for c in COLS))
            if not rows:
                print("none")
        elif a.cmd == "expire":
            print(f"expired {expire(cfg, a.project, today, a.days)}")
    except ValueError as err:
        print(str(err), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
