import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import health  # noqa: E402


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
        "# last-scan: 2026-09-01T10:00\n"
        "id\tfound\tstore\tsession\ttype\tlesson\tevidence\tconfidence\tstatus\tresolved\n"
        "F0001\t2026-09-01\tC--Users-test-proj\ts1\trecur\tmem:x\tfix it\thigh\topen\t\n"
        "F0002\t2026-09-01\tglobal\ts1\trecur\tglobal:y\tagain\tmedium\tresolved:evict\t2026-09-02\n")
    (retro / "retro-log.tsv").write_text(
        "2026-09-01T10:00\tC--Users-test-proj\t1\t0\t0\tno\t0\t0\n"
        "2026-09-02T11:00\tNewsletter\t0\t0\t0\tyes\t0\t0\n")
    return cfg


def test_gotchas_words_counts_only_that_section(tmp_path):
    cfg = build(tmp_path)
    assert health.gotchas_words(cfg / "CLAUDE.md") == 361
    (cfg / "CLAUDE.md").write_text("# T\n## Other\n- z\n")
    assert health.gotchas_words(cfg / "CLAUDE.md") is None


def test_store_stats_counts_entries_and_dated(tmp_path):
    cfg = build(tmp_path)
    assert health.store_stats(cfg / "projects") == [("C--Users-test-proj", 4, 1)]


def test_findings_status_open_and_age(tmp_path):
    cfg = build(tmp_path)
    open_rows, age = health.findings_status(cfg / "retro" / "findings.tsv")
    assert open_rows == 1 and age > 1
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
        "F0003\t2026-09-01\tglobal\ts1\trecur\tglobal:z\tfix it\thigh\topen\t\n")
    assert health.findings_status(findings)[0] == 3
    assert health.findings_status(findings, store="proj-a")[0] == 2
    assert health.findings_status(findings, store="proj-b")[0] == 2
    assert health.findings_status(findings, store="proj-c")[0] == 1


def test_ledger_bad_stores(tmp_path):
    cfg = build(tmp_path)
    bad = health.ledger_bad_stores(cfg / "retro" / "retro-log.tsv", {"C--Users-test-proj"})
    assert bad == ["Newsletter"]


def test_report_text(tmp_path):
    cfg = build(tmp_path)
    text = health.report(cfg, store=None)
    assert "Machine gotchas: 361 of 350 words" in text
    assert "C--Users-test-proj: 4 of 20 entries, 1 dated files" in text
    assert "Findings: 1 open, scan" in text
    assert "Ledger: 1 rows whose store is not a memory folder slug: Newsletter" in text
