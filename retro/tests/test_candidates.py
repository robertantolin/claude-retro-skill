import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidates as C  # noqa: E402


def test_log_new_then_confirm_on_second_sighting(tmp_path):
    row, ok = C.log(tmp_path, "P", "rework-loop", "Memo trimmed repeatedly", "four trim rounds", "2026-09-01")
    assert row["count"] == 1 and ok is False and row["status"] == "open"
    row, ok = C.log(tmp_path, "P", "rework-loop", "memo trimmed  repeatedly", "again", "2026-09-05")
    assert row["count"] == 2 and ok is True and row["last_seen"] == "2026-09-05"
    assert len(C.load(tmp_path, "P")) == 1


def test_fuzzy_match_same_category_only(tmp_path):
    C.log(tmp_path, "P", "repeat-manual", "assemble three files by hand", "x", "2026-09-01")
    row, ok = C.log(tmp_path, "P", "repeat-manual", "three files assembled by hand again", "y", "2026-09-02")
    assert ok is True and row["count"] == 2
    row, ok = C.log(tmp_path, "P", "time-sink", "assemble three files by hand", "z", "2026-09-02")
    assert ok is False and row["count"] == 1


def test_first_sighting_always_counts_one(tmp_path):
    row, ok = C.log(tmp_path, "P", "time-sink", "manual export step", "s", "2026-09-01")
    assert row["count"] == 1 and ok is False
    assert [r["count"] for r in C.load(tmp_path, "P")] == [1]


def test_bad_category_rejected(tmp_path):
    with pytest.raises(ValueError):
        C.log(tmp_path, "P", "vibes", "k", "s", "2026-09-01")


def test_bad_date_rejected(tmp_path):
    with pytest.raises(ValueError):
        C.log(tmp_path, "P", "time-sink", "k", "s", "yesterday")
    assert not C.path(tmp_path, "P").exists()


def test_denied_row_never_confirms_again(tmp_path):
    C.log(tmp_path, "P", "revisited", "pricing question", "a", "2026-09-01")
    C.set_status(tmp_path, "P", "revisited", "pricing question", "denied")
    row, ok = C.log(tmp_path, "P", "revisited", "pricing question", "b", "2026-09-02")
    assert row["count"] == 2 and ok is False and row["status"] == "denied"


def test_cap_drops_oldest_singletons(tmp_path):
    for i in range(C.CAP + 2):
        C.log(tmp_path, "P", "tool-friction", f"k{i}a k{i}b k{i}c", "s", f"2026-08-{(i % 28) + 1:02d}")
    rows = C.load(tmp_path, "P")
    assert len(rows) == C.CAP


def test_expire_removes_old_count_one(tmp_path):
    # the two time-sink keys share no content word, so containment matching keeps them apart
    C.log(tmp_path, "P", "time-sink", "old export step", "s", "2026-06-01")
    C.log(tmp_path, "P", "time-sink", "fresh deploy check", "s", "2026-09-01")
    C.log(tmp_path, "P", "revisited", "old but seen twice", "s", "2026-06-01")
    C.log(tmp_path, "P", "revisited", "old but seen twice", "s", "2026-06-02")
    assert C.expire(tmp_path, "P", "2026-09-10") == 1
    keys = {r["key"] for r in C.load(tmp_path, "P")}
    assert keys == {"fresh deploy check", "old but seen twice"}


def test_denied_singleton_survives_expire(tmp_path):
    today = date.today()
    old = (today - timedelta(days=100)).isoformat()
    C.log(tmp_path, "P", "revisited", "denied old pattern", "s", old)
    C.set_status(tmp_path, "P", "revisited", "denied old pattern", "denied")
    C.log(tmp_path, "P", "revisited", "vanishing open singleton", "s", old)
    assert C.expire(tmp_path, "P", today.isoformat()) == 1
    keys = {r["key"] for r in C.load(tmp_path, "P")}
    assert keys == {"denied old pattern"}


def test_denied_singleton_survives_cap(tmp_path):
    C.log(tmp_path, "P", "tool-friction", "denied singleton pattern", "s", "2026-07-01")
    C.set_status(tmp_path, "P", "tool-friction", "denied singleton pattern", "denied")
    for i in range(C.CAP + 1):
        C.log(tmp_path, "P", "tool-friction", f"k{i}a k{i}b k{i}c", "s", f"2026-08-{(i % 28) + 1:02d}")
    rows = C.load(tmp_path, "P")
    assert len(rows) == C.CAP
    assert "denied singleton pattern" in {r["key"] for r in rows}


def test_similar_matches_keys_that_share_the_nouns():
    # containment over stemmed content words, not Jaccard: a short key wholly inside a longer one
    # is the same observation written two ways, and plural or past-tense endings do not block it
    assert C.similar("memo assembly", "weekly status memo manual assembly") is True
    assert C.similar("export scripts", "export script run") is True
    assert C.similar("status memo assembly", "deploy pipeline retry timeout") is False


def test_validate_reports_bad_rows(tmp_path):
    C.log(tmp_path, "P", "time-sink", "slow deploy step", "s", "2026-09-01")
    assert C.validate(tmp_path) == []
    with C.path(tmp_path, "P").open("a", encoding="utf-8") as f:
        f.write("2026-09-02\tvibes\tk1\ts\t1\t2026-09-02\topen\n")
        f.write("2026-09-02\ttime-sink\tk2\ts\t1\t2026-09-02\tmaybe\n")
        f.write("2026-09-02\ttime-sink\tk3\ts\tmany\t2026-09-02\topen\n")
        f.write("2026-09-02\ttime-sink\tk4\n")
    bad = C.validate(tmp_path)
    assert len(bad) == 4
    assert all(b.startswith("P line ") for b in bad)


def test_cli_log_prints_confirmed_flag(tmp_path, capsys):
    args = ["--claude-dir", str(tmp_path), "log", "--project", "P", "--category", "rework-loop",
            "--key", "memo trimmed", "--summary", "s", "--date", "2026-09-01"]
    assert C.main(args) == 0
    assert C.main(args) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].endswith("confirmed=no") and out[1].endswith("confirmed=yes")
    missing = ["--claude-dir", str(tmp_path), "status", "--project", "P", "--category", "rework-loop",
               "--key", "nothing resembling that", "denied"]
    assert C.main(missing) == 1
