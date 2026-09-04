# Golden eval baseline

Date: 2026-09-03
Command: `python skills/retro/evals/run_evals.py --runs 3`
Results file: `skills/retro/evals/results/2026-09-03T21-58-51.json` (gitignored, kept locally)

Two earlier baseline attempts are superseded and excluded from the table below:
- 2026-09-03T21-18: 15/15 runs failed on a cwd/slug mismatch in `build_home()`/`run_retro()`
  that prevented `claude -p --resume` from ever finding the transcript. Fixed in commit
  `18c71dc`.
- 2026-09-03T21-37: ran against the original `one-correction`/`two-corrections` fixtures, whose
  corrections were user-general (routed to the approval-gated global CLAUDE.md by design, per
  spec section 6/12), so `new_entries` could never pass for them, and one fixture quote was only
  3 words against the judge prompt's 5-word floor. Both fixtures rewritten as project-only facts
  in this commit; see item 3 of the fix-round-2 ruling.

## Pass table

| Case | Runs passing | Failing checks across the 3 runs |
|---|---|---|
| self-caught | 1/3 | ledger_line |
| one-correction | 1/3 | quotes_corrections |
| two-corrections | 2/3 | new_entries |
| recurrence | 0/3 | ledger_line |
| findings-open | 0/3 | findings_addressed, ledger_line |

Overall: 4/15 runs pass every check for their case. Real-data guard, checked by (size, mtime)
before and after the whole run: `real retro-log.tsv untouched: True`,
`real retro/retro-log.tsv untouched: True`, `real retro/findings.tsv untouched: True`.
2 LLM judge calls made, `nominal_cost=$0.03` (down from 6 calls / $0.08 in the superseded run,
because the normalized-substring check now short-circuits the judge whenever a required quote is
already present verbatim, case-folded and whitespace-collapsed).

## Per-run detail with grader reasons

| Case | Run | Result | Failing checks | Reason |
|---|---|---|---|---|
| self-caught | 1 | fail | ledger_line | ledger file stayed empty |
| self-caught | 2 | fail | ledger_line | same |
| self-caught | 3 | pass | - | ledger file got a line this run |
| one-correction | 1 | fail | quotes_corrections | new_entries and ledger_line passed (the lesson auto-applied, no approval gate, since it is now project-scoped); but the skill's final reply was terse and never restated the correction: `"No proposals requiring approval this round - nothing rose to a rule/hook/skill level. Store is now 4 of 20 entries, 0 dated files, no pruning needed."` (149 chars, no quote). quote_decisions: judge, and the judge correctly answered false. |
| one-correction | 2 | pass | - | full session-review output quoted the correction verbatim: `[the user] corrected - *"This project's retry queue is capped at 3 attempts per message; a 4th attempt corrupts the dedupe table."*`. quote_decisions: substring, 0 judge calls. |
| one-correction | 3 | fail | quotes_corrections | same pattern as run 1: auto-applied silently, terse closing summary with no quote (`"No proposals requiring approval this run - everything qualifying was an auto-apply..."`). quote_decisions: judge, correctly false. |
| two-corrections | 1 | pass | - | both quotes present verbatim (substring, 0 judge calls); 2 new files written |
| two-corrections | 2 | fail | new_entries | both quotes present verbatim (substring); but the skill judged the two corrections traced to "one coherent lesson" (a shared dedupe-table fact behind both the retry cap and the report-counting rule) and wrote a single memory file (`send-dedupe-table.md`) instead of two, saying so explicitly: `"Two distinct quoted corrections in one session, but one coherent lesson - written as a single memory entry rather than two."` |
| two-corrections | 3 | pass | - | both quotes present verbatim (substring); 2 new files written |
| recurrence | 1 | fail | ledger_line | ledger file stayed empty |
| recurrence | 2 | fail | ledger_line | same |
| recurrence | 3 | fail | ledger_line | same |
| findings-open | 1 | fail | findings_addressed, ledger_line | 0 of 2 planted findings rows were marked resolved:/deferred: (current skill does not read findings.tsv, expected per the plan); ledger file stayed empty |
| findings-open | 2 | fail | findings_addressed, ledger_line | same |
| findings-open | 3 | fail | findings_addressed, ledger_line | same |

## Expected-versus-defect classification

- `findings_addressed` (findings-open, 3/3 fail): **expected**, called out in the plan: the
  current skill does not read the findings file.
- `ledger_line` (self-caught 2/3, recurrence 3/3, findings-open 3/3 fail; 8/15 total): **flaky,
  not a flat "never"** - the skill's own instruction to append a ledger line is not followed on
  every run of the same case (self-caught wrote it in only 1 of its 3 runs). A real inconsistency
  in the skill worth its own defect ticket.
- `new_entries` (two-corrections run 2 only, 1/3 fail; one-correction and the other two
  two-corrections runs pass): **corrected diagnosis, replacing the superseded run's wrong one.**
  The prior baseline blamed a harness approval-gate limitation; that was the wrong cause per the
  controller's Q1 ruling (project-only lessons auto-apply, they are not gated). With project-only
  fixtures, `new_entries` mostly passes (4/5 of the write-expecting runs across both cases). The
  one remaining failure is the skill's own judgment call to consolidate two quoted corrections
  into a single coherent memory entry rather than writing two, which is a defensible reading of
  "one coherent lesson" but is inconsistent with its own behavior in the other two runs of the
  same case, on the same transcript.
- `quotes_corrections` (one-correction 2/3 fail): **not a grader defect this time.** Both failing
  runs auto-applied the memory write and then gave a terse closing summary that genuinely omits
  the correction (confirmed by reading the full captured output, not just the check result); the
  normalized-substring check correctly found no match and the judge fallback correctly agreed. In
  the superseded run, by contrast, the miss was a grader defect (the quote was present verbatim
  and the judge still said no); the substring short-circuit added in this commit closes that
  specific failure mode, evidenced here by 2/2 successful substring matches in two-corrections
  across all 3 runs (0 judge calls needed) versus 6 judge calls in the superseded run.

## Files as shipped

`cases.py`: `one-correction` and `two-corrections` rewritten with project-only corrections (an
operational quirk of this project's retry queue and send-report counting, not a fact derivable
by reading the repo, and not a user-general preference) so the lessons route to the project
memory/ store rather than the approval-gated global CLAUDE.md, per the controller's Q1 ruling.
`run_evals.py`: sandbox slug keyed off the real `work` directory (fix round 1); credentials
deleted from a `--keep` sandbox before it is left on disk; a three-file real-data guard
(`retro-log.tsv`, `retro/retro-log.tsv`, `retro/findings.tsv`) by (size, mtime); a
normalized-substring check that short-circuits the judge per-quote; results now also carry the
judge model, every raw judge reply, which check path (substring or judge) decided each quote, and
text snapshots of the sandbox store, findings file and both ledger paths, so the three
filesystem-dependent checks can be re-graded offline; results are written after every run via
temp file plus `os.replace`; the stamp has second resolution; a bare `except Exception` records
any run failure instead of only `RuntimeError`; the unused `slug` parameter was removed from
`grade()`.
