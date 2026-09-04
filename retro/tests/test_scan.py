import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan  # noqa: E402
import synth  # noqa: E402


def test_lesson_index_reads_memory_global_and_rules(tmp_path):
    cfg = tmp_path
    mem = cfg / "projects" / "C--p" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("- idx\n")
    (mem / "verify-first.md").write_text('---\nname: verify-first\ndescription: "Check the file before claiming"\n---\nbody\n')
    (cfg / "CLAUDE.md").write_text("# Me\n\n## Machine gotchas\n- No jq on this machine.\n\n## Active projects\n| a | b |\n- not a lesson\n")
    (cfg / "rules").mkdir()
    (cfg / "rules" / "design-brief.md").write_text("---\ndescription: Before building anything visual\n---\n")
    idx = scan.lesson_index(cfg)
    assert ("mem:C--p/verify-first", "Check the file before claiming") in idx
    assert ("global:Machine gotchas", "No jq on this machine.") in idx
    assert ("rule:design-brief", "Before building anything visual") in idx
    assert not any(k.startswith("global:Active projects") for k, _ in idx)


def test_parse_classification_drops_invented_ids():
    msgs = [{"id": 1, "text": "a", "prior": ""}, {"id": 2, "text": "b", "prior": ""}]
    reply = '[{"id": 1, "correction": true, "gist": "x"}, {"id": 7, "correction": true, "gist": "y"}]'
    items, dropped = scan.parse_classification(reply, msgs)
    assert [i["id"] for i in items] == [1] and dropped == 1


def test_parse_classification_rejects_non_list():
    try:
        scan.parse_classification('{"ok": 1}', [{"id": 1}])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_findings_roundtrip(tmp_path):
    p = tmp_path / "findings.tsv"
    rows = [scan.finding_row("F0001", "2026-09-03", "C--p", "s1", "recur", "mem:C--p/x", "fix\tit\nnow", "high")]
    scan.save_findings(p, "2026-09-03T10:00", rows)
    stamp, back = scan.load_findings(p)
    assert stamp == "2026-09-03T10:00"
    assert back[0]["evidence"] == "fix it now" and back[0]["status"] == "open"
    assert scan.next_id(back) == "F0002"


def test_state_roundtrip(tmp_path):
    p = tmp_path / "scan-state.json"
    st = scan.load_state(p)
    assert st == {"offsets": {}, "last_scan": None}
    st["offsets"]["x"] = 10
    scan.save_state(p, st, "2026-09-03T10:00")
    assert json.loads(p.read_text())["offsets"]["x"] == 10


def test_progress_persists_when_a_later_session_is_interrupted(tmp_path, monkeypatch):
    cfg = tmp_path
    (cfg / "CLAUDE.md").write_text("## Machine gotchas\n- Watch for wrong redoes.\n")
    p1 = synth.write_transcript(cfg, r"C:\proj1", "s1", [("user", "That was wrong, redo it.")])
    p2 = synth.write_transcript(cfg, r"C:\proj2", "s2", [("user", "That was also wrong, redo it.")])

    def fake_call(model, prompt, timeout=300):
        if model == "sonnet":
            return '[{"id": 1, "correction": true, "gist": "wrong"}]'
        if model == "opus":
            if "C--proj1" in prompt:
                return '{"match": "L1", "confidence": "high", "why": "matches"}'
            raise KeyboardInterrupt("simulated kill")
        raise AssertionError(f"unexpected model {model}")

    monkeypatch.setattr(scan.llm, "call", fake_call)

    try:
        scan.main(["--claude-dir", str(cfg)])
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("expected KeyboardInterrupt")

    stamp, rows = scan.load_findings(cfg / "retro" / "findings.tsv")
    assert stamp is not None
    assert any(r["session"] == "s1" for r in rows)
    state = scan.load_state(cfg / "retro" / "scan-state.json")
    assert str(p1) in state["offsets"]
    assert str(p2) not in state["offsets"]


def test_classify_retries_once_on_transient_runtime_error(monkeypatch):
    monkeypatch.setattr(scan.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_call(model, prompt, timeout=300):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("claude exit 1: transient")
        return '[{"id": 1, "correction": true, "gist": "x"}]'

    monkeypatch.setattr(scan.llm, "call", fake_call)
    items, dropped = scan.classify([{"id": 1, "text": "a", "prior": ""}], "sonnet")
    assert calls["n"] == 2
    assert items == [{"id": 1, "correction": True, "gist": "x"}]
    assert dropped == 0


def test_match_retries_once_on_transient_runtime_error(monkeypatch):
    monkeypatch.setattr(scan.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_call(model, prompt, timeout=300):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("claude exit 1: transient")
        return '{"match": "L1", "confidence": "high", "why": "ok"}'

    monkeypatch.setattr(scan.llm, "call", fake_call)
    index = [("mem:x/y", "desc")]
    res = scan.match({"store": "s", "prior": "", "text": "t", "gist": "g"}, index, "opus")
    assert calls["n"] == 2
    assert res["match_key"] == "mem:x/y" and res["confidence"] == "high"


def test_call_with_retry_survives_timeout_then_succeeds(monkeypatch):
    monkeypatch.setattr(scan.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_call(model, prompt, timeout=300):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.TimeoutExpired(cmd="claude", timeout=300)
        return "ok"

    monkeypatch.setattr(scan.llm, "call", fake_call)
    result = scan._call_with_retry("sonnet", "prompt")
    assert calls["n"] == 2
    assert result == "ok"


def test_match_accepts_a_list_reply_by_taking_first_dict(monkeypatch):
    monkeypatch.setattr(scan.time, "sleep", lambda s: None)

    def fake_call(model, prompt, timeout=300):
        return '[{"match": "L1", "confidence": "high", "why": "ok"}]'

    monkeypatch.setattr(scan.llm, "call", fake_call)
    index = [("mem:x/y", "desc")]
    res = scan.match({"store": "s", "prior": "", "text": "t", "gist": "g"}, index, "opus")
    assert res["match_key"] == "mem:x/y" and res["confidence"] == "high"


def test_chunking_persists_earlier_chunk_when_a_later_chunk_is_interrupted(tmp_path, monkeypatch):
    cfg = tmp_path
    paths = []
    for i in range(11):
        sid = f"s{i:02d}"
        p = synth.write_transcript(cfg, r"C:\proj", sid, [("user", f"Message number {i}, nothing wrong here.")])
        paths.append(p)

    def fake_call(model, prompt, timeout=300):
        if model == "sonnet":
            if "number 10" in prompt:
                raise KeyboardInterrupt("simulated kill in chunk 2")
            return '[{"id": 1, "correction": false, "gist": ""}]'
        raise AssertionError(f"unexpected model {model}")

    monkeypatch.setattr(scan.llm, "call", fake_call)

    try:
        scan.main(["--claude-dir", str(cfg)])
    except KeyboardInterrupt:
        pass
    else:
        raise AssertionError("expected KeyboardInterrupt")

    state = scan.load_state(cfg / "retro" / "scan-state.json")
    for p in paths[:10]:
        assert str(p) in state["offsets"]
    assert str(paths[10]) not in state["offsets"]
