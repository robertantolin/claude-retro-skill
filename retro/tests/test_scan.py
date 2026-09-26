import json
import os
import subprocess
import sys
import time
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
    items, dropped, _ = scan.parse_classification(reply, msgs)
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
    items, dropped, _ = scan.classify([{"id": 1, "text": "a", "prior": ""}], "sonnet")
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


def test_classify_decisions_retries_once_on_transient_runtime_error(monkeypatch):
    monkeypatch.setattr(scan.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_call(model, prompt, timeout=300):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("claude exit 1: transient")
        return '[{"k": 0, "decision": "approve-all"}]'

    monkeypatch.setattr(scan.llm, "call", fake_call)
    retros = [{"reply": "proposal text", "next_user": "yes", "ts": "2026-09-01T10:00"}]
    verdicts = scan.classify_decisions(retros, "sonnet")
    assert calls["n"] == 2
    assert verdicts == ["approve-all"]


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


def test_findings_cols_include_reason_and_old_rows_pad(tmp_path):
    assert scan.FINDINGS_COLS[-1] == "reason"
    p = tmp_path / "findings.tsv"
    p.write_text("# last-scan: 2026-09-03T19:58\n" + "\t".join(scan.FINDINGS_COLS[:-1]) + "\n"
                 "F0001\t2026-09-03\tC--p\ts\trecur\tmem:C--p/x\tev\thigh\topen\t\n")
    _, rows = scan.load_findings(p)
    assert rows[0]["reason"] == "" and rows[0]["status"] == "open"


def test_parse_classification_returns_candidates():
    msgs = [{"id": 1, "text": "a", "prior": ""}]
    reply = ('{"messages": [{"id": 1, "correction": true, "gist": "x"}], '
             '"candidates": [{"category": "rework-loop", "key": "memo trimmed", "summary": "four rounds", "count": 4}, '
             '{"category": "vibes", "key": "bad", "summary": "s", "count": 1}]}')
    items, dropped, cands = scan.parse_classification(reply, msgs)
    assert items == [{"id": 1, "correction": True, "gist": "x"}] and dropped == 0
    assert cands == [{"category": "rework-loop", "key": "memo trimmed", "summary": "four rounds", "count": 4}]


def test_parse_classification_accepts_bare_list():
    msgs = [{"id": 1, "text": "a", "prior": ""}]
    items, dropped, cands = scan.parse_classification('[{"id": 1, "correction": false, "gist": ""}]', msgs)
    assert items[0]["correction"] is False and cands == []


def test_trim_to_budget_drops_oldest():
    msgs = [{"id": i, "text": "x" * 100, "prior": "p" * 100} for i in range(1, 6)]
    kept, truncated = scan.trim_to_budget(msgs, 450)
    assert [m["id"] for m in kept] == [4, 5] and truncated is True
    kept, truncated = scan.trim_to_budget(msgs, 10000)
    assert len(kept) == 5 and truncated is False


def test_is_hard():
    assert scan.is_hard({"category": "rework-loop", "count": 3})
    assert scan.is_hard({"category": "repeat-manual", "count": 3})
    assert not scan.is_hard({"category": "rework-loop", "count": 2})
    assert not scan.is_hard({"category": "revisited", "count": 9})


def test_record_candidates_confirms_and_writes_finding(tmp_path):
    import candidates as C
    C.log(tmp_path, "C--p", "revisited", "pricing question re-asked", "s", "2026-09-01")
    rows = []
    out = scan.record_candidates(tmp_path, "C--p", [
        {"category": "revisited", "key": "pricing question asked again", "summary": "again", "count": 1},
        {"category": "rework-loop", "key": "memo trimmed", "summary": "four rounds", "count": 4},
        {"category": "time-sink", "key": "slow deploy", "summary": "s", "count": 1},
    ], "2026-09-05", rows)
    assert [o["confirmed"] for o in out] == [True, False, False]
    assert [o["hard"] for o in out] == [False, True, False]
    assert [r["type"] for r in rows] == ["candidate", "candidate"]
    assert rows[0]["lesson"] == "cand:revisited/pricing question re-asked" and rows[1]["confidence"] == "high"
    assert {r["status"] for r in C.load(tmp_path, "C--p")} == {"proposed", "open"}
    # second call does not duplicate the finding
    scan.record_candidates(tmp_path, "C--p", [{"category": "rework-loop", "key": "memo trimmed", "summary": "x", "count": 4}], "2026-09-06", rows)
    assert len(rows) == 2


def test_set_status_with_reason(tmp_path):
    rdir = tmp_path / "retro"
    rows = [scan.finding_row("F0001", "2026-09-03", "C--p", "s", "recur", "mem:C--p/x", "ev", "high")]
    scan.save_findings(rdir / "findings.tsv", "2026-09-03T10:00", rows)
    assert scan.set_status(tmp_path, "F0001", "denied", "not worth a rule") is True
    _, back = scan.load_findings(rdir / "findings.tsv")
    assert back[0]["status"] == "denied" and back[0]["reason"] == "not worth a rule" and back[0]["resolved"]
    assert scan.set_status(tmp_path, "F0009", "denied") is False


def test_scan_session_end_to_end_with_stubbed_llm(tmp_path, monkeypatch):
    import candidates as C
    # a short literal cwd: slug_of(tmp_path/"work") pushes the transcript past Windows' 260-char path limit
    work = r"C:\work"
    sid = "11111111-2222-3333-4444-555555555555"
    p = synth.write_transcript(tmp_path, str(work), sid, [
        ("user", "Set up retries."),
        ("assistant", "Retries run forever."),
        ("user", "This project's retry queue is capped at 3 attempts per message."),
        ("assistant", "Capped."),
    ])
    slug = synth.slug_of(str(work))
    mem = tmp_path / "projects" / slug / "memory"
    mem.mkdir(parents=True)
    (mem / "retry-cap.md").write_text("---\nname: retry-cap\ndescription: Retries are capped at 3\n---\n")
    replies = iter([
        '{"messages": [{"id": 1, "correction": false, "gist": ""}, {"id": 2, "correction": true, "gist": "retry cap ignored"}],'
        ' "candidates": [{"category": "rework-loop", "key": "retry config redone", "summary": "s", "count": 3}]}',
        '{"match": "L1", "confidence": "high", "why": "same lesson"}',
    ])
    monkeypatch.setattr(scan.llm, "call", lambda model, prompt, timeout=300: next(replies))
    monkeypatch.setattr(scan, "predates_lesson", lambda *a, **k: False)
    out = scan.scan_session(tmp_path, p, {"classify": "sonnet", "match": "opus"}, 48000)
    assert out["store"] == slug and out["truncated"] is False
    assert out["corrections"][0]["match_key"] == f"mem:{slug}/retry-cap" and out["corrections"][0]["text"].startswith("This project's retry")
    assert out["candidates"][0]["hard"] is True and out["candidates"][0]["finding_id"].startswith("F")
    _, rows = scan.load_findings(tmp_path / "retro" / "findings.tsv")
    assert {r["type"] for r in rows} == {"recur", "candidate"}
    st = scan.load_state(tmp_path / "retro" / "scan-state.json")
    assert st["offsets"][str(p)] == p.stat().st_size
    # candidates.log counts one sighting per call (controller ruling 1: no count argument),
    # so a single scan_session records count 1 regardless of the classifier's count=3.
    assert C.load(tmp_path, slug)[0]["count"] == 1


def test_full_scan_logs_candidates_only_for_transcripts_without_a_bookmark(tmp_path, monkeypatch):
    import candidates as C
    cfg = tmp_path
    p_seen = synth.write_transcript(cfg, r"C:\seen", "s1", [("user", "Nothing wrong here.")])
    p_new = synth.write_transcript(cfg, r"C:\new", "s2", [("user", "Nothing wrong here either.")])
    scan.save_state(cfg / "retro" / "scan-state.json",
                    {"offsets": {str(p_seen): p_seen.stat().st_size}, "last_scan": None}, "2026-09-01T10:00")

    def fake_call(model, prompt, timeout=300):
        return ('{"messages": [{"id": 1, "correction": false, "gist": ""}],'
                ' "candidates": [{"category": "time-sink", "key": "slow thing", "summary": "s", "count": 1}]}')

    monkeypatch.setattr(scan.llm, "call", fake_call)
    # --since re-reads both transcripts from byte 0; only the one with no bookmark is a first sighting
    scan.main(["--claude-dir", str(cfg), "--since", "2026-01-01"])
    assert [r["key"] for r in C.load(cfg, "C--new")] == ["slow thing"]
    assert C.load(cfg, "C--seen") == []


def test_scan_session_skips_while_a_full_scan_holds_the_lock(tmp_path):
    p = synth.write_transcript(tmp_path, r"C:\w", "s1", [("user", "That was wrong, redo it.")])
    lock = tmp_path / "retro" / "scan.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("pid 123 started 2026-09-12T10:00\n")
    out = scan.scan_session(tmp_path, p, {"classify": "sonnet", "match": "opus"}, 48000)
    assert out["error"] == "history scan in progress; session scan skipped"
    assert not (tmp_path / "retro" / "findings.tsv").exists()
    assert not (tmp_path / "retro" / "scan-state.json").exists()
    assert lock.exists()


def test_scan_session_clears_a_stale_lock_and_proceeds(tmp_path, monkeypatch):
    p = synth.write_transcript(tmp_path, r"C:\w", "s1", [("user", "Nothing wrong here.")])
    lock = tmp_path / "retro" / "scan.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("pid 123\n")
    old = time.time() - 3 * 3600
    os.utime(lock, (old, old))
    monkeypatch.setattr(scan.llm, "call",
                        lambda model, prompt, timeout=300: '[{"id": 1, "correction": false, "gist": ""}]')
    out = scan.scan_session(tmp_path, p, {"classify": "sonnet", "match": "opus"}, 48000)
    assert out["error"] is None and not lock.exists()
    assert scan.load_state(tmp_path / "retro" / "scan-state.json")["offsets"][str(p)] == p.stat().st_size


def test_session_scan_keeps_the_history_watermark(tmp_path, monkeypatch):
    p = synth.write_transcript(tmp_path, r"C:\w", "s1", [("user", "Nothing wrong here.")])
    scan.save_state(tmp_path / "retro" / "scan-state.json", {"offsets": {}}, "2026-06-01T10:00")
    monkeypatch.setattr(scan.llm, "call",
                        lambda model, prompt, timeout=300: '[{"id": 1, "correction": false, "gist": ""}]')
    out = scan.scan_session(tmp_path, p, {"classify": "sonnet", "match": "opus"}, 48000)
    assert out["error"] is None
    state = scan.load_state(tmp_path / "retro" / "scan-state.json")
    assert state["last_scan"] == "2026-06-01T10:00" and state["offsets"][str(p)] == p.stat().st_size


def test_full_scan_keeps_rows_written_while_it_ran(tmp_path, monkeypatch):
    cfg = tmp_path
    (cfg / "CLAUDE.md").write_text("## Machine gotchas\n- Watch for wrong redoes.\n")
    synth.write_transcript(cfg, r"C:\proj", "s1", [("user", "That was wrong, redo it.")])
    rdir = cfg / "retro"
    scan.save_findings(rdir / "findings.tsv", "2026-09-01T10:00",
                       [scan.finding_row("F0001", "2026-09-01", "C--proj", "s0", "recur", "mem:a", "ev", "high")])

    def fake_call(model, prompt, timeout=300):
        if model == "sonnet":
            # another writer lands a resolve and a new row while this scan is mid-flight
            _, rows = scan.load_findings(rdir / "findings.tsv")
            rows[0]["status"] = "denied"
            rows.append(scan.finding_row("F0002", "2026-09-02", "C--proj", "s9", "recur", "mem:b", "ev", "high"))
            scan.save_findings(rdir / "findings.tsv", "2026-09-02T10:00", rows)
            return '[{"id": 1, "correction": true, "gist": "wrong"}]'
        return '{"match": "L1", "confidence": "high", "why": "matches"}'

    monkeypatch.setattr(scan.llm, "call", fake_call)
    scan.main(["--claude-dir", str(cfg)])
    _, rows = scan.load_findings(rdir / "findings.tsv")
    by_id = {r["id"]: r for r in rows}
    assert by_id["F0001"]["status"] == "denied"
    assert "F0002" in by_id
    assert any(r["session"] == "s1" for r in rows)


def test_full_scan_takes_the_lock_before_reading_transcripts(tmp_path, monkeypatch):
    cfg = tmp_path
    synth.write_transcript(cfg, r"C:\proj", "s1", [("user", "Nothing wrong here.")])
    seen = {}
    real_read = scan.T.read_records

    def watched(path, off):
        seen["locked"] = (cfg / "retro" / "scan.lock").exists()
        return real_read(path, off)

    monkeypatch.setattr(scan.T, "read_records", watched)
    monkeypatch.setattr(scan.llm, "call",
                        lambda model, prompt, timeout=300: '[{"id": 1, "correction": false, "gist": ""}]')
    scan.main(["--claude-dir", str(cfg)])
    assert seen["locked"] is True
    assert not (cfg / "retro" / "scan.lock").exists()


def test_dry_run_writes_no_lock(tmp_path):
    synth.write_transcript(tmp_path, r"C:\proj", "s1", [("user", "Nothing wrong here.")])
    scan.main(["--claude-dir", str(tmp_path), "--dry-run"])
    assert not (tmp_path / "retro" / "scan.lock").exists()


def test_scan_session_reports_an_unreadable_transcript(tmp_path):
    out = scan.scan_session(tmp_path, tmp_path / "projects" / "C--p" / "gone.jsonl",
                            {"classify": "sonnet", "match": "opus"}, 48000)
    assert out["error"].startswith("cannot read transcript:")
    assert not (tmp_path / "retro" / "findings.tsv").exists()


def test_set_status_validates_the_status(tmp_path):
    rows = [scan.finding_row("F0001", "2026-09-03", "C--p", "s", "recur", "mem:C--p/x", "ev", "high")]
    scan.save_findings(tmp_path / "retro" / "findings.tsv", "2026-09-03T10:00", rows)
    for ok in ("open", "denied", "no-decision", "resolved: added a rule", "deferred: next week"):
        assert scan.set_status(tmp_path, "F0001", ok) is True
    try:
        scan.set_status(tmp_path, "F0001", "maybe")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
