# Changelog

All notable changes to the `/retro` skill. Versions follow [Semantic Versioning](https://semver.org/): a major bump means the skill's behaviour or its data layout changed in a way you should read about before upgrading.

## [3.0.0] - 2026-09-04

The retro now closes its own loop. Until v2 the skill judged its own work; nothing outside the retro checked whether recorded lessons actually stopped mistakes from recurring. v3 adds an independent observer, a health check, and golden tests, and wires their output back into the next retro.

### Added

- **`scan.py`, an independent observer.** Reads your Claude Code session transcripts from a watermark forward, finds the messages where you corrected the assistant (a model classifies each candidate with the assistant's previous turn as context; revisions of scope are not counted as corrections), matches each correction against every recorded lesson, and writes `~/.claude/retro/findings.tsv`. A `recur` row means a lesson existed and failed anyway. A `dormant` row means a lesson has not been touched or matched in 60 days. It also records how you answered each past retro in `~/.claude/retro/decisions.tsv`. Runs on your own Claude subscription through `claude -p`; saves after every session so an interrupted run resumes; retries a failed model call once; `--dry-run` reports what it would read without calling a model; `--since YYYY-MM-DD` backfills.
- **`health.py`.** Prints, for a store, the entry count against the cap, dated filenames, the Machine gotchas word budget, the open findings for that store, the scan's age, and any ledger rows whose store is not a real memory folder. The retro calls it in steps 3 and 6 instead of hand-run shell counts.
- **Findings loop in `SKILL.md` (step 4).** Every retro reads `findings.tsv`, prints the last scan date, and must resolve each open row for the current project or the global file: promote to a mechanism, rewrite the lesson, evict it, or defer with a reason. A finding is valid evidence for a lesson even when the current session had no fresh correction.
- **Golden evals (`evals/`).** Five cases (self-caught slip, one correction, two corrections, recurrence, open findings) run the real skill inside a throwaway home directory with a synthetic session and grade the output. `run_evals.py` records every run's full output and sandbox state in a results file so a failure can be re-graded offline. `BASELINE.md` records the pre-edit and post-edit scores for this release.
- **Unit tests (`tests/`).** 28 tests over the scripts, all stub the model call; `python -m pytest ~/.claude/skills/retro/tests -q`.
- **`CHANGELOG.md`** (this file) and GitHub releases with tags from v1.0.0 on.

### Changed

- **Ledger moved and widened.** The run ledger now lives at `~/.claude/retro/retro-log.tsv` with eight columns: `timestamp`, `store`, `proposed`, `auto-applied`, `deleted`, `empty`, `findings-resolved`, `findings-deferred`. `timestamp` is ISO date plus hour and minute; `store` is the memory folder name or `global`. The line is written on every retro, including an empty one.
- **Empty retro is stated, always.** Whenever no new lesson qualified, the retro writes "Empty retro: nothing durable surfaced" with its reason, even when it resolved findings or pruned entries.
- **Prune order gained a tiebreaker.** Among otherwise equal entries, a lesson listed as dormant in the findings file is evicted first.
- **Applied lines quote their correction.** Each auto-applied lesson is reported with the user's correction it came from, verbatim; findings updates and the ledger line carry no quote.
- **Routing tie-breaker.** A project-only fact phrased as a prohibition ("this project must never X") is a context gap and goes to the store, not to a rule or a hook.
- **Store check line** now includes `Findings: N open, R resolved, D deferred, scan S days old`.
- **Generic wording.** The skill text refers to "the user" throughout; the same file ships publicly and privately.

### Known limitations

- The golden evals pass 13 of 15 runs on this release (pre-edit skill: 4 of 15). The two misses are the model skipping a step it was explicitly told to do, once each; see `evals/BASELINE.md`.
- The scan's first backfill over a large transcript history is slow and costs subscription usage (about an hour and several hundred model calls for 286 sessions). Routine weekly runs are small.
- Developed and tested on Windows 11 with Python 3.14; the scripts are standard library only and use no platform-specific calls, but macOS and Linux are untested.

### Upgrading from v2

1. Replace `~/.claude/skills/retro/` with the new folder (all of it, not only `SKILL.md`).
2. Move your ledger, if you have one: `~/.claude/retro-log.tsv` becomes `~/.claude/retro/retro-log.tsv`, and each row gains a project-folder name in place of the free-text project, plus two trailing `0` columns. The skill does not migrate it for you.
3. Run `python ~/.claude/skills/retro/scan.py --since <date>` once to backfill findings, then weekly without `--since`.
4. Run the evals before and after any future edit to `SKILL.md`.

## [2.0.0] - 2026-08-30

Five changes, each from a failure mode seen in sustained use.

### Changed

- **Zero lessons is the stated default.** The bar is "would knowing this at the start have changed what I did?"; at most one new lesson per retro, a second only for a different correction in the same session. A cap of three was being read as a quota of three.
- **Scope before storage (new step 3).** Machine-level and person-level lessons go to the user-level instruction file, where every project can read them; only project-specific lessons go to a project store. Warns against inventing a global memory directory that is never loaded.
- **Recurrence check before any write (new step 4).** If the lesson already exists in a sibling store, the instruction layer has already failed for it, so the skill proposes a hook and cites the prior entries instead of writing a duplicate.
- **Budgeted pruning.** Session state and dated snapshots are barred from the lesson store; the store is capped at 20 entries with a fixed eviction order.
- **Tiered approval gate.** Lesson-store writes auto-apply and are reported as an undoable done-list; skills, rules, hooks and any CLAUDE.md stop and wait for a diff approval. A prompt on every trivial write trains reflex approval.

### Fixed

- Tier-boundary ambiguity for projects that keep lessons as a `## Lessons Learned` section in CLAUDE.md (those edits wait like any instruction-file change), and three README inaccuracies.

## [1.0.0] - 2026-08-12

### Added

- Initial release of the `/retro` skill: honest session review, a bar for what counts as a lesson, routing to memory, instruction files, skills or hooks, and a human approval gate on every change to standing instructions.
- Structured output: summary table, numbered proposals, explicit accept/edit/reject options, and an empty-retro format.
- README with an install-by-prompt path and a portability section for other agent tools.

[3.0.0]: https://github.com/robertantolin/claude-retro-skill/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/robertantolin/claude-retro-skill/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/robertantolin/claude-retro-skill/releases/tag/v1.0.0
