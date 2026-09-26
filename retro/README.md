# retro

Privacy first. The skill scans your Claude Code session transcripts. For the session you are closing it sends the model your own messages, a short tail (up to 600 characters) of Claude's reply before each one, and the one-line titles of your existing lessons, global instruction bullets, and rules files. It does not send tool output or file contents. The optional one-time history scan does the same for past sessions in the range you choose, plus the text of past retro replies so it can learn how you answered them; you can bound that range or skip it. Everything it stores lives under `~/.claude/retro/`.

A session-end retrospective skill for Claude Code. It reads what went wrong in the session you are closing, checks whether the lesson already exists, and proposes at most three changes, all decided in one dialog that carries each proposal's card: approve, deny with a one-line reason, or refine. Nothing is written or deleted without that decision unless you have set the kind to approve-always through "retro settings". A store that has grown past its cap of 20 lessons gets a delete proposal on its own. Every write is journaled and can be undone with one command.

## What it does

1. Runs a classifier over the finishing session to find your corrections and up to three candidate observations (repeated manual work, revisited decisions, rework loops, tool friction, time sinks).
2. Prints a short report: session review, a findings table, candidates, proposals, housekeeping.
3. Asks every proposal in one dialog, each question holding its own card; a denial picks its reason from the options. Refine rewrites the proposal and asks again. Nothing is applied until every answer is in. A kind of change you deny three times in a row in one project stops being proposed in that project and is logged instead; say "retro settings" to turn it back on.
4. Applies approved changes through a journal so `python journal.py undo <run>` reverses them. Deleted files go to a trash folder for 30 days.
5. Keeps outcome metrics: which lessons recurred after being written, which kinds of proposal you deny, how often candidates confirm. `python health.py --metrics`.

## Install

See `install.md`. Requires Claude Code with the question tool (interactive sessions), Python 3.10 or later, and a `claude` login for the scan's model calls.

## Files

`SKILL.md` the procedure; `scan.py` classification and history scan; `settings.py`, `ledger.py`, `journal.py`, `candidates.py` state under `~/.claude/retro/`; `health.py` report and metrics; `evals/` golden cases; `tests/` unit tests (`python -m pytest tests -q`).

## Evidence bar for candidates

A candidate is logged on first sight and shown only as one line. It becomes a proposal when a later session in the same project produces a matching one, or at once when a single session shows three or more rework rounds or three or more repeats of the same manual sequence. A denied candidate is not raised again while its record exists; records are kept for denied candidates and expire only for single-sighting candidates that were never proposed.
