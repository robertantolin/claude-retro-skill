import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import journal  # noqa: E402
import ledger  # noqa: E402


def test_begin_creates_journal_and_proposals_dir(tmp_path):
    run = journal.begin(tmp_path, "P")
    assert (tmp_path / "retro" / "journal" / f"{run}.json").exists()
    assert (tmp_path / "retro" / "proposals" / run).is_dir()
    j = journal.load(tmp_path, run)
    assert j["project"] == "P" and j["writes"] == [] and j["started_at"]


def test_snapshot_commit_and_undo_edit(tmp_path):
    f = tmp_path / "lesson.md"
    f.write_text("before")
    run = journal.begin(tmp_path, "P")
    journal.snapshot(tmp_path, run, f, "store-write", 1)
    f.write_text("after")
    journal.commit(tmp_path, run, f)
    j = journal.load(tmp_path, run)
    assert j["writes"][0]["before"] == "before" and j["writes"][0]["after_sha"] == journal.sha("after")
    msgs = journal.undo(tmp_path, run)
    assert f.read_text() == "before" and any("restored" in m for m in msgs)
    assert journal.load(tmp_path, run)["reverted_at"]


def test_undo_removes_created_file(tmp_path):
    f = tmp_path / "new.md"
    run = journal.begin(tmp_path, "P")
    journal.snapshot(tmp_path, run, f, "store-write", 1)
    f.write_text("x")
    journal.commit(tmp_path, run, f)
    journal.undo(tmp_path, run)
    assert not f.exists()


def test_undo_refuses_when_file_changed_since(tmp_path):
    f = tmp_path / "lesson.md"
    f.write_text("before")
    run = journal.begin(tmp_path, "P")
    journal.snapshot(tmp_path, run, f, "store-write", 1)
    f.write_text("after")
    journal.commit(tmp_path, run, f)
    f.write_text("someone else edited")
    try:
        journal.undo(tmp_path, run)
    except RuntimeError as e:
        assert "lesson.md" in str(e)
        assert f.read_text() == "someone else edited"
        return
    raise AssertionError("expected refusal")


def test_delete_moves_to_trash_and_undo_restores(tmp_path):
    f = tmp_path / "old.md"
    f.write_text("bye")
    run = journal.begin(tmp_path, "P")
    trashed = journal.delete(tmp_path, run, f, "store-delete", 2)
    assert not f.exists() and trashed.read_text() == "bye"
    assert trashed.parent == tmp_path / "retro" / "trash" / run
    journal.undo(tmp_path, run)
    assert f.read_text() == "bye"


def test_restore_single_file(tmp_path):
    f = tmp_path / "old.md"
    f.write_text("bye")
    run = journal.begin(tmp_path, "P")
    journal.delete(tmp_path, run, f, "store-delete", 1)
    assert journal.restore(tmp_path, run, "old.md") == f and f.read_text() == "bye"


def test_undo_marks_ledger_reverted(tmp_path):
    run = journal.begin(tmp_path, "P")
    ledger.append_row(tmp_path, run, "P", 1, "F0001", "store-write", "approve-once")
    journal.undo(tmp_path, run)
    assert ledger.load_rows(tmp_path)[0]["decision"] == "reverted"


def test_purge_removes_old_trash_and_journals(tmp_path):
    f = tmp_path / "old.md"
    f.write_text("bye")
    run = journal.begin(tmp_path, "P")
    journal.delete(tmp_path, run, f, "store-delete", 1)
    old = time.time() - 40 * 86400
    for p in (tmp_path / "retro" / "trash" / run, tmp_path / "retro" / "journal" / f"{run}.json"):
        os.utime(p, (old, old))
    out = journal.purge(tmp_path, days=30)
    assert out == {"trash": 1, "journals": 1}
    assert not (tmp_path / "retro" / "trash" / run).exists()


def test_same_named_deletes_get_unique_trash_names(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "lesson.md").write_text("from a")
    (b / "lesson.md").write_text("from b")
    run = journal.begin(tmp_path, "P")
    ta = journal.delete(tmp_path, run, a / "lesson.md", "store-delete", 1)
    tb = journal.delete(tmp_path, run, b / "lesson.md", "store-delete", 2)
    assert ta != tb
    assert ta.read_text() == "from a" and tb.read_text() == "from b"
    journal.undo(tmp_path, run)
    assert (a / "lesson.md").read_text() == "from a"
    assert (b / "lesson.md").read_text() == "from b"


def test_undo_refuses_when_trash_copy_is_missing(tmp_path):
    f = tmp_path / "old.md"
    f.write_text("bye")
    run = journal.begin(tmp_path, "P")
    trashed = journal.delete(tmp_path, run, f, "store-delete", 1)
    trashed.unlink()
    try:
        journal.undo(tmp_path, run)
    except RuntimeError as e:
        assert "old.md" in str(e)
        assert journal.load(tmp_path, run)["reverted_at"] is None
        return
    raise AssertionError("expected refusal")


def test_restore_reports_a_purged_trash_copy(tmp_path, capsys):
    f = tmp_path / "old.md"
    f.write_text("bye")
    run = journal.begin(tmp_path, "P")
    trashed = journal.delete(tmp_path, run, f, "store-delete", 1)
    trashed.unlink()
    assert journal.main(["--claude-dir", str(tmp_path), "restore", run, "old.md"]) == 1
    assert "trash copy missing for old.md" in capsys.readouterr().err


def test_undo_skips_an_uncommitted_snapshot(tmp_path):
    untouched = tmp_path / "untouched.md"
    untouched.write_text("original")
    edited = tmp_path / "edited.md"
    edited.write_text("before")
    run = journal.begin(tmp_path, "P")
    journal.snapshot(tmp_path, run, untouched, "store-write", 1)
    journal.snapshot(tmp_path, run, edited, "store-write", 2)
    edited.write_text("after")
    journal.commit(tmp_path, run, edited)
    msgs = journal.undo(tmp_path, run)
    assert edited.read_text() == "before"
    assert untouched.read_text() == "original"
    assert not any("untouched.md" in m for m in msgs)


def test_undo_skips_an_already_restored_delete(tmp_path):
    f = tmp_path / "old.md"
    f.write_text("bye")
    run = journal.begin(tmp_path, "P")
    journal.delete(tmp_path, run, f, "store-delete", 1)
    journal.restore(tmp_path, run, "old.md")
    journal.undo(tmp_path, run)
    assert f.read_text() == "bye"


def test_cli_exit_codes(tmp_path, capsys):
    assert journal.main(["--claude-dir", str(tmp_path), "begin", "--project", "P"]) == 0
    run = capsys.readouterr().out.strip()
    assert (tmp_path / "retro" / "journal" / f"{run}.json").exists()
    assert journal.main(["--claude-dir", str(tmp_path), "undo", "no-such-run"]) == 1
    assert journal.main(["--claude-dir", str(tmp_path), "restore", run, "missing.md"]) == 1
