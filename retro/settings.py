"""Retro settings: ~/.claude/retro/settings.json. Standard library only.

Usage: python settings.py [--claude-dir PATH] init | show | set-always KIND on|off
       | reset-bar KIND [PROJECT] | mark-first-run | set-history SINCE|skip

approve_always is one list of kinds. raised_bar is per project, {project: [kinds]}; a v3 file
holding a plain list is read as raised for every project under the key "*".
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import claude_dir  # noqa: E402

KINDS = ("store-write", "store-delete", "global-line", "rule-skill-hook", "other-file")
DEFAULTS = {
    "version": 3,
    "approve_always": [],
    "raised_bar": {},
    "first_run_done": False,
    "history_scan": {"asked": False, "since": None},
    "session_budget_chars": 48000,
}


def path(cfg: Path) -> Path:
    return cfg / "retro" / "settings.json"


def load(cfg: Path) -> dict:
    s = json.loads(json.dumps(DEFAULTS))
    p = path(cfg)
    if p.exists():
        try:
            s.update(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    bar = s["raised_bar"]
    if isinstance(bar, list):
        s["raised_bar"] = {"*": list(bar)} if bar else {}
    return s


def save(cfg: Path, s: dict):
    merged = json.loads(json.dumps(DEFAULTS))
    merged.update(s)
    p = path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(merged, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _check(kind: str):
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {', '.join(KINDS)}")


def is_always(cfg: Path, kind: str) -> bool:
    _check(kind)
    return kind in load(cfg)["approve_always"]


def set_always(cfg: Path, kind: str, on: bool):
    _check(kind)
    s = load(cfg)
    kinds = [k for k in s["approve_always"] if k != kind]
    if on:
        kinds.append(kind)
    s["approve_always"] = kinds
    save(cfg, s)


def is_raised(cfg: Path, kind: str, project: str) -> bool:
    _check(kind)
    bar = load(cfg)["raised_bar"]
    return kind in bar.get("*", []) or kind in bar.get(project, [])


def set_bar(cfg: Path, kind: str, raised: bool, project):
    """Raise or reset the bar for one kind in one project. A reset with project None clears the
    kind under every project, the legacy "*" entry included."""
    _check(kind)
    if raised and project is None:
        raise ValueError("a bar is raised for one project")
    s = load(cfg)
    bar = s["raised_bar"]
    for p in (list(bar) if project is None else [project]):
        kinds = [k for k in bar.get(p, []) if k != kind]
        if raised:
            kinds.append(kind)
        if kinds:
            bar[p] = kinds
        else:
            bar.pop(p, None)
    s["raised_bar"] = bar
    save(cfg, s)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude-dir", type=Path, default=None)
    ap.add_argument("cmd", choices=["init", "show", "set-always", "reset-bar", "mark-first-run", "set-history"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    cfg = a.claude_dir or claude_dir()
    if a.cmd == "init":
        save(cfg, load(cfg))
        print(str(path(cfg)))
    elif a.cmd == "show":
        print(json.dumps(load(cfg), indent=1))
    elif a.cmd == "set-always":
        if len(a.args) != 2 or a.args[1] not in ("on", "off"):
            print("usage: set-always KIND on|off", file=sys.stderr)
            return 2
        try:
            set_always(cfg, a.args[0], a.args[1] == "on")
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{a.args[0]} approve-always {a.args[1]}")
    elif a.cmd == "reset-bar":
        project = a.args[1] if len(a.args) > 1 else None
        try:
            set_bar(cfg, a.args[0], False, project)
        except IndexError:
            print("usage: reset-bar KIND [PROJECT]", file=sys.stderr)
            return 2
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{a.args[0]} bar reset " + (f"in {project}" if project else "in every project"))
    elif a.cmd == "mark-first-run":
        s = load(cfg)
        s["first_run_done"] = True
        save(cfg, s)
        print("first run marked done")
    elif a.cmd == "set-history":
        if not a.args:
            print("usage: set-history SINCE|skip", file=sys.stderr)
            return 2
        s = load(cfg)
        s["history_scan"] = {"asked": True, "since": None if a.args[0] == "skip" else a.args[0]}
        save(cfg, s)
        print(json.dumps(s["history_scan"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
