import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm  # noqa: E402


def test_extract_json_handles_fences_and_prose():
    assert llm.extract_json('Sure:\n```json\n[{"id": 1}]\n```\nDone.') == [{"id": 1}]
    assert llm.extract_json('{"a": [1, 2]} trailing') == {"a": [1, 2]}


def test_extract_json_raises_when_absent():
    try:
        llm.extract_json("no json here")
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_claude_dir_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert llm.claude_dir() == tmp_path
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert llm.claude_dir() == Path.home() / ".claude"


def test_live_call_bills_subscription_and_returns_text():
    # one cheap live call; skipped when the user opts out
    if os.environ.get("RETRO_SKIP_LIVE"):
        return
    out = llm.call("haiku", "Reply with exactly: OK")
    assert "OK" in out
    assert "calls=1" in llm.usage_summary()
