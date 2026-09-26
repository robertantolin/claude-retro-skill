import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ledger  # noqa: E402
import settings  # noqa: E402


def row(cfg, **kw):
    base = dict(run_id="r1", project="P", proposal=1, finding_id="F0001", kind="store-write", decision="approve-once")
    base.update(kw)
    return ledger.append_row(cfg, **base)


def test_append_creates_header_and_row(tmp_path):
    row(tmp_path)
    lines = ledger.path(tmp_path).read_text().splitlines()
    assert lines[0] == "\t".join(ledger.COLS)
    assert lines[1].split("\t")[0] == "r1" and len(lines[1].split("\t")) == len(ledger.COLS)


def test_append_rejects_bad_values(tmp_path):
    for bad in (dict(kind="banana"), dict(decision="maybe"), dict(applied="x"), dict(verified="q")):
        try:
            row(tmp_path, **bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_migrates_old_ledger(tmp_path):
    p = ledger.path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("2026-09-01T16:42\tC--x\t0\t3\t0\tyes\t0\t0\n")
    row(tmp_path)
    assert (p.parent / "retro-log.v2.tsv").read_text().startswith("2026-09-01T16:42")
    assert ledger.load_rows(tmp_path)[0]["run_id"] == "r1"


def test_zero_byte_ledger_is_not_migrated(tmp_path):
    p = ledger.path(tmp_path)
    p.parent.mkdir(parents=True)
    v2 = p.with_name("retro-log.v2.tsv")
    v2.write_text("2026-09-01T16:42\tC--x\t0\t3\t0\tyes\t0\t0\n")
    p.write_text("")
    assert ledger.load_rows(tmp_path) == []
    assert v2.read_text().startswith("2026-09-01T16:42")
    assert p.exists()


def test_existing_v2_is_set_aside_before_a_second_migration(tmp_path):
    p = ledger.path(tmp_path)
    p.parent.mkdir(parents=True)
    v2 = p.with_name("retro-log.v2.tsv")
    v2.write_text("the only pre-v3 copy\n")
    p.write_text("2026-09-01T16:42\tC--x\t0\t3\t0\tyes\t0\t0\n")
    ledger.load_rows(tmp_path)
    assert v2.read_text().startswith("2026-09-01T16:42")
    kept = sorted(p.parent.glob("retro-log.v2.*.tsv"))
    assert len(kept) == 1 and kept[0].read_text() == "the only pre-v3 copy\n"


def test_validate_reports_malformed(tmp_path):
    row(tmp_path)
    with ledger.path(tmp_path).open("a") as f:
        f.write("r2\tbroken\n")
    assert len(ledger.validate(tmp_path)) == 1


def test_recent_and_pending(tmp_path):
    old = (datetime.now() - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M")
    row(tmp_path, run_id="old", timestamp=old)
    row(tmp_path, run_id="new", decision="no-decision")
    row(tmp_path, run_id="other", project="Q")
    assert [r["run_id"] for r in ledger.recent(tmp_path, "P")] == ["new"]
    assert [r["run_id"] for r in ledger.pending(tmp_path, "P")] == ["new"]


def test_three_denials_in_one_project_raise_its_bar(tmp_path):
    for n in (1, 2):
        row(tmp_path, proposal=n, kind="global-line", decision="deny")
    assert not settings.is_raised(tmp_path, "global-line", "P")
    row(tmp_path, proposal=3, kind="global-line", decision="deny")
    assert settings.is_raised(tmp_path, "global-line", "P")
    assert not settings.is_raised(tmp_path, "global-line", "Q")


def test_denials_spread_over_projects_do_not_raise_a_bar(tmp_path):
    # 2026-09-17: one denial in project A and two in project B switched lesson files off everywhere
    row(tmp_path, project="A", proposal=1, kind="store-write", decision="deny")
    row(tmp_path, project="B", proposal=1, kind="store-write", decision="deny")
    row(tmp_path, project="B", proposal=2, kind="store-write", decision="deny")
    assert settings.load(tmp_path)["raised_bar"] == {}


def test_cli_append_announces_a_raised_bar(tmp_path, capsys):
    base = ["--claude-dir", str(tmp_path), "append", "--run-id", "r", "--project", "P", "--finding-id", "none",
            "--kind", "store-write", "--decision", "deny", "--proposal"]
    for n in ("1", "2"):
        assert ledger.main(base + [n]) == 0
    assert "bar raised" not in capsys.readouterr().out
    assert ledger.main(base + ["3"]) == 0
    out = capsys.readouterr().out
    assert "bar raised" in out and "store-write" in out and "reset-bar store-write" in out


def test_mark_reverted(tmp_path):
    row(tmp_path)
    row(tmp_path, proposal=2)
    assert ledger.mark_reverted(tmp_path, "r1") == 2
    assert all(r["decision"] == "reverted" for r in ledger.load_rows(tmp_path))


def test_title_of_reads_proposal_md(tmp_path):
    d = tmp_path / "retro" / "proposals" / "r1"
    d.mkdir(parents=True)
    (d / "1.md").write_text("# Proposal 1 of 2: Search past sessions with the tool that works\n\n- What changes: x\n")
    assert ledger.title_of(tmp_path, "r1", 1) == "Search past sessions with the tool that works"
    assert ledger.title_of(tmp_path, "r1", 9) == ""


def test_validate_migrates_old_ledger(tmp_path):
    p = ledger.path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("2026-09-01T16:42\tC--x\t0\t3\t0\tyes\t0\t0\n")
    assert ledger.validate(tmp_path) == []
    assert (p.parent / "retro-log.v2.tsv").exists()


def test_mark_reverted_keeps_malformed_lines(tmp_path):
    row(tmp_path)
    with ledger.path(tmp_path).open("a", encoding="utf-8") as f:
        f.write("r1\tbroken\n")
    row(tmp_path, proposal=2)
    assert ledger.mark_reverted(tmp_path, "r1") == 2
    assert "r1\tbroken" in ledger.path(tmp_path).read_text(encoding="utf-8")
    assert [r["decision"] for r in ledger.load_rows(tmp_path)] == ["reverted", "reverted"]


def test_cli_append_validate_pending(tmp_path, capsys):
    base = ["--claude-dir", str(tmp_path)]
    good = ["append", "--run-id", "cli1", "--project", "P", "--proposal", "1",
            "--finding-id", "F0001", "--kind", "store-write", "--decision", "approve-once"]
    assert ledger.main(base + good) == 0
    assert [r["run_id"] for r in ledger.load_rows(tmp_path)] == ["cli1"]
    capsys.readouterr()
    bad = good[:-3] + ["banana", "--decision", "approve-once"]
    assert ledger.main(base + bad) == 2
    assert "banana" in capsys.readouterr().err
    assert ledger.main(base + ["validate"]) == 0
    capsys.readouterr()
    row(tmp_path, run_id="cli2", decision="no-decision")
    assert ledger.main(base + ["pending", "--project", "P"]) == 0
    assert "cli2" in capsys.readouterr().out
