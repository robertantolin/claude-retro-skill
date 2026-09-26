"""Prints retro store metrics. The only write it can perform is moving a pre-v3 ledger aside to
retro-log.v2.tsv on first use, and it says so. Exit 0 always.

Usage: python health.py [--claude-dir PATH] [--store SLUG] [--metrics [--days N]]
"""
import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidates as C  # noqa: E402
import ledger  # noqa: E402
import scan  # noqa: E402
import settings  # noqa: E402
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


def findings_status(findings: Path, store=None):
    if not findings.exists():
        return None
    _, rows = scan.load_findings(findings)
    n = 0
    for r in rows:
        # dormant rows are delete candidates (scan.py --open lists them), not findings for the table
        if r["status"] != "open" or r["type"] == "dormant":
            continue
        if store is not None and r["store"] not in (store, "global"):
            continue
        n += 1
    return (n,)


def coverage(cfg: Path) -> str:
    p = cfg / "retro" / "scan-state.json"
    if not p.exists():
        return "History scan: never run"
    try:
        last = json.loads(p.read_text(encoding="utf-8")).get("last_scan")
    except json.JSONDecodeError:
        last = None
    return f"History scan: covers sessions up to {last[:10]}" if last else "History scan: never run"


def _journals(cfg: Path):
    jdir = cfg / "retro" / "journal"
    if not jdir.exists():
        return []
    out = []
    for p in sorted(jdir.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def metrics(cfg: Path, days: int = 30) -> dict:
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    rows = [r for r in ledger.load_rows(cfg) if r["timestamp"] >= since]
    raised = [r for r in rows if r["kind"] != "none"]
    applied = [r for r in raised if r["decision"] in ("approve-once", "approve-always", "auto") and r["applied"] == "y" and r["verified"] == "y"]
    by_kind = {}
    for r in raised:
        d = by_kind.setdefault(r["kind"], [0, 0])
        d[1] += 1
        if r["decision"] == "deny":
            d[0] += 1
    runs = {}
    for r in rows:
        runs.setdefault(r["run_id"], []).append(r)
    unread = sum(1 for rs in runs.values() if rs and all(r["decision"] == "no-decision" for r in rs))
    empty = sum(1 for rs in runs.values() if rs and all(r["kind"] == "none" for r in rs))
    journals = _journals(cfg)
    started = {j["run_id"]: j.get("started_at") for j in journals}
    waits = []
    for run_id, rs in runs.items():
        decided = [r for r in rs if r["decision"] in ("approve-once", "approve-always", "deny")]
        if decided and started.get(run_id):
            first = min(r["timestamp"] for r in decided)
            waits.append((datetime.fromisoformat(first) - datetime.fromisoformat(started[run_id])).total_seconds())
    written = []
    for j in journals:
        if (j.get("started_at") or "")[:10] < since[:10]:
            continue
        for w in j["writes"]:
            if w["kind"] == "store-write" and not w["deleted"] and w["after_sha"]:
                p = Path(w["path"])
                if p.parent.name == "memory":
                    written.append((f"mem:{p.parent.parent.name}/{p.stem}", j["started_at"][:10]))
    fpath = cfg / "retro" / "findings.tsv"
    _, frows = scan.load_findings(fpath) if fpath.exists() else (None, [])
    recurred = sum(1 for key, day in written if any(r["type"] == "recur" and r["lesson"] == key and r["found"] > day for r in frows))
    cands = []
    cdir = cfg / "retro" / "candidates"
    if cdir.exists():
        for p in cdir.glob("*.tsv"):
            cands += [c for c in C.load(cfg, p.stem) if c["date"] >= since[:10]]
    confirmed = sum(1 for c in cands if c["count"] >= 2)
    return {
        "days": days,
        "runs": len(runs), "runs_unread": unread, "empty_runs": empty,
        "proposals_raised": len(raised),
        "proposals_per_run": round(len(raised) / len(runs), 1) if runs else 0,
        "proposal_conversion": f"{len(applied)} of {len(raised)}",
        "denial_by_kind": {k: f"{d[0]} of {d[1]}" for k, d in by_kind.items()},
        "candidate_confirmation": f"{confirmed} of {len(cands)}",
        "lessons_written": len(written), "lessons_recurred": recurred,
        "time_to_first_decision_s": int(statistics.median(waits)) if waits else None,
    }


def report(cfg: Path, store=None) -> str:
    lines = []
    w = gotchas_words(cfg / "CLAUDE.md")
    lines.append("Machine gotchas: section absent" if w is None else f"Machine gotchas: {w} of {GOTCHAS_BUDGET} words")
    for slug, n, d in store_stats(cfg / "projects"):
        if store is None or slug == store:
            lines.append(f"{slug}: {n} of {STORE_CAP} entries, {d} dated files")
    fs = findings_status(cfg / "retro" / "findings.tsv", store)
    lines.append("Findings: no file; scan has never run" if fs is None else f"Findings: {fs[0]} open")
    lines.append(coverage(cfg))
    lp = cfg / "retro" / "retro-log.tsv"
    pre_v3 = lp.exists() and lp.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0] != "\t".join(ledger.COLS)
    bad = ledger.validate(cfg)
    lines.append(f"Ledger: {len(ledger.load_rows(cfg))} rows, {len(bad)} malformed" + (": " + "; ".join(bad[:3]) if bad else ""))
    if pre_v3:
        lines.append("Ledger: pre-v3 ledger moved to retro-log.v2.tsv")
    cdir = cfg / "retro" / "candidates"
    crows = sum(max(0, len(p.read_text(encoding="utf-8", errors="replace").splitlines()) - 1)
                for p in sorted(cdir.glob("*.tsv"))) if cdir.exists() else 0
    cbad = C.validate(cfg)
    lines.append(f"Candidates: {crows} rows, ok" if not cbad
                 else f"Candidates: {crows} rows, {len(cbad)} malformed: " + "; ".join(cbad[:3]))
    s = settings.load(cfg)
    lines.append("Approve-always: " + (", ".join(s["approve_always"]) or "none"))
    bar = s["raised_bar"]
    if store is None:
        parts = [f"{k} in {'every project' if p == '*' else p}" for p, kinds in bar.items() for k in kinds]
    else:
        parts = [k for p in ("*", store) for k in bar.get(p, [])]
    if parts:
        lines.append("Raised bar (logs as candidate instead of proposing): " + ", ".join(parts))
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    ap.add_argument("--store", default=None)
    ap.add_argument("--metrics", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    cfg = a.claude_dir or claude_dir()
    if a.metrics:
        m = metrics(cfg, a.days)
        print(f"Last {m['days']} days: {m['runs']} runs, {m['empty_runs']} empty, {m['runs_unread']} unread")
        print(f"Proposals raised: {m['proposals_raised']} ({m['proposals_per_run']} per run); applied and verified: {m['proposal_conversion']}")
        print("Denied by kind: " + (", ".join(f"{k} {v}" for k, v in m["denial_by_kind"].items()) or "none"))
        print(f"Candidates confirmed: {m['candidate_confirmation']}")
        print(f"Lessons written by retros: {m['lessons_written']}; recurred after writing: {m['lessons_recurred']}")
        t = m["time_to_first_decision_s"]
        print("Median time to first decision: " + ("no decided runs" if t is None else f"{t} s"))
    else:
        print(report(cfg, a.store))
