import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import settings  # noqa: E402


def test_load_creates_nothing_and_returns_defaults(tmp_path):
    s = settings.load(tmp_path)
    assert s["approve_always"] == [] and s["first_run_done"] is False
    assert not settings.path(tmp_path).exists()


def test_save_and_reload_merge_defaults(tmp_path):
    settings.save(tmp_path, {"approve_always": ["store-write"]})
    s = settings.load(tmp_path)
    assert s["approve_always"] == ["store-write"] and s["session_budget_chars"] == 48000


def test_set_always_and_is_always(tmp_path):
    settings.set_always(tmp_path, "store-write", True)
    assert settings.is_always(tmp_path, "store-write")
    settings.set_always(tmp_path, "store-write", False)
    assert not settings.is_always(tmp_path, "store-write")


def test_unknown_kind_rejected(tmp_path):
    try:
        settings.set_always(tmp_path, "banana", True)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_bar_is_per_project(tmp_path):
    assert not settings.is_raised(tmp_path, "global-line", "P")
    settings.set_bar(tmp_path, "global-line", True, "P")
    assert settings.is_raised(tmp_path, "global-line", "P")
    assert not settings.is_raised(tmp_path, "global-line", "Q")
    assert settings.load(tmp_path)["raised_bar"] == {"P": ["global-line"]}
    settings.set_bar(tmp_path, "global-line", False, "P")
    assert not settings.is_raised(tmp_path, "global-line", "P")
    assert settings.load(tmp_path)["raised_bar"] == {}


def test_legacy_list_bar_applies_to_every_project(tmp_path):
    settings.path(tmp_path).parent.mkdir(parents=True)
    settings.path(tmp_path).write_text(json.dumps({"version": 3, "raised_bar": ["store-write"]}))
    assert settings.load(tmp_path)["raised_bar"] == {"*": ["store-write"]}
    assert settings.is_raised(tmp_path, "store-write", "P")
    assert settings.is_raised(tmp_path, "store-write", "Q")
    # reset-bar without a project clears the kind everywhere, legacy entry included
    assert settings.main(["--claude-dir", str(tmp_path), "reset-bar", "store-write"]) == 0
    assert not settings.is_raised(tmp_path, "store-write", "P")
    assert settings.load(tmp_path)["raised_bar"] == {}


def test_cli_init_show(tmp_path, capsys):
    settings.main(["--claude-dir", str(tmp_path), "init"])
    assert settings.path(tmp_path).exists()
    capsys.readouterr()  # discard the path line printed by init
    settings.main(["--claude-dir", str(tmp_path), "show"])
    out = json.loads(capsys.readouterr().out)
    assert out["version"] == 3


def test_cli_bad_args_exit_2(tmp_path, capsys):
    for argv in (["set-always", "banana", "on"], ["reset-bar"], ["set-history"]):
        assert settings.main(["--claude-dir", str(tmp_path)] + argv) == 2
        err = capsys.readouterr().err.strip()
        assert err and "\n" not in err  # one-line message, not a traceback
    assert not settings.path(tmp_path).exists()  # nothing written by a refused command


def test_cli_good_args_exit_0(tmp_path):
    assert settings.main(["--claude-dir", str(tmp_path), "set-always", "store-write", "on"]) == 0
    assert settings.is_always(tmp_path, "store-write")
    settings.set_bar(tmp_path, "store-write", True, "P")
    settings.set_bar(tmp_path, "store-write", True, "Q")
    assert settings.main(["--claude-dir", str(tmp_path), "reset-bar", "store-write", "P"]) == 0
    assert not settings.is_raised(tmp_path, "store-write", "P")
    assert settings.is_raised(tmp_path, "store-write", "Q")
    assert settings.main(["--claude-dir", str(tmp_path), "reset-bar", "store-write"]) == 0
    assert not settings.is_raised(tmp_path, "store-write", "Q")
