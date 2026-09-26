"""Retro write journal, soft delete, undo. Everything under ~/.claude/retro/{journal,proposals,trash}.

Usage: python journal.py [--claude-dir PATH] begin --project P
       | snapshot --run R --path F --kind K --proposal N | commit --run R --path F
       | delete --run R --path F --kind K --proposal N | undo R | restore R NAME | purge [--days 30]
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
from llm import claude_dir  # noqa: E402


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _jpath(cfg: Path, run_id: str) -> Path:
    return cfg / "retro" / "journal" / f"{run_id}.json"


def load(cfg: Path, run_id: str) -> dict:
    p = _jpath(cfg, run_id)
    if not p.exists():
        raise RuntimeError(f"no journal for run {run_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save(cfg: Path, j: dict):
    p = _jpath(cfg, j["run_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(j, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def begin(cfg: Path, project: str) -> str:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    (cfg / "retro" / "proposals" / run_id).mkdir(parents=True, exist_ok=True)
    _save(cfg, {"run_id": run_id, "project": project, "started_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "reverted_at": None, "writes": []})
    return run_id


def _read(path: Path):
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def snapshot(cfg: Path, run_id: str, path: Path, kind: str, proposal):
    j = load(cfg, run_id)
    before = _read(Path(path))
    j["writes"].append({"path": str(Path(path)), "kind": kind, "proposal": int(proposal),
                        "before": before, "before_sha": None if before is None else sha(before),
                        "after_sha": None, "deleted": False, "trash": None})
    _save(cfg, j)


def commit(cfg: Path, run_id: str, path: Path):
    j = load(cfg, run_id)
    target = str(Path(path))
    for w in reversed(j["writes"]):
        if w["path"] == target and w["after_sha"] is None and not w["deleted"]:
            after = _read(Path(path))
            w["after_sha"] = None if after is None else sha(after)
            _save(cfg, j)
            return
    raise RuntimeError(f"no open snapshot for {target}")


def delete(cfg: Path, run_id: str, path: Path, kind: str, proposal) -> Path:
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"cannot delete missing file {path}")
    j = load(cfg, run_id)
    tdir = cfg / "retro" / "trash" / run_id
    tdir.mkdir(parents=True, exist_ok=True)
    dest = tdir / f"{len(j['writes'])}-{path.name}"
    before = _read(path)
    shutil.move(str(path), str(dest))
    j["writes"].append({"path": str(path), "kind": kind, "proposal": int(proposal), "before": before,
                        "before_sha": sha(before), "after_sha": None, "deleted": True, "trash": str(dest)})
    _save(cfg, j)
    return dest


def undo(cfg: Path, run_id: str) -> list:
    j = load(cfg, run_id)
    if j.get("reverted_at"):
        raise RuntimeError(f"run {run_id} already reverted")
    todo = []
    for w in j["writes"]:
        p = Path(w["path"])
        if w.get("restored"):
            continue
        if w["deleted"]:
            if p.exists():
                raise RuntimeError(f"refused: {p} exists again; restore it by hand")
            if not Path(w["trash"]).exists():
                raise RuntimeError(f"refused: trash copy for {p} is missing")
        else:
            cur = _read(p)
            cur_sha = None if cur is None else sha(cur)
            if w["after_sha"] is None:
                if cur_sha == w["before_sha"]:
                    continue
                raise RuntimeError(f"refused: {p} changed since the retro touched it")
            if cur_sha != w["after_sha"]:
                raise RuntimeError(f"refused: {p} changed since the retro touched it")
        todo.append(w)
    msgs = []
    for w in reversed(todo):
        p = Path(w["path"])
        if w["deleted"]:
            shutil.move(w["trash"], str(p))
            msgs.append(f"restored {p} from trash")
        elif w["before"] is None:
            if p.exists():
                p.unlink()
            msgs.append(f"removed {p} (created by the retro)")
        else:
            p.write_text(w["before"], encoding="utf-8")
            msgs.append(f"restored {p} to its earlier content")
    j["reverted_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _save(cfg, j)
    n = ledger.mark_reverted(cfg, run_id)
    msgs.append(f"{n} ledger rows marked reverted")
    return msgs


def restore(cfg: Path, run_id: str, name: str) -> Path:
    j = load(cfg, run_id)
    for w in j["writes"]:
        if w["deleted"] and Path(w["path"]).name == name:
            dest = Path(w["path"])
            if dest.exists():
                raise RuntimeError(f"refused: {dest} exists")
            if not Path(w["trash"]).exists():
                raise RuntimeError(f"trash copy missing for {name}; purged?")
            shutil.move(w["trash"], str(dest))
            w["restored"] = True
            _save(cfg, j)
            return dest
    raise RuntimeError(f"{name} not in trash for run {run_id}")


def purge(cfg: Path, days: int = 30) -> dict:
    cutoff = time.time() - days * 86400
    out = {"trash": 0, "journals": 0}
    tdir = cfg / "retro" / "trash"
    if tdir.exists():
        for d in tdir.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                out["trash"] += 1
    jdir = cfg / "retro" / "journal"
    if jdir.exists():
        for p in jdir.glob("*.json"):
            if p.stat().st_mtime < cutoff:
                p.unlink()
                out["journals"] += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("begin")
    b.add_argument("--project", required=True)
    s = sub.add_parser("snapshot")
    for opt in ("--run", "--path", "--kind", "--proposal"):
        s.add_argument(opt, required=True)
    c = sub.add_parser("commit")
    c.add_argument("--run", required=True)
    c.add_argument("--path", required=True)
    d = sub.add_parser("delete")
    for opt in ("--run", "--path", "--kind", "--proposal"):
        d.add_argument(opt, required=True)
    u = sub.add_parser("undo")
    u.add_argument("run")
    r = sub.add_parser("restore")
    r.add_argument("run")
    r.add_argument("name")
    p = sub.add_parser("purge")
    p.add_argument("--days", type=int, default=30)
    a = ap.parse_args(argv)
    cfg = a.claude_dir or claude_dir()
    try:
        if a.cmd == "begin":
            print(begin(cfg, a.project))
        elif a.cmd == "snapshot":
            snapshot(cfg, a.run, Path(a.path), a.kind, a.proposal)
            print("snapshot taken")
        elif a.cmd == "commit":
            commit(cfg, a.run, Path(a.path))
            print("committed")
        elif a.cmd == "delete":
            print(f"moved to {delete(cfg, a.run, Path(a.path), a.kind, a.proposal)}")
        elif a.cmd == "undo":
            print("\n".join(undo(cfg, a.run)))
        elif a.cmd == "restore":
            print(f"restored {restore(cfg, a.run, a.name)}")
        elif a.cmd == "purge":
            print(json.dumps(purge(cfg, a.days)))
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
