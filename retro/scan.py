"""Retro scan: read new transcripts, find the user's corrections, match them to recorded
lessons, recover decisions on past retros. Writes only under <claude dir>/retro/.

--since is for backfills only and re-appends rows for sessions already scanned; routine runs
rely on the watermark.

Usage: python scan.py [--since YYYY-MM-DD] [--dry-run] [--classify-model sonnet]
                      [--match-model opus] [--decisions-model sonnet]
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm  # noqa: E402
import transcripts as T  # noqa: E402

FINDINGS_COLS = ["id", "found", "store", "session", "type", "lesson", "evidence", "confidence", "status", "resolved"]
DECISION_COLS = ["session", "retro_at", "store", "proposed", "decision", "reply_excerpt"]
DORMANT_DAYS = 60

CLASSIFY_PROMPT = """Below are the messages a user sent to an AI coding assistant during one working session, in order. Each is preceded by the tail of the assistant's previous reply, marked PRIOR.

Mark each user message that is a CORRECTION: the user tells the assistant that something it did, said, assumed, or produced was wrong, unwanted, off-target, too much, too little, or needs redoing. Redirections after a wrong assumption count. Pushback on approach counts. A request to explain something more simply counts when PRIOR shows the assistant was technical.

NOT corrections: a revision of content the user asked for where the assistant was not wrong; new requests; approvals ("yes", "go ahead", "approve 1 and 2"); neutral questions; pasted content; greetings.

Reply with JSON only, one entry per message id, in order:
[{"id": 1, "correction": false, "gist": ""}, {"id": 2, "correction": true, "gist": "<8 words: what was wrong>"}]

=== MESSAGES ===
%s
"""

MATCH_PROMPT = """A user corrected an AI coding assistant. Decide whether the correction is a RECURRENCE of an already-recorded lesson: the same class of mistake the lesson exists to prevent, even if the concrete details differ. Be strict: topical overlap is not enough; the lesson must be one that, had it been followed, would have prevented this correction.

Reply with JSON only:
{"match": "<L-number or null>", "confidence": "high|medium|low", "why": "<12 words>"}

=== PROJECT ===
%s
=== ASSISTANT'S PRIOR REPLY (tail) ===
%s
=== CORRECTION ===
%s
=== GIST ===
%s
=== LESSON INDEX ===
%s
"""

DECISION_PROMPT = """Below are retrospectives an AI assistant wrote at the end of sessions, each followed by the user's next message. Classify the user's reply to each retrospective:
- approve-all: approves everything proposed
- approve-some: approves a subset, by number or name
- edit: asks for changes to a proposal before approving
- reject: rejects the proposals
- none: the reply does not address the retrospective (new topic, empty, session ended)

Reply with JSON only: [{"k": 0, "decision": "approve-all"}, ...]

%s
"""


def lesson_index(cfg: Path):
    rows = []
    for p in sorted((cfg / "projects").glob("*/memory/*.md")) if (cfg / "projects").exists() else []:
        if p.name == "MEMORY.md":
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        desc = re.search(r"^description:\s*(.+)$", txt, re.M)
        name = re.search(r"^name:\s*(.+)$", txt, re.M)
        d = (desc.group(1) if desc else name.group(1) if name else txt[:120]).strip().strip('"')
        rows.append((f"mem:{p.parent.parent.name}/{p.stem}", d[:220]))
    cm = cfg / "CLAUDE.md"
    if cm.exists():
        sec = None
        for line in cm.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("## "):
                sec = line[3:].strip()
            elif line.startswith("- ") and sec and sec != "Active projects":
                rows.append((f"global:{sec}", line[2:].strip()[:220]))
    for p in sorted((cfg / "rules").glob("*.md")) if (cfg / "rules").exists() else []:
        txt = p.read_text(encoding="utf-8", errors="replace")
        desc = re.search(r"^description:\s*(.+)$", txt, re.M)
        head = re.search(r"^#+\s*(.+)$", txt, re.M)
        rows.append((f"rule:{p.stem}", (desc.group(1) if desc else head.group(1) if head else "").strip()[:220]))
    return rows


def format_messages(messages):
    parts = []
    for m in messages:
        parts.append(f"PRIOR: {m.get('prior', '')[-600:]}\n[{m['id']}] {m['text'][:700]}")
    return "\n\n".join(parts)


def parse_classification(reply: str, messages):
    items = llm.extract_json(reply)
    if isinstance(items, dict):
        items = next((v for v in items.values() if isinstance(v, list)), None)
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise ValueError("classification reply was not a list of objects")
    valid = {m["id"] for m in messages}
    kept, dropped = [], 0
    for it in items:
        try:
            i = int(it.get("id"))
        except (TypeError, ValueError):
            dropped += 1
            continue
        if i in valid:
            kept.append({"id": i, "correction": bool(it.get("correction")), "gist": str(it.get("gist", ""))[:120]})
        else:
            dropped += 1
    return kept, dropped


def _call_with_retry(model: str, prompt: str) -> str:
    """Call the model; on any error, sleep 20s and try once more. This is the only retry:
    if the second attempt also fails, raise RuntimeError with the last 200 chars of it."""
    try:
        return llm.call(model, prompt)
    except Exception:
        time.sleep(20)
        try:
            return llm.call(model, prompt)
        except Exception as e2:
            raise RuntimeError(str(e2)[-200:]) from e2


def classify(messages, model: str):
    if not messages:
        return [], 0
    prompt = CLASSIFY_PROMPT % format_messages(messages)
    try:
        return parse_classification(_call_with_retry(model, prompt), messages)
    except (ValueError, RuntimeError) as e:
        raise RuntimeError(f"classify failed: {str(e)[-200:]}")


def match(item, index, model: str):
    idx_txt = "\n".join(f"L{i+1} [{k}] {d}" for i, (k, d) in enumerate(index))
    prompt = MATCH_PROMPT % (item["store"], item.get("prior", ""), item["text"], item.get("gist", ""), idx_txt)
    out = {"match_key": None, "confidence": "low", "why": ""}
    try:
        r = llm.extract_json(_call_with_retry(model, prompt))
        if isinstance(r, list):
            r = next((x for x in r if isinstance(x, dict)), None)
        if not isinstance(r, dict):
            raise ValueError("match reply was not an object")
        m = str(r.get("match") or "")
        if m.upper().startswith("L") and m[1:].isdigit() and 1 <= int(m[1:]) <= len(index):
            out["match_key"] = index[int(m[1:]) - 1][0]
        out["confidence"] = str(r.get("confidence", "low"))
        out["why"] = str(r.get("why", ""))[:120]
    except (ValueError, RuntimeError) as e:
        out["why"] = f"error: {str(e)[-200:]}"
    return out


def classify_decisions(retros, model: str):
    if not retros:
        return []
    blocks = []
    for k, r in enumerate(retros):
        blocks.append(f"=== RETRO {k} ===\n{r['reply'][-2500:]}\n=== USER REPLY {k} ===\n{r['next_user'][:500]}")
    try:
        items = llm.extract_json(_call_with_retry(model, DECISION_PROMPT % "\n\n".join(blocks)))
        by = {int(i["k"]): str(i.get("decision", "none")) for i in items if isinstance(i, dict) and "k" in i}
    except (ValueError, RuntimeError, TypeError):
        return []
    allowed = {"approve-all", "approve-some", "edit", "reject", "none"}
    return [by.get(k, "none") if by.get(k) in allowed else "none" for k in range(len(retros))]


def count_proposals(reply: str):
    heads = re.findall(r"^###\s*\d+\.", reply, re.M)
    if heads:
        return len(heads)
    rows = re.findall(r"^\|\s*\d+\s*\|", reply, re.M)
    return len(rows) if rows else ""


def clean(s: str, n: int = 200) -> str:
    return re.sub(r"[\t\r\n]+", " ", s or "")[:n]


def finding_row(fid, found, store, session, kind, lesson, evidence, confidence):
    return {"id": fid, "found": found, "store": store, "session": session, "type": kind, "lesson": lesson,
            "evidence": clean(evidence), "confidence": confidence, "status": "open", "resolved": ""}


def load_findings(path: Path):
    if not path.exists():
        return None, []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    stamp = lines[0].split(":", 1)[1].strip() if lines and lines[0].startswith("# last-scan:") else None
    rows = []
    for line in lines[1:]:
        cols = line.split("\t")
        if cols[0] == "id" or len(cols) < len(FINDINGS_COLS):
            continue
        rows.append(dict(zip(FINDINGS_COLS, cols)))
    return stamp, rows


def _atomic_write(path: Path, text: str):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _chunks(seq, n=10):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def save_findings(path: Path, stamp: str, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = [f"# last-scan: {stamp}", "\t".join(FINDINGS_COLS)]
    out += ["\t".join(str(r.get(c, "")) for c in FINDINGS_COLS) for r in rows]
    _atomic_write(path, "\n".join(out) + "\n")


def next_id(rows):
    n = max((int(r["id"][1:]) for r in rows if r.get("id", "").startswith("F")), default=0)
    return f"F{n + 1:04d}"


def load_state(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"offsets": {}, "last_scan": None}


def save_state(path: Path, state, stamp: str):
    state["last_scan"] = stamp
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(state, indent=1))


def load_decisions(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= len(DECISION_COLS):
            rows.append(dict(zip(DECISION_COLS, cols)))
    return rows


def save_decisions(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = ["\t".join(DECISION_COLS)] + ["\t".join(str(r.get(c, "")) for c in DECISION_COLS) for r in rows]
    _atomic_write(path, "\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--classify-model", default="sonnet")
    ap.add_argument("--match-model", default="opus")
    ap.add_argument("--decisions-model", default="sonnet")
    ap.add_argument("--claude-dir", type=Path, default=None)
    a = ap.parse_args(argv)

    cfg = a.claude_dir or llm.claude_dir()
    rdir = cfg / "retro"
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    today = stamp[:10]
    state = load_state(rdir / "scan-state.json")
    since_ts = datetime.fromisoformat(a.since).timestamp() if a.since else None
    log = []

    # 1. collect transcripts with new bytes
    work = []
    for p in sorted((cfg / "projects").glob("*/*.jsonl")):
        if since_ts is not None:
            if p.stat().st_mtime < since_ts:
                continue
            off = 0
        else:
            off = state["offsets"].get(str(p), 0)
        if p.stat().st_size > off:
            work.append((p, off))

    counts = {"transcripts": len(work), "messages": 0, "corrections": 0, "matched": 0, "invented": 0,
              "skipped": 0, "decisions": 0, "dormant": 0}
    sessions = []
    for p, off in work:
        try:
            recs, new_off = T.read_records(p, off)
        except OSError as e:
            log.append(f"skip unreadable {p}: {e}")
            counts["skipped"] += 1
            continue
        ex = T.extract(recs)
        counts["messages"] += len(ex["messages"])
        sessions.append({"path": p, "new_off": new_off, "store": p.parent.name, "session": p.stem, **ex})
    if a.dry_run:
        for s in sessions:
            print(f"{s['store']}/{s['session'][:8]}: {len(s['messages'])} messages, {len(s['retros'])} retro turns")
        print(f"dry-run: {counts['transcripts']} transcripts, {counts['messages']} messages")
        return 0

    # 2. classify, match
    index = lesson_index(cfg)
    _, rows = load_findings(rdir / "findings.tsv")
    decisions = load_decisions(rdir / "decisions.tsv")
    known = {(d["session"], d["retro_at"]) for d in decisions}

    def process(s):
        try:
            items, dropped = classify(s["messages"], a.classify_model)
        except RuntimeError as e:
            return s, None, 0, str(e)
        return s, items, dropped, None

    for chunk in _chunks(sessions, 10):
        for s, items, dropped, err in llm.run_parallel(process, chunk, workers=2):
            if err:
                log.append(f"skip {s['store']}/{s['session'][:8]}: {err}")
                counts["skipped"] += 1
                continue
            counts["invented"] += dropped
            by_id = {m["id"]: m for m in s["messages"]}
            for it in items:
                if not it["correction"]:
                    continue
                counts["corrections"] += 1
                m = by_id[it["id"]]
                res = match({"store": s["store"], "prior": m["prior"], "text": m["text"], "gist": it["gist"]},
                            index, a.match_model)
                log.append(f"{s['store']}/{s['session'][:8]} #{m['id']} {res['confidence']} {res['match_key']} :: {it['gist']} :: {res['why']}")
                if res["match_key"] and res["confidence"] in ("high", "medium"):
                    store = "global" if res["match_key"].split(":")[0] in ("global", "rule") else s["store"]
                    rows.append(finding_row(next_id(rows), today, store, s["session"], "recur",
                                            res["match_key"], m["text"], res["confidence"]))
                    counts["matched"] += 1
            # decisions
            fresh = [r for r in s["retros"] if (s["session"], r["ts"]) not in known]
            if fresh:
                verdicts = classify_decisions(fresh, a.decisions_model)
                for r, v in zip(fresh, verdicts):
                    decisions.append({"session": s["session"], "retro_at": r["ts"], "store": s["store"],
                                      "proposed": count_proposals(r["reply"]), "decision": v,
                                      "reply_excerpt": clean(r["next_user"], 120)})
                    counts["decisions"] += 1
            state["offsets"][str(s["path"])] = s["new_off"]
            save_findings(rdir / "findings.tsv", stamp, rows)
            save_decisions(rdir / "decisions.tsv", decisions)
            save_state(rdir / "scan-state.json", state, stamp)

    # 3. dormant lessons
    cutoff = datetime.now() - timedelta(days=DORMANT_DAYS)
    recent = {r["lesson"] for r in rows if r["type"] == "recur" and r["found"] >= cutoff.strftime("%Y-%m-%d")}
    open_dormant = {r["lesson"] for r in rows if r["type"] == "dormant" and r["status"] == "open"}
    for key, _ in index:
        if not key.startswith("mem:") or key in recent or key in open_dormant:
            continue
        slug, stem = key[4:].split("/", 1)
        f = cfg / "projects" / slug / "memory" / f"{stem}.md"
        if f.exists() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            rows.append(finding_row(next_id(rows), today, slug, "", "dormant", key, "", ""))
            counts["dormant"] += 1

    save_findings(rdir / "findings.tsv", stamp, rows)
    save_decisions(rdir / "decisions.tsv", decisions)
    save_state(rdir / "scan-state.json", state, stamp)
    with (rdir / "scan.log").open("a", encoding="utf-8") as f:
        f.write(f"\n# scan {stamp}\n" + "\n".join(log) + "\n")
    print(" ".join(f"{k}={v}" for k, v in counts.items()), "|", llm.usage_summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
