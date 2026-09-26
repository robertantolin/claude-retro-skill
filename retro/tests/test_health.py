import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import health  # noqa: E402

# Fixture dates are relative to today, so the 400-day window test below never expires.
NOW = datetime.now()


def day(ago: int) -> str:
    return (NOW - timedelta(days=ago)).strftime("%Y-%m-%d")


RECENT, NEXT_DAY, THIRD_DAY, LATER, OLD = day(12), day(11), day(10), day(8), day(600)


def build(tmp_path: Path) -> Path:
    cfg = tmp_path / ".claude"
    store = cfg / "projects" / "C--Users-test-proj" / "memory"
    store.mkdir(parents=True)
    (store / "MEMORY.md").write_text("- index\n")
    for name in ("a-lesson", "b-lesson", "c-lesson", "session-2026-08-01"):
        (store / f"{name}.md").write_text("---\nname: x\ndescription: y\n---\nbody\n")
    words = " ".join(["gotcha"] * 360)
    (cfg / "CLAUDE.md").write_text(f"# T\n\n## Machine gotchas\n- {words}\n\n## Other\n- z\n")
    retro = cfg / "retro"
    retro.mkdir()
    (retro / "findings.tsv").write_text(
        f"# last-scan: {RECENT}T10:00\n"
        "id\tfound\tstore\tsession\ttype\tlesson\tevidence\tconfidence\tstatus\tresolved\n"
        f"F0001\t{RECENT}\tC--Users-test-proj\ts1\trecur\tmem:x\tfix it\thigh\topen\t\n"
        f"F0002\t{RECENT}\tglobal\ts1\trecur\tglobal:y\tagain\tmedium\tresolved:evict\t{NEXT_DAY}\n"
        f"F0003\t{LATER}\tC--Users-test-proj\ts2\trecur\tmem:C--Users-test-proj/a-lesson\tagain\thigh\topen\t\t\n")
    (retro / "retro-log.tsv").write_text(
        "run_id\ttimestamp\tproject\tproposal\tfinding_id\tkind\tdecision\trefine_count\tapplied\tverified\n"
        f"r1\t{RECENT}T10:05\tC--Users-test-proj\t1\tF0001\tstore-write\tapprove-once\t0\ty\ty\n"
        f"r1\t{RECENT}T10:06\tC--Users-test-proj\t2\tF0002\tglobal-line\tdeny\t1\tn\tna\n"
        f"r2\t{NEXT_DAY}T11:00\tC--Users-test-proj\t0\t\tnone\tnone\t0\tn\tna\n"
        f"r3\t{THIRD_DAY}T11:00\tC--Users-test-proj\t1\tF0003\tstore-write\tno-decision\t0\tn\tna\n")
    (retro / "scan-state.json").write_text(json.dumps({"offsets": {}, "last_scan": f"{RECENT}T10:00"}))
    (retro / "journal").mkdir()
    (retro / "journal" / "r1.json").write_text(json.dumps({
        "run_id": "r1", "project": "C--Users-test-proj", "started_at": f"{RECENT}T10:00:00", "reverted_at": None,
        "writes": [{"path": str(store / "a-lesson.md"), "kind": "store-write", "proposal": 1, "before": None,
                    "before_sha": None, "after_sha": "x", "deleted": False, "trash": None}]}))
    (retro / "journal" / "r0.json").write_text(json.dumps({
        "run_id": "r0", "project": "C--Users-test-proj", "started_at": f"{OLD}T10:00:00", "reverted_at": None,
        "writes": [{"path": str(store / "b-lesson.md"), "kind": "store-write", "proposal": 1, "before": None,
                    "before_sha": None, "after_sha": "x", "deleted": False, "trash": None}]}))
    (retro / "candidates").mkdir()
    (retro / "candidates" / "C--Users-test-proj.tsv").write_text(
        "date\tcategory\tkey\tsummary\tcount\tlast_seen\tstatus\n"
        f"{RECENT}\trework-loop\tmemo trimmed\ts\t2\t{THIRD_DAY}\tproposed\n"
        f"{NEXT_DAY}\ttime-sink\tslow deploy\ts\t1\t{NEXT_DAY}\topen\n"
        f"{OLD}\trepeat-manual\told sighting\ts\t1\t{OLD}\topen\n")
    return cfg


def test_gotchas_words_counts_only_that_section(tmp_path):
    cfg = build(tmp_path)
    assert health.gotchas_words(cfg / "CLAUDE.md") == 361
    (cfg / "CLAUDE.md").write_text("# T\n## Other\n- z\n")
    assert health.gotchas_words(cfg / "CLAUDE.md") is None


def test_store_stats_counts_entries_and_dated(tmp_path):
    cfg = build(tmp_path)
    assert health.store_stats(cfg / "projects") == [("C--Users-test-proj", 4, 1)]


def test_findings_status_open(tmp_path):
    cfg = build(tmp_path)
    assert health.findings_status(cfg / "retro" / "findings.tsv")[0] == 2
    assert health.findings_status(cfg / "retro" / "missing.tsv") is None


def test_findings_status_filters_by_store(tmp_path):
    retro = tmp_path / ".claude" / "retro"
    retro.mkdir(parents=True)
    findings = retro / "findings.tsv"
    findings.write_text(
        "# last-scan: 2026-09-01T10:00\n"
        "id\tfound\tstore\tsession\ttype\tlesson\tevidence\tconfidence\tstatus\tresolved\n"
        "F0001\t2026-09-01\tproj-a\ts1\trecur\tmem:x\tfix it\thigh\topen\t\n"
        "F0002\t2026-09-01\tproj-b\ts1\trecur\tmem:y\tfix it\thigh\topen\t\n"
        "F0003\t2026-09-01\tglobal\ts1\trecur\tglobal:z\tfix it\thigh\topen\t\n"
        "F0004\t2026-09-01\tproj-a\t\tdormant\tmem:proj-a/quiet\t\t\topen\t\n")
    # a dormant row is a delete candidate, not an open finding for the retro's table
    assert health.findings_status(findings)[0] == 3
    assert health.findings_status(findings, store="proj-a")[0] == 2
    assert health.findings_status(findings, store="proj-b")[0] == 2
    assert health.findings_status(findings, store="proj-c")[0] == 1


def test_coverage_line(tmp_path):
    cfg = build(tmp_path)
    assert health.coverage(cfg) == f"History scan: covers sessions up to {RECENT}"
    (cfg / "retro" / "scan-state.json").write_text('{"offsets": {}, "last_scan": null}')
    assert health.coverage(cfg) == "History scan: never run"
    (cfg / "retro" / "scan-state.json").unlink()
    assert health.coverage(cfg) == "History scan: never run"


def test_report_text(tmp_path):
    cfg = build(tmp_path)
    text = health.report(cfg, store=None)
    assert "Machine gotchas: 361 of 350 words" in text
    assert "C--Users-test-proj: 4 of 20 entries, 1 dated files" in text
    assert "Findings: 2 open" in text
    assert f"History scan: covers sessions up to {RECENT}" in text
    assert "Ledger: 4 rows, 0 malformed" in text
    assert "Candidates: 3 rows, ok" in text
    assert "Approve-always: none" in text
    assert "pre-v3 ledger moved" not in text
    assert "Raised bar" not in text


def test_report_announces_pre_v3_migration(tmp_path):
    cfg = build(tmp_path)
    (cfg / "retro" / "retro-log.tsv").write_text(
        "2026-09-01T10:00\tC--Users-test-proj\t1\t0\t0\tno\t0\t0\n"
        "2026-09-02T11:00\tC--Users-test-proj\t0\t0\t0\tyes\t0\t0\n")
    text = health.report(cfg, store=None)
    assert "Ledger: pre-v3 ledger moved to retro-log.v2.tsv" in text
    assert (cfg / "retro" / "retro-log.v2.tsv").exists()
    assert "Ledger: 0 rows, 0 malformed" in text


def test_report_flags_a_malformed_candidates_file(tmp_path):
    cfg = build(tmp_path)
    with (cfg / "retro" / "candidates" / "C--Users-test-proj.tsv").open("a", encoding="utf-8") as f:
        f.write(f"{NEXT_DAY}\tvibes\tbad category\ts\t1\t{NEXT_DAY}\topen\n")
    text = health.report(cfg, store=None)
    assert "Candidates: 4 rows, " in text and "vibes" in text
    assert "Candidates: 4 rows, ok" not in text


def test_report_raised_bar_line(tmp_path):
    cfg = build(tmp_path)
    (cfg / "retro" / "settings.json").write_text(json.dumps({"raised_bar": ["global-line"]}))
    text = health.report(cfg, store=None)
    assert "Raised bar (logs as candidate instead of proposing): global-line in every project" in text
    (cfg / "retro" / "settings.json").write_text(json.dumps({"raised_bar": {"C--Users-test-proj": ["store-write"]}}))
    assert "Raised bar (logs as candidate instead of proposing): store-write" in health.report(cfg, store="C--Users-test-proj")
    assert "Raised bar" not in health.report(cfg, store="C--other")
    assert "store-write in C--Users-test-proj" in health.report(cfg, store=None)


def test_metrics(tmp_path):
    cfg = build(tmp_path)
    m = health.metrics(cfg, days=3650)
    assert m["proposals_raised"] == 3
    assert m["proposals_per_run"] == 1.0
    assert m["proposal_conversion"] == "1 of 3"
    assert m["denial_by_kind"] == {"store-write": "0 of 2", "global-line": "1 of 1"}
    assert m["candidate_confirmation"] == "1 of 3"
    assert m["runs"] == 3 and m["runs_unread"] == 1 and m["empty_runs"] == 1
    assert m["lessons_written"] == 2 and m["lessons_recurred"] == 1
    assert m["time_to_first_decision_s"] == 300


def test_metrics_day_window_excludes_old_journals_and_candidates(tmp_path):
    cfg = build(tmp_path)
    m = health.metrics(cfg, days=400)
    assert m["lessons_written"] == 1 and m["lessons_recurred"] == 1
    assert m["candidate_confirmation"] == "1 of 2"
