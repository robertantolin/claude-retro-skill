# Contributing

Thanks for looking. This is a one-person project, so the process is short.

## Reporting a bug

Open an issue with the bug report form. The most useful bug report includes the retro's printed report (redact anything personal), the `python health.py` output, and your Claude Code version. If the retro wrote something it should not have, run `python journal.py undo <run>` first and say so in the issue.

## Proposing a change

Open an issue before a pull request for anything that changes `SKILL.md`. The skill text is tuned against golden evals, and a sentence that reads well can still make the model skip part of the report; the results of past attempts are in `retro/evals/BASELINE.md`. Small fixes to the Python scripts can go straight to a pull request.

## Running the checks

From the `retro/` folder:

```bash
python -m pytest tests -q            # unit tests, no model calls
python evals/run_evals.py --runs 3   # golden evals, makes model calls through your claude login
```

The evals need a `claude` login file at `~/.claude/.credentials.json`, so they run on Windows and Linux but not on macOS, where the login is kept in the Keychain. A change to `SKILL.md` needs the evals before and after; record the numbers in `retro/evals/BASELINE.md`.

## Style

Plain sentences, no dates or narrative inside `SKILL.md`, standard-library Python only, and every command in the skill runs as a script by path (never inline `python -c`), because project hooks on some machines block the inline form.
