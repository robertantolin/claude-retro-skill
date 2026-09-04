"""Read Claude Code session transcripts (JSONL) for the retro scan."""
import json
import re
from pathlib import Path

RETRO_MARK = "<command-name>/retro</command-name>"
EXCLUDE = ("<command-name>", "<local-command", "<bash-stdout>", "<bash-stderr>")


def slug_of(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def read_records(path: Path, offset: int = 0):
    recs = []
    with path.open("rb") as f:
        f.seek(offset)
        data = f.read()
    last_nl = data.rfind(b"\n")
    if last_nl == -1:
        return [], offset
    for line in data[:last_nl].split(b"\n"):
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line.decode("utf-8", errors="replace")))
        except json.JSONDecodeError:
            continue
    return recs, offset + last_nl + 1


def _blocks(rec):
    c = (rec.get("message") or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []


def text_of(rec) -> str:
    return "".join(b.get("text", "") for b in _blocks(rec) if b.get("type") == "text")


def qualifies(rec) -> bool:
    if rec.get("type") != "user" or rec.get("isMeta"):
        return False
    blocks = _blocks(rec)
    if not any(b.get("type") == "text" for b in blocks) or any(b.get("type") == "tool_result" for b in blocks):
        return False
    t = text_of(rec).strip()
    return bool(t) and not t.startswith("[Request interrupted") and not any(x in t for x in EXCLUDE)


def _is_retro(rec) -> bool:
    return rec.get("type") == "user" and not rec.get("isMeta") and RETRO_MARK in text_of(rec)


def extract(records) -> dict:
    messages, retros = [], []
    prior = ""
    n = 0
    i = 0
    while i < len(records):
        rec = records[i]
        if rec.get("type") == "assistant":
            t = text_of(rec)
            if t:
                prior = (prior + t)[-600:]
        elif _is_retro(rec):
            reply = []
            j = i + 1
            while j < len(records) and not qualifies(records[j]):
                if records[j].get("type") == "assistant":
                    reply.append(text_of(records[j]))
                j += 1
            retros.append({"ts": rec.get("timestamp", "")[:16], "reply": "".join(reply),
                           "next_user": text_of(records[j]).strip() if j < len(records) else "",
                           "ordinal": len(retros) + 1})
            prior = ""
        elif qualifies(rec):
            n += 1
            messages.append({"id": n, "uuid": rec.get("uuid", ""), "ts": rec.get("timestamp", "")[:19],
                             "text": text_of(rec).strip()[:700], "prior": prior})
            prior = ""
        i += 1
    return {"messages": messages, "retros": retros}
