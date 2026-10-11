"""The coach mod writes retro/coach-log.tsv, one row per nudge or fan-out miss. The retro reads it
as optional evidence: an absent, empty or malformed ledger gives an empty result, so the retro
behaves as it did before the reader existed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan  # noqa: E402

HEADER = "run_id\ttimestamp\tproject\tsignal\tcount\taction\tmatched_lesson\n"
ROWS = [
    "r1\t2026-09-01T10:00\tproj-a\tfanout-miss\t11\tline\tnone\n",
    "r1\t2026-09-01T11:30\tproj-a\tfanout-miss\t21\tnone\tnone\n",
    "r2\t2026-09-02T09:00\tproj-a\tfanout-miss\t14\tnone\tnone\n",
    "r3\t2026-09-04T16:45\tproj-b\tfanout-miss\t27\tline\tnone\n",
    "r3\t2026-09-04T17:00\tproj-b\tcorrection\t2\tnudge\tmem:proj-b/x\n",
]
MALFORMED = [
    "r9\t2026-09-05T10:00\tproj-a\tfanout-miss\t40\tline\n",           # six columns
    "r9\t2026-09-05T10:05\tproj-a\tfanout-miss\tmany\tline\tnone\n",  # count not an integer
    "r9\t2026-09-05T10:10\tproj-a\tfanout-miss\t3.5\tline\tnone\n",   # count not an integer
    "\n",
]


def _ledger(cfg: Path, text: str) -> Path:
    p = cfg / "retro" / "coach-log.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _by(rows):
    return {(r["project"], r["signal"]): r for r in rows}


def test_counts_windows_dates_and_read_spread(tmp_path):
    _ledger(tmp_path, HEADER + "".join(ROWS))
    rows = scan.mod_signals(tmp_path)
    assert [(r["project"], r["signal"]) for r in rows] == [
        ("proj-a", "fanout-miss"), ("proj-b", "correction"), ("proj-b", "fanout-miss"),
        ("overall", "correction"), ("overall", "fanout-miss")]
    by = _by(rows)
    a = by[("proj-a", "fanout-miss")]
    assert (a["rows"], a["windows"], a["first"], a["last"]) == (3, 2, "2026-09-01", "2026-09-02")
    assert (a["min"], a["median"], a["max"]) == (11, 14, 21)
    o = by[("overall", "fanout-miss")]
    assert (o["rows"], o["windows"], o["first"], o["last"]) == (4, 3, "2026-09-01", "2026-09-04")
    assert (o["min"], o["median"], o["max"]) == (11, 17.5, 27)
    c = by[("overall", "correction")]
    assert (c["rows"], c["windows"], c["first"], c["last"]) == (1, 1, "2026-09-04", "2026-09-04")
    # read counts are reported for fan-out misses only
    assert "min" not in c and "median" not in by[("proj-b", "correction")]


def test_malformed_rows_are_skipped(tmp_path):
    _ledger(tmp_path, HEADER + "".join(ROWS[:2] + MALFORMED + ROWS[2:]))
    clean = tmp_path / "clean"
    _ledger(clean, HEADER + "".join(ROWS))
    assert scan.mod_signals(tmp_path) == scan.mod_signals(clean)


def test_absent_empty_header_only_and_wrong_header_give_nothing(tmp_path):
    assert scan.mod_signals(tmp_path) == []
    p = _ledger(tmp_path, "")
    assert scan.mod_signals(tmp_path) == []
    p.write_text(HEADER, encoding="utf-8")
    assert scan.mod_signals(tmp_path) == []
    p.write_text(HEADER.replace("run_id", "run") + "".join(ROWS), encoding="utf-8")
    assert scan.mod_signals(tmp_path) == []
    p.write_text("".join(ROWS), encoding="utf-8")
    assert scan.mod_signals(tmp_path) == []
    p.write_text(HEADER + "".join(MALFORMED), encoding="utf-8")
    assert scan.mod_signals(tmp_path) == []


def test_open_cli_prints_the_mod_signals_block_last(tmp_path, capsys):
    _ledger(tmp_path, HEADER + "".join(ROWS))
    assert scan.main(["--claude-dir", str(tmp_path), "--open", "proj-a"]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    head = next(i for i, l in enumerate(lines) if l.startswith("Mod signals"))
    dormant = next(i for i, l in enumerate(lines) if l.startswith("Dormant lessons"))
    assert head > dormant
    block = lines[head + 1:]
    assert "proj-a\tfanout-miss\trows 3\twindows 2\t2026-09-01 to 2026-09-02\treads min 11 median 14 max 21" in block
    assert "overall\tfanout-miss\trows 4\twindows 3\t2026-09-01 to 2026-09-04\treads min 11 median 17.5 max 27" in block
    assert "overall\tcorrection\trows 1\twindows 1\t2026-09-04 to 2026-09-04" in block
    assert "none" not in block


def test_open_cli_has_no_mod_signals_text_without_a_usable_ledger(tmp_path, capsys):
    # absent, empty or malformed: --open prints exactly what it printed before the reader existed
    assert scan.main(["--claude-dir", str(tmp_path), "--open", "proj-a"]) == 0
    absent = capsys.readouterr().out
    assert "Mod signals" not in absent
    assert absent.splitlines()[-1] == "none" and absent.count("none") == 2
    p = _ledger(tmp_path, "")
    for text in ("", HEADER, HEADER.replace("run_id", "run") + "".join(ROWS), HEADER + "".join(MALFORMED)):
        p.write_text(text, encoding="utf-8")
        assert scan.main(["--claude-dir", str(tmp_path), "--open", "proj-a"]) == 0
        assert capsys.readouterr().out == absent


def test_the_ledger_path_comes_from_the_config_dir(tmp_path, capsys, monkeypatch):
    # A real-looking home holds a ledger; the evals point CLAUDE_CONFIG_DIR at a sandbox without
    # one. The sandbox must win, or every eval case would read the user's real ledger.
    real_home = tmp_path / "realhome"
    _ledger(real_home / ".claude", HEADER + "".join(ROWS))
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: real_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(sandbox))
    assert scan.mod_signals(sandbox) == []
    assert scan.main(["--open", "proj-a"]) == 0
    assert "Mod signals" not in capsys.readouterr().out
    # and the same CLI reads the ledger that the config dir does hold
    _ledger(sandbox, HEADER + "".join(ROWS))
    assert scan.main(["--open", "proj-a"]) == 0
    assert "overall\tfanout-miss\trows 4" in capsys.readouterr().out
