"""Retro scan: read new transcripts, find the user's corrections, match them to recorded
lessons, recover decisions on past retros. Writes only under <claude dir>/retro/.

--since is for backfills only and re-appends rows for sessions already scanned; routine runs
rely on the watermark.

Usage: python scan.py [--since YYYY-MM-DD] [--dry-run] [--classify-model sonnet]
                      [--match-model opus] [--decisions-model sonnet] [--background]
       python scan.py --session PATH
       python scan.py --resolve FID --status S [--reason R]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidates as C  # noqa: E402
import journal  # noqa: E402
import llm  # noqa: E402
import settings  # noqa: E402
import transcripts as T  # noqa: E402

FINDINGS_COLS = ["id", "found", "store", "session", "type", "lesson", "evidence", "confidence", "status", "resolved", "reason"]
DECISION_COLS = ["session", "retro_at", "store", "proposed", "decision", "reply_excerpt"]
DORMANT_DAYS = 60
FINDING_STATUSES = ("open", "denied", "no-decision")
FINDING_STATUS_PREFIXES = ("resolved:", "deferred:")
LOCK_STALE_SECONDS = 2 * 3600

CLASSIFY_PROMPT = """Below are the messages a user sent to an AI coding assistant during one working session, in order. Each is preceded by the tail of the assistant's previous reply, marked PRIOR.

PART 1. Mark each user message that is a CORRECTION: the user tells the assistant that something it did, said, assumed, or produced was wrong, unwanted, off-target, too much, too little, or needs redoing. Redirections after a wrong assumption count. Pushback on approach counts. A request to explain something more simply counts when PRIOR shows the assistant was technical.

NOT corrections: a revision of content the user asked for where the assistant was not wrong; new requests; approvals ("yes", "go ahead", "approve 1 and 2"); neutral questions; pasted content; greetings.

PART 2. List at most three CANDIDATE observations about the session that are not corrections, each in exactly one of these categories:
- repeat-manual: the same multi-step sequence was performed by hand more than once
- revisited: a decision was remade or a question re-asked that an earlier turn had settled
- rework-loop: the same artifact was revised in three or more rounds
- tool-friction: repeated failed commands, permission prompts, or retries on the same action
- time-sink: a task took far more turns than its size suggests
A single occurrence of hand-done multi-step work, a re-asked question, or a friction event qualifies with count 1; repetition raises count.

"count" is the number of repetitions or rounds you can point to (1 if it happened once). "key" is a short stable label another reader would write the same way for the same pattern: 3 to 5 lower-case nouns, artifact first then action, no verbs or adjectives, for example `status memo manual assembly`. Omit the list when nothing qualifies.

Reply with JSON only:
{"messages": [{"id": 1, "correction": false, "gist": ""}, {"id": 2, "correction": true, "gist": "<8 words: what was wrong>"}],
 "candidates": [{"category": "rework-loop", "key": "<label>", "summary": "<20 words: what happened>", "count": 3}]}

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


def predates_lesson(cfg: Path, key: str, session_id: str, ts: str) -> bool:
    """True when a correction cannot be a recurrence of a memory lesson: it comes from the
    session that created the file (frontmatter originSessionId) or is older than the file."""
    if not key.startswith("mem:"):
        return False
    slug, stem = key[4:].split("/", 1)
    f = cfg / "projects" / slug / "memory" / f"{stem}.md"
    if not f.exists():
        return False
    origin = re.search(r"^\s*originSessionId:\s*(\S+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
    if origin and origin.group(1).strip('"') == session_id:
        return True
    try:
        msg = datetime.fromisoformat(ts[:19]).replace(tzinfo=timezone.utc)
        st = f.stat()
        # Linux has no st_birthtime and its st_ctime is the metadata-change time, so an edited
        # lesson file reads as newly created there and corrections older than the edit are
        # wrongly treated as predating the lesson.
        created = datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_ctime), tz=timezone.utc)
        return msg < created
    except (ValueError, OSError):
        return False


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


def _parse_candidates(raw):
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict) or c.get("category") not in C.CATEGORIES:
            continue
        try:
            n = max(1, int(c.get("count", 1)))
        except (TypeError, ValueError):
            n = 1
        key = C.normalize(str(c.get("key", "")))
        if not key:
            continue
        out.append({"category": c["category"], "key": key, "summary": str(c.get("summary", ""))[:200], "count": n})
    return out[:3]


def parse_classification(reply: str, messages):
    data = llm.extract_json(reply)
    cands = []
    if isinstance(data, dict):
        cands = _parse_candidates(data.get("candidates"))
        items = data.get("messages")
        if items is None:
            items = next((v for v in data.values() if isinstance(v, list)), None)
    else:
        items = data
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
    return kept, dropped, cands


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
        return [], 0, []
    prompt = CLASSIFY_PROMPT % format_messages(messages)
    try:
        return parse_classification(_call_with_retry(model, prompt), messages)
    except (ValueError, RuntimeError) as e:
        raise RuntimeError(f"classify failed: {str(e)[-200:]}")


def trim_to_budget(messages, budget_chars: int):
    kept = list(messages)
    truncated = False
    while len(kept) > 1 and sum(len(m["text"]) + len(m.get("prior", "")) for m in kept) > budget_chars:
        kept.pop(0)
        truncated = True
    return kept, truncated


def is_hard(cand) -> bool:
    return cand["category"] in ("rework-loop", "repeat-manual") and int(cand.get("count", 1)) >= 3


def reopen_finding(cfg: Path, rows, fid: str, reason: str):
    """Set a finding back to open, in the caller's rows and on disk: the history scan saves through
    merge_findings, which keeps the disk row, so an in-memory change alone would be lost there."""
    def apply(r):
        r["status"], r["resolved"], r["reason"] = "open", "", clean(reason, 200)
    for r in rows:
        if r["id"] == fid:
            apply(r)
    fpath = cfg / "retro" / "findings.tsv"
    stamp, disk = load_findings(fpath)
    hit = [r for r in disk if r["id"] == fid]
    if hit:
        for r in hit:
            apply(r)
        save_findings(fpath, stamp or datetime.now().strftime("%Y-%m-%dT%H:%M"), disk)


def record_candidates(cfg: Path, store: str, cands, today: str, rows):
    out = []
    for c in cands:
        row, confirmed = C.log(cfg, store, c["category"], c["key"], c["summary"], today)
        hard = is_hard(c) and row["status"] == "open"
        key = f"cand:{row['category']}/{row['key']}"
        fid = ""
        existing = next((r for r in rows if r["lesson"] == key and r["type"] == "candidate"), None)
        # A candidate the retro parked ("deferred: await a repeat") comes back on its next sighting.
        # Until 2026-09-23 nothing did this: log() confirms only open rows, and a raised candidate
        # sits at "proposed", so 17 parked candidates could never be raised again.
        if row["status"] == "proposed" and (existing is None or existing["status"].startswith("deferred:")):
            if existing is not None:
                reopen_finding(cfg, rows, existing["id"], f"seen again {today}, after {existing['status']}")
            confirmed = True
        if confirmed or hard:
            if existing is None:
                fid = next_id(rows)
                rows.append(finding_row(fid, today, store, "", "candidate", key, row["summary"],
                                        "high" if hard else "medium"))
            else:
                fid = existing["id"]
            C.set_status(cfg, store, row["category"], row["key"], "proposed")
        out.append({"category": row["category"], "key": row["key"], "summary": row["summary"], "count": row["count"],
                    "confirmed": bool(confirmed), "hard": bool(hard), "finding_id": fid, "status": row["status"] if not fid else "proposed"})
    return out


def set_status(cfg: Path, fid: str, status: str, reason: str = "") -> bool:
    if status not in FINDING_STATUSES and not status.startswith(FINDING_STATUS_PREFIXES):
        raise ValueError(f"unknown status {status!r}; expected one of {', '.join(FINDING_STATUSES)} "
                         f"or a {' / '.join(FINDING_STATUS_PREFIXES)} prefix")
    rdir = cfg / "retro"
    stamp, rows = load_findings(rdir / "findings.tsv")
    hit = False
    for r in rows:
        if r["id"] == fid:
            r["status"] = status
            r["resolved"] = datetime.now().strftime("%Y-%m-%d")
            r["reason"] = clean(reason, 200)
            hit = True
    if hit:
        save_findings(rdir / "findings.tsv", stamp or datetime.now().strftime("%Y-%m-%dT%H:%M"), rows)
    return hit


def open_findings(cfg: Path, project: str):
    """The retro's step 2 list: open recur and candidate findings for a project and for global. The
    second list is the project's dormant lessons whose lesson has not matched a correction since the
    dormant row was written; a store-delete at cap takes its entry from there."""
    _, rows = load_findings(cfg / "retro" / "findings.tsv")
    open_rows = [r for r in rows if r["status"] == "open" and r["type"] != "dormant"
                 and r["store"] in (project, "global")]
    dormant = [r for r in rows if r["type"] == "dormant" and r["status"] == "open" and r["store"] == project
               and not any(x["type"] == "recur" and x["lesson"] == r["lesson"] and x["found"] > r["found"] for x in rows)]
    return open_rows, dormant


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
            "evidence": clean(evidence), "confidence": confidence, "status": "open", "resolved": "", "reason": ""}


def load_findings(path: Path):
    if not path.exists():
        return None, []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    stamp = lines[0].split(":", 1)[1].strip() if lines and lines[0].startswith("# last-scan:") else None
    rows = []
    for line in lines[1:]:
        cols = line.split("\t")
        if cols[0] == "id" or len(cols) < len(FINDINGS_COLS) - 1:
            continue
        cols = (cols + [""] * len(FINDINGS_COLS))[: len(FINDINGS_COLS)]
        rows.append(dict(zip(FINDINGS_COLS, cols)))
    return stamp, rows


def _atomic_write(path: Path, text: str):
    # the pid suffix keeps a session scan and a history scan off each other's temp file
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
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


def merge_findings(path: Path, stamp: str, rows, persisted: set):
    """Save without clobbering another writer. The long history scan holds its rows in memory for
    up to an hour, so before each write it rereads the file, keeps every row on disk (a session
    scan's rows, and any --resolve made meanwhile), and appends only the rows it has not written
    yet, matched on finding id. An id already taken on disk is reassigned."""
    _, disk = load_findings(path)
    out = list(disk)
    on_disk = {r["id"] for r in out}
    for r in rows:
        if r["id"] in persisted:
            continue
        if r["id"] in on_disk:
            r["id"] = next_id(out)
        out.append(r)
        on_disk.add(r["id"])
        persisted.add(r["id"])
    save_findings(path, stamp, out)


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


def scan_session(cfg: Path, path: Path, models: dict, budget_chars: int) -> dict:
    """Classify one transcript from byte 0, record findings and candidates, advance its bookmark,
    and return what the retro needs as a dict."""
    rdir = cfg / "retro"
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    today = stamp[:10]
    store = path.parent.name
    result = {"session": path.stem, "store": store, "truncated": False, "messages_seen": 0,
              "corrections": [], "candidates": [], "error": None}
    lock = rdir / "scan.lock"
    if lock.exists():
        if time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS:
            result["error"] = "history scan in progress; session scan skipped"
            return result
        lock.unlink(missing_ok=True)
    try:
        recs, new_off = T.read_records(path, 0)
    except OSError as e:
        result["error"] = f"cannot read transcript: {e}"
        return result
    ex = T.extract(recs)
    messages, truncated = trim_to_budget(ex["messages"], budget_chars)
    result["truncated"] = truncated
    result["messages_seen"] = len(messages)
    _, rows = load_findings(rdir / "findings.tsv")
    try:
        items, dropped, cands = classify(messages, models["classify"])
    except RuntimeError as e:
        result["error"] = str(e)
        return result
    index = lesson_index(cfg)
    by_id = {m["id"]: m for m in messages}
    for it in items:
        if not it["correction"]:
            continue
        m = by_id[it["id"]]
        res = match({"store": store, "prior": m["prior"], "text": m["text"], "gist": it["gist"]}, index, models["match"])
        entry = {"id": m["id"], "text": m["text"], "gist": it["gist"], "match_key": res["match_key"],
                 "confidence": res["confidence"], "why": res["why"], "predates": False, "finding_id": ""}
        if res["match_key"] and res["confidence"] in ("high", "medium"):
            if predates_lesson(cfg, res["match_key"], path.stem, m["ts"]):
                entry["predates"] = True
            else:
                fstore = "global" if res["match_key"].split(":")[0] in ("global", "rule") else store
                fid = next_id(rows)
                rows.append(finding_row(fid, today, fstore, path.stem, "recur", res["match_key"], m["text"], res["confidence"]))
                entry["finding_id"] = fid
        result["corrections"].append(entry)
    result["candidates"] = record_candidates(cfg, store, cands, today, rows)
    save_findings(rdir / "findings.tsv", stamp, rows)
    state = load_state(rdir / "scan-state.json")
    state["offsets"][str(path)] = new_off
    # last_scan is the history coverage watermark, which health.py reports; a session scan covers
    # one transcript, not the history, so it leaves that value alone.
    save_state(rdir / "scan-state.json", state, state.get("last_scan"))
    with (rdir / "scan.log").open("a", encoding="utf-8") as f:
        f.write(f"\n# session {stamp} {store}/{path.stem[:8]} messages={len(messages)} truncated={truncated} "
                f"corrections={len(result['corrections'])} candidates={len(result['candidates'])}\n")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--classify-model", default="sonnet")
    ap.add_argument("--match-model", default="opus")
    ap.add_argument("--decisions-model", default="sonnet")
    ap.add_argument("--claude-dir", type=Path, default=None)
    ap.add_argument("--session", type=Path, default=None, help="scan one transcript and print JSON for the retro")
    ap.add_argument("--background", action="store_true", help="re-launch detached and return at once")
    ap.add_argument("--resolve", default=None, help="finding id to update")
    ap.add_argument("--status", default=None)
    ap.add_argument("--reason", default="")
    ap.add_argument("--open", default=None, metavar="PROJECT",
                    help="list a project's open findings (plus global) and its dormant lessons; no model calls")
    a = ap.parse_args(argv)

    cfg = a.claude_dir or llm.claude_dir()
    rdir = cfg / "retro"
    if a.open:
        open_rows, dormant = open_findings(cfg, a.open)
        print(f"Open findings for {a.open} and global:")
        for r in open_rows:
            print(f"{r['id']}\t{r['type']}\t{r['confidence']}\t{r['lesson']}\t{r['evidence']}")
        if not open_rows:
            print("none")
        print(f"Dormant lessons in {a.open} (no match in {DORMANT_DAYS} days; delete candidates):")
        for r in dormant:
            print(f"{r['id']}\t{r['lesson']}")
        if not dormant:
            print("none")
        return 0
    if a.resolve:
        if not a.status:
            print("--resolve needs --status", file=sys.stderr)
            return 2
        try:
            ok = set_status(cfg, a.resolve, a.status, a.reason)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"{a.resolve} -> {a.status}" if ok else f"{a.resolve} not found")
        return 0 if ok else 1
    if a.background:
        args = [arg for arg in (argv if argv is not None else sys.argv[1:]) if arg != "--background"]
        rdir.mkdir(parents=True, exist_ok=True)
        log_f = (rdir / "scan.log").open("a", encoding="utf-8")
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args], stdout=log_f, stderr=log_f,
                         stdin=subprocess.DEVNULL, creationflags=flags, start_new_session=True)
        print("scan started in the background; progress in " + str(rdir / "scan.log"))
        return 0
    if a.session:
        budget = int(settings.load(cfg)["session_budget_chars"])
        out = scan_session(cfg, a.session.resolve(), {"classify": a.classify_model, "match": a.match_model}, budget)
        print(json.dumps(out, indent=1))
        return 0 if not out["error"] else 1
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    today = stamp[:10]
    state = load_state(rdir / "scan-state.json")
    since_ts = datetime.fromisoformat(a.since).timestamp() if a.since else None
    log = []

    # A lock so a --session scan started mid-run does not double-count the same transcript. It is
    # taken before the transcripts are read, not after: reading every file in a 90-day range takes
    # minutes, and a session scan starting inside that window must see the lock. A dry run reads
    # and writes nothing, so it takes no lock.
    lock = rdir / "scan.lock"
    if not a.dry_run:
        rdir.mkdir(parents=True, exist_ok=True)
        lock.write_text(f"pid {os.getpid()} started {stamp}\n", encoding="utf-8")
    try:
        # 1. collect transcripts with new bytes
        work = []
        for p in sorted((cfg / "projects").glob("*/*.jsonl")):
            # a transcript with a stored bookmark has been scanned before, so a --since re-read of it
            # is not a fresh sighting: its candidates were already logged and must not be logged twice
            first_sighting = state["offsets"].get(str(p), 0) == 0
            if since_ts is not None:
                if p.stat().st_mtime < since_ts:
                    continue
                off = 0
            else:
                off = state["offsets"].get(str(p), 0)
            if p.stat().st_size > off:
                work.append((p, off, first_sighting))

        counts = {"transcripts": len(work), "messages": 0, "corrections": 0, "matched": 0, "invented": 0,
                  "skipped": 0, "predates": 0, "decisions": 0, "dormant": 0}
        sessions = []
        for p, off, first_sighting in work:
            try:
                recs, new_off = T.read_records(p, off)
            except OSError as e:
                log.append(f"skip unreadable {p}: {e}")
                counts["skipped"] += 1
                continue
            ex = T.extract(recs)
            counts["messages"] += len(ex["messages"])
            sessions.append({"path": p, "new_off": new_off, "store": p.parent.name, "session": p.stem,
                             "fresh": first_sighting, **ex})
        if a.dry_run:
            for s in sessions:
                print(f"{s['store']}/{s['session'][:8]}: {len(s['messages'])} messages, {len(s['retros'])} retro turns")
            print(f"dry-run: {counts['transcripts']} transcripts, {counts['messages']} messages")
            return 0

        # 2. classify, match
        index = lesson_index(cfg)
        _, rows = load_findings(rdir / "findings.tsv")
        persisted = {r["id"] for r in rows}
        decisions = load_decisions(rdir / "decisions.tsv")
        known = {(d["session"], d["retro_at"]) for d in decisions}

        def process(s):
            try:
                items, dropped, cands = classify(s["messages"], a.classify_model)
            except RuntimeError as e:
                return s, None, 0, [], str(e)
            return s, items, dropped, cands, None

        for chunk in _chunks(sessions, 10):
            for s, items, dropped, cands, err in llm.run_parallel(process, chunk, workers=2):
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
                        if predates_lesson(cfg, res["match_key"], s["session"], m["ts"]):
                            log.append(f"  skipped: correction predates lesson {res['match_key']}")
                            counts["predates"] += 1
                            continue
                        store = "global" if res["match_key"].split(":")[0] in ("global", "rule") else s["store"]
                        rows.append(finding_row(next_id(rows), today, store, s["session"], "recur",
                                                res["match_key"], m["text"], res["confidence"]))
                        counts["matched"] += 1
                if s["fresh"]:
                    record_candidates(cfg, s["store"], cands, today, rows)
                # decisions
                fresh_retros = [r for r in s["retros"] if (s["session"], r["ts"]) not in known]
                if fresh_retros:
                    verdicts = classify_decisions(fresh_retros, a.decisions_model)
                    for r, v in zip(fresh_retros, verdicts):
                        decisions.append({"session": s["session"], "retro_at": r["ts"], "store": s["store"],
                                          "proposed": count_proposals(r["reply"]), "decision": v,
                                          "reply_excerpt": clean(r["next_user"], 120)})
                        counts["decisions"] += 1
                state["offsets"][str(s["path"])] = s["new_off"]
                merge_findings(rdir / "findings.tsv", stamp, rows, persisted)
                save_decisions(rdir / "decisions.tsv", decisions)
                save_state(rdir / "scan-state.json", state, stamp)
                # a first scan can outlast LOCK_STALE_SECONDS; refresh the lock so a session scan
                # does not treat it as abandoned and delete it while this one is still running
                lock.touch()

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

        # 4. expiry and purge
        cdir = rdir / "candidates"
        if cdir.exists():
            for p in cdir.glob("*.tsv"):
                counts["expired"] = counts.get("expired", 0) + C.expire(cfg, p.stem, today)
        counts["purged"] = sum(journal.purge(cfg, 30).values())

        merge_findings(rdir / "findings.tsv", stamp, rows, persisted)
        save_decisions(rdir / "decisions.tsv", decisions)
        save_state(rdir / "scan-state.json", state, stamp)
        with (rdir / "scan.log").open("a", encoding="utf-8") as f:
            f.write(f"\n# scan {stamp}\n" + "\n".join(log) + "\n")
        print(" ".join(f"{k}={v}" for k, v in counts.items()), "|", llm.usage_summary())
        return 0
    finally:
        if not a.dry_run:
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
