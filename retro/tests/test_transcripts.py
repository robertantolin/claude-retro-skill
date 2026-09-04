import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import transcripts as T  # noqa: E402
import synth  # noqa: E402


def test_slug_rule():
    assert T.slug_of(r"C:\Projects\Client Alpha\newsletter") == "C--Projects-Client-Alpha-newsletter"
    assert T.slug_of(r"C:\Users\me\.claude") == "C--Users-me--claude"


def test_extract_keeps_real_user_messages_and_prior(tmp_path):
    sid = str(uuid.uuid4())
    turns = [
        ("user", "Set up the sender."),
        ("assistant", "Done, I created two tokens."),
        ("user", "I only have one account."),
        ("assistant", "Fixed."),
        ("user", "<command-name>/retro</command-name>"),
        ("assistant", "## 1. Session review\nEmpty retro: nothing durable surfaced"),
        ("user", "approve"),
    ]
    path = synth.write_transcript(tmp_path, r"C:\proj", sid, turns)
    recs, offset = T.read_records(path)
    assert offset == path.stat().st_size
    out = T.extract(recs)
    texts = [m["text"] for m in out["messages"]]
    assert texts == ["Set up the sender.", "I only have one account.", "approve"]
    assert out["messages"][1]["prior"].endswith("two tokens.")
    assert out["messages"][0]["prior"] == ""
    assert len(out["retros"]) == 1
    assert "Empty retro" in out["retros"][0]["reply"]
    assert out["retros"][0]["next_user"] == "approve"
    assert out["retros"][0]["ordinal"] == 1


def test_excluded_shapes(tmp_path):
    sid = str(uuid.uuid4())
    turns = [
        ("user", "[Request interrupted by user]"),
        ("user", "<bash-stdout>ls</bash-stdout>"),
        ("user", "<local-command-caveat>x</local-command-caveat>"),
        ("user", "   "),
        ("user", "real one"),
    ]
    path = synth.write_transcript(tmp_path, r"C:\proj", sid, turns)
    recs, _ = T.read_records(path)
    assert [m["text"] for m in T.extract(recs)["messages"]] == ["real one"]


def test_tool_result_and_meta_are_not_user_messages():
    rec = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}}
    assert not T.qualifies(rec)
    rec = {"type": "user", "isMeta": True, "message": {"role": "user", "content": "x"}}
    assert not T.qualifies(rec)


def test_read_records_resumes_from_offset(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    recs, off = T.read_records(p)
    assert [r["a"] for r in recs] == [1, 2]
    p.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    recs, off2 = T.read_records(p, off)
    assert [r["a"] for r in recs] == [3] and off2 > off


def test_read_records_does_not_consume_partial_trailing_line(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_bytes(b'{"a":1}\n{"a":2,"partial"')
    recs, off = T.read_records(p)
    assert [r["a"] for r in recs] == [1] and off == len(b'{"a":1}\n')
    p.write_bytes(b'{"a":1}\n{"a":2,"partial":true}\n{"a":3}\n')
    recs, off2 = T.read_records(p, off)
    assert [r["a"] for r in recs] == [2, 3] and off2 == p.stat().st_size
