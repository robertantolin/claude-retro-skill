"""Two 2026-09-23 defects: a candidate the retro parked as deferred was never raised again, and no
command listed a project's open findings, so each retro hand-filtered findings.tsv."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import candidates as C  # noqa: E402
import scan  # noqa: E402

HEADER = "# last-scan: 2026-09-01T10:00\n" + "\t".join(scan.FINDINGS_COLS) + "\n"


def _row(fid, store, kind, lesson, status="open", found="2026-09-01", evidence="fix it", confidence="high"):
    return "\t".join([fid, found, store, "s1", kind, lesson, evidence, confidence, status, "", ""]) + "\n"


def _sight(cfg, rows, today, count=1):
    return scan.record_candidates(cfg, "C--p", [
        {"category": "repeat-manual", "key": "deploy script rerun", "summary": "ran it by hand", "count": count}],
        today, rows)


def test_deferred_candidate_is_raised_again_on_the_next_sighting(tmp_path):
    fpath = tmp_path / "retro" / "findings.tsv"
    rows = []
    _sight(tmp_path, rows, "2026-09-01")
    out = _sight(tmp_path, rows, "2026-09-02")
    assert out[0]["confirmed"] and out[0]["finding_id"] == "F0001"
    scan.save_findings(fpath, "2026-09-02T10:00", rows)
    # the retro had no room for it and parked it, saying the log would re-raise it on repeat
    assert scan.set_status(tmp_path, "F0001", "deferred:await-repeat", "single sighting; re-raises on repeat")
    _, rows = scan.load_findings(fpath)
    out = _sight(tmp_path, rows, "2026-09-10")
    assert out[0]["confirmed"] and out[0]["finding_id"] == "F0001"
    row = next(r for r in rows if r["id"] == "F0001")
    assert row["status"] == "open" and row["resolved"] == "" and "2026-09-10" in row["reason"]
    # on disk too, for the history scan whose merge keeps disk rows
    _, disk = scan.load_findings(fpath)
    assert next(r for r in disk if r["id"] == "F0001")["status"] == "open"
    assert len(rows) == 1
    assert C.load(tmp_path, "C--p")[0]["status"] == "proposed"


def test_decided_candidate_stays_decided(tmp_path):
    fpath = tmp_path / "retro" / "findings.tsv"
    rows = []
    _sight(tmp_path, rows, "2026-09-01")
    _sight(tmp_path, rows, "2026-09-02")
    scan.save_findings(fpath, "2026-09-02T10:00", rows)
    for status in ("resolved:promote", "denied"):
        scan.set_status(tmp_path, "F0001", status, "done")
        _, rows = scan.load_findings(fpath)
        out = _sight(tmp_path, rows, "2026-09-10")
        assert not out[0]["confirmed"] and out[0]["finding_id"] == ""
        assert rows[0]["status"] == status


def _findings(tmp_path):
    fpath = tmp_path / "retro" / "findings.tsv"
    fpath.parent.mkdir(parents=True)
    fpath.write_text(
        HEADER
        + _row("F0001", "proj-a", "recur", "mem:proj-a/one")
        + _row("F0002", "proj-b", "recur", "mem:proj-b/two")
        + _row("F0003", "global", "recur", "global:Output preferences")
        + _row("F0004", "proj-a", "candidate", "cand:rework-loop/memo", confidence="medium")
        + _row("F0005", "proj-a", "recur", "mem:proj-a/done", status="resolved:approved")
        + _row("F0006", "proj-a", "dormant", "mem:proj-a/quiet", evidence="", confidence="")
        + _row("F0007", "proj-a", "dormant", "mem:proj-a/woke", evidence="", confidence="")
        + _row("F0008", "proj-a", "recur", "mem:proj-a/woke", status="resolved:noted", found="2026-09-05")
        + _row("F0009", "proj-b", "dormant", "mem:proj-b/quiet", evidence="", confidence="")
        + _row("F0010", "proj-a", "dormant", "mem:proj-a/gone", status="resolved:evict", evidence="", confidence=""),
        encoding="utf-8")
    return fpath


def test_open_findings_lists_the_project_and_global_rows_and_its_dormant_lessons(tmp_path):
    _findings(tmp_path)
    open_rows, dormant = scan.open_findings(tmp_path, "proj-a")
    assert [r["id"] for r in open_rows] == ["F0001", "F0003", "F0004"]
    # F0007 is dormant but its lesson matched a correction after the dormant row was written
    assert [r["id"] for r in dormant] == ["F0006"]
    assert scan.open_findings(tmp_path, "proj-c") == ([next(r for r in open_rows if r["id"] == "F0003")], [])


def test_open_cli_prints_both_lists(tmp_path, capsys):
    _findings(tmp_path)
    assert scan.main(["--claude-dir", str(tmp_path), "--open", "proj-a"]) == 0
    out = capsys.readouterr().out
    assert "Open findings for proj-a and global:" in out
    assert "F0001\trecur\thigh\tmem:proj-a/one\tfix it" in out
    assert "F0004\tcandidate\tmedium\tcand:rework-loop/memo" in out
    assert "F0002" not in out and "F0005" not in out
    assert "Dormant lessons in proj-a (no match in 60 days; delete candidates):" in out
    assert "F0006\tmem:proj-a/quiet" in out
    assert "F0007" not in out and "F0009" not in out and "F0010" not in out
    (tmp_path / "retro" / "findings.tsv").unlink()
    assert scan.main(["--claude-dir", str(tmp_path), "--open", "proj-a"]) == 0
    assert capsys.readouterr().out.count("none") == 2
