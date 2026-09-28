"""For every retro run since 2026-09-14 across all projects (a run is detected by its
`journal.py begin` call, so plain-text starts count too): for each AskUserQuestion
whose header starts with 'Proposal', classify where the matching card text
('**Proposal N of M') was emitted relative to the question:
  same-msg     card text block in the same assistant message as the tool call
  prev-msg     card in the immediately preceding assistant message (only thinking/tool between allowed? no: strictly previous assistant msg)
  earlier      card exists earlier in the run but other assistant text/tool msgs came between
  missing      no card text for that N anywhere in the run
Also record: chars of the text block holding the card, and how many chars the card is
from the END of that block (i.e. how much other text sits below it).
"""
import json, sys, re, glob, os

root = os.path.expanduser("~/.claude/projects")
files = glob.glob(os.path.join(root, "*", "*.jsonl"))
out = []
for path in files:
    try:
        if os.path.getmtime(path) < 1789171200:  # 2026-09-14 00:00 UTC approx
            continue
    except OSError:
        continue
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    # A retro run starts with `journal.py begin` (step 0.2), whether the user typed /retro or
    # asked in plain words; the slash-command marker alone missed the plain-text starts.
    def begins_retro(r):
        if r.get("type") != "assistant":
            return False
        for b in r.get("message", {}).get("content", []) or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and \
                    "journal.py begin" in str((b.get("input") or {}).get("command", "")):
                return True
        return False
    retro_idx = [i for i, r in enumerate(rows) if begins_retro(r)]
    if not retro_idx:
        continue
    proj = os.path.basename(os.path.dirname(path)).replace("C--LLM-Projects-Claude-", "")
    for si, start in enumerate(retro_idx):
        end = retro_idx[si + 1] if si + 1 < len(retro_idx) else len(rows)
        ts = (rows[start].get("timestamp") or "")[:16]
        # collect assistant messages in order (skip thinking-only)
        amsgs = []
        for r in rows[start:end]:
            if r.get("type") != "assistant":
                continue
            c = r.get("message", {}).get("content")
            if not isinstance(c, list):
                continue
            blocks = [b for b in c if b.get("type") in ("text", "tool_use")]
            if not blocks:
                continue
            amsgs.append(blocks)
        # flatten with message index
        asks = []
        cards = {}  # N -> list of (msg_i, blocklen, tail_chars)
        for mi, blocks in enumerate(amsgs):
            for b in blocks:
                if b.get("type") == "text":
                    txt = b.get("text", "")
                    for m in re.finditer(r"\*\*Proposal (\d+) of (\d+)", txt):
                        n = int(m.group(1))
                        cards.setdefault(n, []).append((mi, len(txt), len(txt) - m.start()))
                elif b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                    for q in b.get("input", {}).get("questions", []):
                        h = q.get("header", "")
                        mm = re.match(r"Proposal (\d+)", h)
                        if mm:
                            asks.append((int(mm.group(1)), mi, h))
        if not asks and not cards:
            out.append((proj, ts, "-", "no proposals asked or printed", "", ""))
            continue
        for n, mi, h in asks:
            cs = cards.get(n, [])
            if any(c[0] == mi for c in cs):
                loc = "same-msg"
                c = [c for c in cs if c[0] == mi][-1]
            elif any(c[0] == mi - 1 for c in cs):
                loc = "prev-msg"
                c = [c for c in cs if c[0] == mi - 1][-1]
            elif cs:
                loc = "earlier(%d msgs between)" % (mi - cs[-1][0] - 1)
                c = cs[-1]
            else:
                loc = "MISSING"
                c = None
            extra = "" if c is None else f"block={c[1]}ch card_tail={c[2]}ch"
            out.append((proj, ts, f"P{n}", loc, extra, ""))
        for n in cards:
            if not any(a[0] == n for a in asks):
                out.append((proj, ts, f"P{n}", "card printed, never asked", "", ""))

for o in sorted(out, key=lambda x: x[1]):
    print("\t".join(str(x) for x in o))
