import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import recur as R  # noqa: E402


def _home(tmp_path):
    cfg = tmp_path / ".claude"
    store = cfg / "projects" / "P" / "memory"
    store.mkdir(parents=True)
    (store / "retry-cap.md").write_text("The send queue allows three Attempts; a fourth corrupts dedupe.\n", encoding="utf-8")
    (store / "MEMORY.md").write_text("- [retry-cap](retry-cap.md)\n", encoding="utf-8")
    (cfg / "CLAUDE.md").write_text("## Output\n- Reports for marketing readers skip protocol detail.\n", encoding="utf-8")
    (cfg / "rules").mkdir()
    (cfg / "rules" / "export.md").write_text("Finance exports use a BOM so accents survive.\n", encoding="utf-8")
    proj = tmp_path / "work"
    proj.mkdir()
    (proj / "CLAUDE.md").write_text("Nightly jobs are scheduled in UTC.\n", encoding="utf-8")
    return cfg, proj


def test_two_of_three_words_in_a_memory_file_counts(tmp_path):
    cfg, proj = _home(tmp_path)
    hits = R.search(cfg, ["attempts", "dedupe", "webhook"], proj)
    assert [(p.name, f) for p, f in hits] == [("retry-cap.md", ["attempts", "dedupe"])]


def test_one_word_is_not_enough(tmp_path):
    cfg, proj = _home(tmp_path)
    assert R.search(cfg, ["attempts", "webhook", "invoice"], proj) == []


def test_stem_and_case_match(tmp_path):
    cfg, proj = _home(tmp_path)
    hits = R.search(cfg, ["Attempt", "DEDUPE", "zebra"], proj)
    assert [p.name for p, _ in hits] == ["retry-cap.md"]


def test_global_rules_and_project_files_are_searched(tmp_path):
    cfg, proj = _home(tmp_path)
    assert [p.name for p, _ in R.search(cfg, ["marketing", "protocol", "x"], proj)] == ["CLAUDE.md"]
    assert [p.parent.name for p, _ in R.search(cfg, ["marketing", "protocol", "x"], proj)] == [".claude"]
    assert [p.name for p, _ in R.search(cfg, ["finance", "accents", "x"], proj)] == ["export.md"]
    assert [p.parent.name for p, _ in R.search(cfg, ["nightly", "utc", "x"], proj)] == ["work"]


def test_missing_project_dir_and_folders_are_fine(tmp_path):
    cfg = tmp_path / ".claude"
    cfg.mkdir()
    assert R.search(cfg, ["a", "b", "c"], tmp_path / "nowhere") == []


def test_cli_prints_none_and_exits_zero(tmp_path, capsys):
    cfg, proj = _home(tmp_path)
    rc = R.main(["--claude-dir", str(cfg), "--project-dir", str(proj), "--words", "zebra", "yak", "gnu"])
    assert rc == 0 and capsys.readouterr().out.strip() == "none"


def test_cli_prints_hit_line(tmp_path, capsys):
    cfg, proj = _home(tmp_path)
    R.main(["--claude-dir", str(cfg), "--project-dir", str(proj), "--words", "attempts", "dedupe", "zebra"])
    out = capsys.readouterr().out.strip()
    assert out.endswith("retry-cap.md\t2 of 3\tattempts dedupe")
