"""Run the golden cases: build a fake home per case, replay the transcript, invoke /retro,
grade the output. Usage: python run_evals.py [--case NAME] [--runs N] [--model sonnet] [--skill PATH]"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(SKILL_DIR))
sys.path.insert(0, str(SKILL_DIR / "tests"))
import llm  # noqa: E402
import scan  # noqa: E402
import synth  # noqa: E402
from cases import CASES  # noqa: E402

JUDGE_PROMPT = """Below is a retrospective an AI assistant wrote, and a list of user corrections that occurred in the session. Answer in JSON only: {"quoted": [true, false, ...]} with one boolean per correction, true when the retrospective quotes that correction verbatim or near-verbatim (a distinctive phrase of at least five words from it).

=== CORRECTIONS ===
%s

=== RETROSPECTIVE ===
%s
"""

LEDGER_RELS = ("retro/retro-log.tsv", "retro-log.tsv")


def build_home(case, skill_src: Path):
    root = Path(tempfile.mkdtemp(prefix="retro-eval-", dir=os.path.realpath(tempfile.gettempdir())))
    work = root / "work"
    work.mkdir()
    home = root / "home"
    cfg = home / ".claude"
    slug = synth.slug_of(str(work))
    store = cfg / "projects" / slug / "memory"
    store.mkdir(parents=True)
    shutil.copytree(skill_src, cfg / "skills" / "retro")
    shutil.copy(llm.claude_dir() / ".credentials.json", cfg / ".credentials.json")
    (cfg / "CLAUDE.md").write_text("# Test user\n\n## Machine gotchas\n- Example gotcha line for the sandbox.\n", encoding="utf-8")
    (cfg / "retro").mkdir()
    (cfg / "retro" / "retro-log.tsv").write_text("", encoding="utf-8")
    (cfg / "retro-log.tsv").write_text("", encoding="utf-8")  # pre-edit skill path
    index = []
    for name, desc in case["store"].items():
        (store / f"{name}.md").write_text(f"---\nname: {name}\ndescription: {desc}\nmetadata:\n  type: feedback\n---\n\n{desc}\n", encoding="utf-8")
        index.append(f"- [{name}]({name}.md) - {desc[:60]}")
    (store / "MEMORY.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    rows = []
    for kind, lesson, evidence, conf in case.get("findings", []):
        rows.append(scan.finding_row(scan.next_id(rows), "2026-09-01", slug, "s0", kind,
                                     lesson.format(slug=slug), evidence, conf))
    if rows:
        scan.save_findings(cfg / "retro" / "findings.tsv", "2026-09-01T09:00", rows)
    sid = str(uuid.uuid4())
    synth.write_transcript(cfg, str(work), sid, case["turns"])
    return root, home, cfg, store, slug, sid, work


def run_retro(home: Path, cfg: Path, sid: str, work: Path, model: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_CONFIG_DIR": str(cfg)})
    cmd = ["claude", "-p", "--resume", sid, "--no-session-persistence", "--strict-mcp-config",
           "--setting-sources", "user", "--dangerously-skip-permissions", "--output-format", "json",
           "--model", model, "--max-turns", "30", "/retro"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, cwd=str(work), timeout=900, shell=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:300]}")
    d = json.loads(r.stdout)
    if d.get("is_error"):
        raise RuntimeError(d.get("result", "")[:300])
    return d.get("result", "")


def normalize_quote(s: str) -> str:
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
        s = s.replace(a, b)
    s = s.replace('"', "").replace("'", "")
    return re.sub(r"\s+", " ", s.casefold()).strip()


def grade(case, output: str, store: Path, cfg: Path, before: set, judge_model: str):
    exp = case["expect"]
    checks = {}
    extra = {"judge_model": judge_model, "judge_replies": [], "quote_decisions": {}}
    checks["empty_retro"] = ("Empty retro: nothing durable surfaced" in output) == exp["empty_retro"]
    after = {p.name for p in store.glob("*.md")} - {"MEMORY.md"}
    checks["new_entries"] = len(after - before) == exp["new_entries"]
    if exp.get("cites"):
        checks["cites_existing"] = exp["cites"] in output
    if exp.get("mechanism"):
        checks["proposes_mechanism"] = bool(re.search(r"\b(hook|rule|script)\b", output, re.I))
    if exp.get("findings_addressed"):
        _, rows = scan.load_findings(cfg / "retro" / "findings.tsv")
        done = sum(1 for r in rows if r["status"].startswith(("resolved:", "deferred:")))
        checks["findings_addressed"] = done == exp["findings_addressed"]
    checks["ledger_line"] = any((cfg / p).exists() and (cfg / p).stat().st_size > 0
                                for p in LEDGER_RELS)
    if exp["quotes"]:
        norm_output = normalize_quote(output)
        satisfied = []
        remaining = []
        for q in exp["quotes"]:
            if normalize_quote(q) in norm_output:
                extra["quote_decisions"][q] = "substring"
                satisfied.append(q)
            else:
                remaining.append(q)
        if remaining:
            try:
                reply = llm.call(judge_model, JUDGE_PROMPT % ("\n".join(f"- {q}" for q in remaining), output[:8000]))
                extra["judge_replies"].append(reply)
                j = llm.extract_json(reply)
                flags = j.get("quoted", [])
                for q, ok in zip(remaining, flags):
                    extra["quote_decisions"][q] = "judge"
                    if ok:
                        satisfied.append(q)
            except (ValueError, RuntimeError):
                pass
        checks["quotes_corrections"] = len(satisfied) == len(exp["quotes"])
    return checks, extra


def _stat_key(p: Path):
    if not p.exists():
        return None
    st = p.stat()
    return (st.st_size, st.st_mtime)


def _snapshot_sandbox(store: Path, cfg: Path):
    store_snapshot = {p.name: p.read_text(encoding="utf-8", errors="replace")
                      for p in sorted(store.glob("*.md"))}
    findings_path = cfg / "retro" / "findings.tsv"
    findings_snapshot = findings_path.read_text(encoding="utf-8", errors="replace") if findings_path.exists() else ""
    ledger_snapshot = {}
    for rel in LEDGER_RELS:
        p = cfg / rel
        ledger_snapshot[rel] = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    return store_snapshot, findings_snapshot, ledger_snapshot


def _write_results_atomic(path: Path, data: dict):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--skill", type=Path, default=SKILL_DIR)
    ap.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    a = ap.parse_args(argv)
    names = [a.case] if a.case else list(CASES)

    real_paths = {
        "retro-log.tsv": llm.claude_dir() / "retro-log.tsv",
        "retro/retro-log.tsv": llm.claude_dir() / "retro" / "retro-log.tsv",
        "retro/findings.tsv": llm.claude_dir() / "retro" / "findings.tsv",
    }
    before_state = {name: _stat_key(p) for name, p in real_paths.items()}

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    results_path = out_dir / f"{stamp}.json"

    results = {}
    for name in names:
        case = CASES[name]
        runs = []
        results[name] = runs
        for k in range(a.runs):
            root, home, cfg, store, slug, sid, work = build_home(case, a.skill)
            before = {p.name for p in store.glob("*.md")} - {"MEMORY.md"}
            run_record = {"checks": {}, "output": "", "error": None,
                         "judge_model": a.judge_model, "judge_replies": [], "quote_decisions": {},
                         "store_snapshot": {}, "findings_snapshot": "", "ledger_snapshot": {},
                         "sandbox": None}
            try:
                out = run_retro(home, cfg, sid, work, a.model)
                checks, extra = grade(case, out, store, cfg, before, a.judge_model)
                run_record["output"] = out
                run_record["checks"] = checks
                run_record["judge_replies"] = extra["judge_replies"]
                run_record["quote_decisions"] = extra["quote_decisions"]
            except Exception as e:
                run_record["error"] = str(e)
                run_record["checks"] = {"run_error": False}
                print(f"{name} run {k + 1}: {e}")
            store_snapshot, findings_snapshot, ledger_snapshot = _snapshot_sandbox(store, cfg)
            run_record["store_snapshot"] = store_snapshot
            run_record["findings_snapshot"] = findings_snapshot
            run_record["ledger_snapshot"] = ledger_snapshot
            if a.keep:
                cred = cfg / ".credentials.json"
                if cred.exists():
                    cred.unlink()
                    print(f"deleted credentials from kept sandbox {root}")
                run_record["sandbox"] = str(root)
            else:
                shutil.rmtree(root, ignore_errors=True)
            runs.append(run_record)
            _write_results_atomic(results_path, {"model": a.model, "judge_model": a.judge_model,
                                                 "skill": str(a.skill), "runs_requested": a.runs,
                                                 "timestamp": stamp, "results": results})
        passed = sum(1 for r in runs if r["checks"] and all(r["checks"].values()))
        failed = sorted({c for r in runs for c, ok in r["checks"].items() if not ok})
        print(f"{name:16} {passed}/{len(runs)} runs pass" + (f"   failing checks: {', '.join(failed)}" if failed else ""))

    after_state = {name: _stat_key(p) for name, p in real_paths.items()}
    all_untouched = True
    for name in real_paths:
        untouched = before_state[name] == after_state[name]
        all_untouched = all_untouched and untouched
        print(f"real {name} untouched: {untouched}")

    print("saved", results_path, "|", llm.usage_summary())
    all_ok = all(all(r["checks"].values()) for rs in results.values() for r in rs if r["checks"])
    return 0 if all_ok and all_untouched else 1


if __name__ == "__main__":
    sys.exit(main())
