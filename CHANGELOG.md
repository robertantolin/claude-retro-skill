# Changelog

All notable changes to the `/retro` skill. Versions follow [Semantic Versioning](https://semver.org/): a major bump means the skill's behaviour or its data layout changed in a way you should read about before upgrading.

## [Unreleased]

## [4.0.0] - 2026-09-26

The retro now asks before every change, decides all of them in one dialog, and can undo any run. Read "Upgrading from 3.x" before installing: the data files under `~/.claude/retro/` change shape, and the skill now needs Claude Code's question tool, so it is Claude Code only.

### Added

- **Proposal cards, decided in one dialog.** Each retro raises at most three proposals. A proposal is a card: what changes, what you get, why you might say no, and the path to its exact diff. All cards are asked in one question dialog with the options Approve, Deny: not worth a change, Deny: already covered, Deny: wrong fix; anything typed under Other is a refine, which rewrites that proposal and asks again. Nothing is applied until every answer is in.
- **Five kinds of change**, each with one target: `store-write` (a lesson file plus its index line), `store-delete`, `global-line` (your user-level instruction file), `rule-skill-hook`, `other-file`. Nothing is ever proposed into a project's CLAUDE.md.
- **`journal.py`.** Every write goes through a snapshot and a commit, deleted files go to `~/.claude/retro/trash/<run>/` for 30 days, and "undo retro" (`python journal.py undo <run>`) puts a whole run back. "restore <file>" brings back one deleted file.
- **`settings.py`** and `~/.claude/retro/settings.json`: approve-always per kind (set only by saying "retro settings"), a raised bar per project (three denials in a row of one kind stop it being proposed in that project until you reset it), first-run and history-scan state.
- **`candidates.py`** and `~/.claude/retro/candidates/<project>.tsv`. The session scan logs observations in five categories: repeated manual work, revisited decisions, rework loops, tool friction, time sinks. One becomes a proposal on its second sighting, or at once when a single session shows three or more rounds or repeats.
- **A session scan on every retro** (`scan.py --session`): one model call classifies this session's corrections and candidates before the report is written. The first run offers a one-time background history scan (last 90 days, everything, or skip). `scan.py --open` lists open findings and dormant lessons; `scan.py --resolve` closes a finding with a status and a reason.
- **Over-cap pruning.** A store above 20 lessons gets a delete proposal of its own every run, at most five entries at a time and dormant lessons first, until it is back at the cap.
- **`health.py --metrics`**: lessons that recurred after being written, proposal conversion, denials by kind, candidate confirmation, median time to first decision.
- **A Housekeeping table** at the end of every report: store size against the cap, the gotchas word budget, open findings, scan coverage, approve-always kinds, raised bars.
- **Evals grow from five to nine golden cases**, graded from the stream-json output, with `--raw` to keep every run's stream and `evals/card_check.py` to audit real transcripts for cards printed next to their question. Unit tests: 108 (31 in 3.0.1).
- `README.md` and `install.md` inside the skill folder, and `license` and `metadata` fields in the `SKILL.md` frontmatter per the Agent Skills specification.

### Changed

- **Memory-store writes and deletes no longer auto-apply.** 3.x applied them and reported a done-list; 4.0 asks for every kind unless you have put that kind on approve-always.
- **Report shape.** Session review (attempted, corrected by you, rework), a Findings table (`# | Problem | Insight | Status`), Candidates, the proposal cards, Applied, Housekeeping. Diffs live in `~/.claude/retro/proposals/<run>/N.diff` instead of inline in the report.
- **Ledger.** `~/.claude/retro/retro-log.tsv` is one row per proposal with ten columns: `run_id, timestamp, project, proposal, finding_id, kind, decision, refine_count, applied, verified`. Only `ledger.py` writes it.
- **`findings.tsv`** gains a `reason` column and the statuses `denied`, `no-decision`, `resolved:<why>` and `deferred:<what is missing>`. Rows written by 3.x are read as they are.
- Lesson entries are at most 120 words and carry no dates, commit hashes or narrative. A global line into a full Machine gotchas section trims an existing line in the same diff so the section stays within 350 words.
- The scan launches `claude` without a shell (`shutil.which`, `shell=False`) and no longer flashes a console window per model call on Windows.

### Removed

- The "Always apply this kind" option from the proposal dialog, and the follow-up question after a denial: the reason is now one of the Deny options. Approve-always remains a setting.
- The inline "In plain terms" block and the inline diffs in the report; the card and the diff file replace them.

### Fixed

- A first-run race between the session scan and the background history scan: the history scan holds a lock, and a session scan that meets it is skipped and says so instead of failing.
- Candidate matching compares stemmed content words by containment instead of Jaccard, so a short key matches a longer one that contains it.
- A parked candidate is raised again on its next sighting instead of being closed for good.
- The second proposal card was dropped from the report once the first proposal had been applied; all cards now print before the first question, and the single dialog carries each card in full.

### Upgrading from 3.x

1. Replace `~/.claude/skills/retro/` with the new folder, all of it.
2. Your ledger migrates itself: on first use, a `retro-log.tsv` without the new header is moved aside as `retro-log.v2.tsv` and a fresh ledger starts. Nothing is deleted. (3.0.0 said the skill does not migrate the ledger; 4.0 does.)
3. `findings.tsv` and `decisions.tsv` from 3.x are read as they are.
4. The first retro asks whether to run a history scan. If you already backfilled with 3.x, "Skip" keeps what you have; a new scan re-reads your transcripts within the range you pick.
5. Run the retro from an interactive Claude Code session. In `claude -p` there is no question tool, so the retro prints its proposals, records no decision, and offers them again next time.

## [3.0.1] - 2026-09-04

### Fixed

- **The scan no longer reports a lesson's own origin as a recurrence.** `scan.py` matched corrections against every lesson, including the correction that created the lesson in the first place, then handed the retro a `recur` row for it. A correction is now skipped when it comes from the session recorded in the memory file's `originSessionId`, or when it is older than the file itself. The first retro on v3.0.0 hit this on its first two findings. Summary line gains a `predates` count; three unit tests added (31 total).

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

[Unreleased]: https://github.com/robertantolin/claude-retro-skill/compare/v4.0.0...HEAD
[4.0.0]: https://github.com/robertantolin/claude-retro-skill/compare/v3.0.1...v4.0.0
[3.0.1]: https://github.com/robertantolin/claude-retro-skill/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/robertantolin/claude-retro-skill/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/robertantolin/claude-retro-skill/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/robertantolin/claude-retro-skill/releases/tag/v1.0.0
