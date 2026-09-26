# Installing retro

1. Copy this folder to `~/.claude/skills/retro/`.
2. Open any project in Claude Code and type `/retro` at the end of a session.
3. On the first run the skill creates `~/.claude/retro/` with default settings (no kind of change is approved automatically) and asks whether to scan your session history: last 90 days, everything, or skip. The scan reads your transcripts under `~/.claude/projects/` and sends your messages to the model; it runs in the background and its progress is in `~/.claude/retro/scan.log`.
4. The history scan is asked on the first run; approve-always is never asked in a proposal dialog. Say "retro settings" in any session to see or change every setting.

Undo the last retro: say "undo retro". Restore one deleted file from the last retro: say "restore <file name>". Metrics: say "retro metrics".

Where `python` is not on the path, use `python3`; the skill's commands accept either.

Tests: `cd ~/.claude/skills/retro && python -m pytest tests -q`. Golden evals (makes model calls): `python evals/run_evals.py --runs 3`.

The evals copy `~/.claude/.credentials.json` into each sandbox, so they do not run on macOS, where that login is kept in the Keychain and no such file exists. Their output under `evals/results/` carries session text and absolute paths from the machine that ran them, so publish this folder from git, which ignores that directory, and never by copying the folder.
