"""Build synthetic Claude Code transcripts and sandbox homes. Used by tests and evals."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


def slug_of(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def make_records(turns, cwd: str, session_id: str) -> list:
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    recs = []
    parent = None
    for i, (role, text) in enumerate(turns):
        uid = str(uuid.uuid4())
        ts = (t0 + timedelta(minutes=i)).isoformat().replace("+00:00", "Z")
        base = {"type": role, "uuid": uid, "parentUuid": parent, "isSidechain": False,
                "userType": "external", "cwd": cwd, "sessionId": session_id, "version": "2.0.0",
                "timestamp": ts}
        if role == "user":
            base["message"] = {"role": "user", "content": text}
        else:
            base["message"] = {"role": "assistant", "model": "claude-sonnet-5", "id": "msg_" + uid[:8],
                               "type": "message", "stop_reason": "end_turn", "stop_sequence": None,
                               "usage": {"input_tokens": 10, "output_tokens": 5},
                               "content": [{"type": "text", "text": text}]}
        recs.append(base)
        parent = uid
    return recs


def write_transcript(cfg: Path, cwd: str, session_id: str, turns) -> Path:
    d = cfg / "projects" / slug_of(cwd)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{session_id}.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in make_records(turns, cwd, session_id):
            f.write(json.dumps(r) + "\n")
    return p
