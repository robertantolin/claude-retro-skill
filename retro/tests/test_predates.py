import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scan  # noqa: E402


def _memory(cfg: Path, slug: str, stem: str, origin: str | None) -> Path:
    d = cfg / "projects" / slug / "memory"
    d.mkdir(parents=True, exist_ok=True)
    head = "---\nname: x\ndescription: y\nmetadata:\n  type: feedback\n"
    if origin:
        head += f"  originSessionId: {origin}\n"
    f = d / f"{stem}.md"
    f.write_text(head + "---\n\nlesson\n", encoding="utf-8")
    return f


def test_correction_from_origin_session_predates_lesson(tmp_path):
    _memory(tmp_path, "S", "lesson", origin="abc-123")
    assert scan.predates_lesson(tmp_path, "mem:S/lesson", "abc-123", "2099-01-01T00:00:00")
    assert not scan.predates_lesson(tmp_path, "mem:S/lesson", "other", "2099-01-01T00:00:00")


def test_correction_older_than_file_predates_lesson(tmp_path):
    f = _memory(tmp_path, "S", "lesson", origin=None)
    assert scan.predates_lesson(tmp_path, "mem:S/lesson", "any", "2000-01-01T00:00:00")
    assert not scan.predates_lesson(tmp_path, "mem:S/lesson", "any", "2099-01-01T00:00:00")
    assert f.exists()


def test_non_memory_keys_and_missing_files_never_predate(tmp_path):
    assert not scan.predates_lesson(tmp_path, "global:Output preferences", "any", "2000-01-01T00:00:00")
    assert not scan.predates_lesson(tmp_path, "mem:S/missing", "any", "2000-01-01T00:00:00")
