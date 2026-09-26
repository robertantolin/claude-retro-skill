# claude-retro-skill

[![tests](https://github.com/robertantolin/claude-retro-skill/actions/workflows/tests.yml/badge.svg)](https://github.com/robertantolin/claude-retro-skill/actions/workflows/tests.yml)
[![release](https://img.shields.io/github/v/release/robertantolin/claude-retro-skill)](https://github.com/robertantolin/claude-retro-skill/releases)
[![license](https://img.shields.io/github/license/robertantolin/claude-retro-skill)](LICENSE)

A `/retro` skill for [Claude Code](https://claude.com/claude-code). At the end of a session the agent reviews its own work, checks whether each lesson already exists, proposes at most three changes to its memory, instructions or automation, and applies only what you approve. Every write is journaled and one command undoes a run.

**In plain terms:** your assistant tells you where it went wrong today, suggests what it should learn, and you say yes or no to each suggestion before anything changes.

**Privacy first.** The skill reads your Claude Code session transcripts. For the session you are closing it sends the model your own messages, a short tail (up to 600 characters) of Claude's reply before each one, and the one-line titles of your existing lessons, global instruction bullets and rules files. It does not send tool output or file contents. The optional one-time history scan does the same for past sessions in the range you choose, plus the text of past retro replies. Model calls go through your own `claude` login; nothing goes anywhere else. Everything the skill stores lives under `~/.claude/retro/`.

## Install

As a plugin, from inside Claude Code:

```
/plugin marketplace add robertantolin/claude-retro-skill
/plugin install retro@claude-retro-skill
```

Or copy the folder into your user-level skills directory:

```bash
git clone https://github.com/robertantolin/claude-retro-skill.git
cp -r claude-retro-skill/retro ~/.claude/skills/retro
```

Or paste this into any Claude Code session and let the agent do it:

```
Clone https://github.com/robertantolin/claude-retro-skill and copy its retro/
folder verbatim into my user-level Claude Code skills directory
(~/.claude/skills/retro on Mac/Linux, %USERPROFILE%\.claude\skills\retro on
Windows). Do not modify SKILL.md. Confirm the files exist, then tell me how
to invoke the skill.
```

Then end any working session with:

```
/retro
```

The first run creates `~/.claude/retro/` and asks one question: whether to scan your session history once (last 90 days, everything, or skip). See `retro/install.md` for the details.

## What a retro looks like

```
## Session review
- Attempted: migrate the export job to the new queue. Landed, after one correction.
- Corrected by you: "the finance export must stay UTF-8 with BOM, Excel garbles it otherwise."
- Rework: none.

## Findings
| # | Problem | Insight | Status |
|---|---|---|---|
| 1 | The export was written without the BOM and Excel showed broken accents. | A project lesson naming the encoding rule, read at the start of every session. | New. Proposal 1. |

Candidates logged, not yet confirmed
- The release checklist was assembled by hand from three files again; a second sighting makes it a proposal for a script.

**Proposal 1 of 1: Record the finance export encoding rule**
- What changes: adds one lesson file to this project's memory folder and its index line.
- What you get: the next session starts knowing the export needs UTF-8 with BOM.
- Why you might say no: the rule may belong in the export script itself, where it cannot be forgotten.
- Exact edit: ~/.claude/retro/proposals/20260926-101502-3f1a/1.diff
```

Then one dialog asks about every proposal. Each question repeats its card, so you decide without scrolling back, and the options are **Approve**, **Deny: not worth a change**, **Deny: already covered**, **Deny: wrong fix**. Type anything else to refine: the proposal is rewritten to your instruction and asked again. Nothing is applied until every answer is in. The report ends with an **Applied** list, a **Housekeeping** table (store size against its cap, open findings, scan coverage, settings) and the undo command for the run.

A session that went normally ends with "Nothing durable surfaced this session." That is the expected result most days.

## What it proposes, and where it goes

Every proposal has exactly one kind and one target:

| Kind | Target |
|---|---|
| `store-write` | Add or edit a lesson in the project's memory folder (`~/.claude/projects/<project>/memory/`), plus its index line |
| `store-delete` | Remove a lesson from a project store; this is how a store gets back under its cap |
| `global-line` | A line in your user-level instruction file, for lessons about your machine or your standing preferences |
| `rule-skill-hook` | A rules file, a skill, a hook, or `settings.json`: automation for a lesson that instructions have already failed to hold |
| `other-file` | Any other path |

Nothing is ever proposed into a project's `CLAUDE.md`, which is loaded every session and should stay short. A lesson that already exists somewhere is never written a second time: the proposal becomes a mechanism (a rule, hook or script) or "No action" with the reason.

## The evidence bar

- **A correction counts** when your words reached the agent wrong and a concrete change would have prevented it. "Be more careful" is not a change.
- **An observation waits for a second sighting.** Repeated manual work, revisited decisions, rework loops, tool friction and time sinks are logged as candidates and become a proposal when a later session in the same project repeats them, or at once when one session shows three or more rounds of the same thing.
- **At most three proposals per retro.** Lessons are at most 120 words and carry no dates or narrative.
- **Stores are capped at 20 lessons.** A store over the cap gets a delete proposal of its own every run, dormant lessons first, until it is back at 20.
- **Denials teach the retro.** Deny one kind of change three times in a row in a project and that kind stops being proposed there; it is logged instead until you say "retro settings" and reset it.

## Undo and the things you can say

| Say | What happens |
|---|---|
| `undo retro` | Reverts the last run: every file it edited is restored from its snapshot and every file it deleted comes back from the trash. It refuses if a file changed since. |
| `restore <file name>` | Brings back one deleted file from the last run |
| `retro settings` | Shows and changes approve-always kinds and raised bars |
| `retro metrics` | Lessons that recurred after being written, proposal conversion, denials by kind |
| `scan history` | Runs the background history scan again |

Deleted files are kept in `~/.claude/retro/trash/<run>/` for 30 days.

## What ships in the folder

`retro/SKILL.md` is the procedure. The scripts beside it are standard-library Python and hold all state under `~/.claude/retro/`: `scan.py` (session and history scans, findings), `ledger.py` (one row per proposal and the raised bar), `journal.py` (snapshots, trash, undo), `settings.py`, `candidates.py`, `health.py` (store health and metrics), `llm.py` (model calls through `claude -p`). `tests/` has 108 unit tests that make no model calls; `evals/` has nine golden cases that run the real skill in a throwaway home and grade the report, with `BASELINE.md` recording every score.

## Requirements

- Claude Code in an interactive session. The proposal dialog uses the question tool; in `claude -p` the retro prints its proposals, records no decision and offers them again next time.
- Python 3.10 or later on the path as `python` or `python3`.
- A `claude` login, for the one model call the session scan makes.
- Developed and tested on Windows 11; the scripts use no platform-specific calls, but macOS and Linux are untested. The evals need the login file that macOS keeps in the Keychain instead, so they do not run there.

## Beyond Claude Code

The loop is portable even though this implementation is not: an honest review, a bar that permits zero lessons, a recurrence check before any write, lessons routed to the one place they fire, a capped store that shrinks as well as grows, and a human deciding every change. Any agent that keeps standing instruction files can run that loop; swap the targets for your tool's rules files and automation hooks.

## Versions

Release notes live in [CHANGELOG.md](CHANGELOG.md) and on the [releases page](https://github.com/robertantolin/claude-retro-skill/releases). The current release is 4.0.0. If you are upgrading from 3.x, read its "Upgrading from 3.x" section: the ledger migrates itself, and the retro now asks before every change.

## Contributing and security

Bugs and ideas go to the [issue tracker](https://github.com/robertantolin/claude-retro-skill/issues); see [CONTRIBUTING.md](CONTRIBUTING.md) for how the skill text is tested before it changes. Security problems go through [private reporting](https://github.com/robertantolin/claude-retro-skill/security/advisories/new), as described in [SECURITY.md](SECURITY.md).

Maintained by [Robert Antolin](https://github.com/robertantolin).

## License

MIT, see [LICENSE](LICENSE).
