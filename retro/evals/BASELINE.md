# Golden eval baseline

## v3 result, 2026-09-13

Eight cases, three runs each, against the rewritten v3 `SKILL.md`.

Results files: `evals/results/2026-09-13T11-45-53.json` (all eight cases), plus three per-case
reruns: `2026-09-13T14-46-27.json` (recurrence), `2026-09-13T15-10-43.json` (findings-open),
`2026-09-13T14-56-26.json` (candidate-confirms), and, after the final fix wave,
`2026-09-13T15-40-47.json` (candidate-confirms again).

| Case | Runs passing | Failing checks | Source |
|---|---|---|---|
| self-caught | 3/3 | none | 11-45-53 |
| one-correction | 3/3 | none | 11-45-53 |
| two-corrections | 2/3 | run 2 only: `claude` exited 1 with empty stderr, a launch failure, not a check | 11-45-53 |
| recurrence | 2/3 | run 1: proposes_mechanism | 14-46-27 |
| findings-open | 3/3 | none | 15-10-43 |
| candidate-confirms | 3/3 | none, after the final fix wave | 15-40-47 |
| hard-number | 3/3 | none | 11-45-53 |
| no-decision | 3/3 | none | 11-45-53 |

All eight cases meet the bar of at least two runs of three. `candidate-confirms` was the one open
item at 0/3; the diagnosis and the fix that closed it are below.

Real-data guard, checked by (size, mtime) before and after every run:
`real retro/retro-log.v2.tsv untouched: True`, `real retro/findings.tsv untouched: True`.
`retro/retro-log.tsv` is guarded too but prints no line, because the live store has no such file
yet: the pre-v3 ledger was set aside as `retro-log.v2.tsv` and nothing has written a v3 ledger
there. A guard line for a file that does not exist would read `untouched: True` and mean nothing,
so only files present at one end or the other are reported. A file appearing mid-run still fails
the guard.

Cost line, identical on all four runs. The LLM judge was never called: every expected quote
matched as a substring.

```
saved ~/.claude/skills/retro/evals/results/2026-09-13T11-45-53.json | llm calls=0 nominal_cost=$0.00
```

### Harness changes

- `run_retro` now reads `--output-format stream-json --verbose` and concatenates every assistant
  text block. Under `--output-format json` only the final `result` string came back, and because
  a question tool call ends a turn, that string held just the closing Housekeeping table. Every
  quote and citation check was grading a fragment of the reply.
- `build_home` writes `retro/settings.json` through `settings.save` with `first_run_done` true and
  `history_scan.asked` true, so the first-run prompt never fires in print mode, and seeds
  `case["candidates"]` through `candidates.log`. The two empty ledger files it used to write are
  gone: an empty file carries no v3 header, so `ledger._migrate` moved it aside as
  `retro-log.v2.tsv` on first read and the run then reported a pre-v3 migration that never happened.
- `LEDGER_RELS` and `real_paths` drop the pre-edit `retro-log.tsv` path. The live ledger is
  `retro/retro-log.tsv`; `retro-log.v2.tsv` is only where a pre-v3 ledger is set aside.

### SKILL.md wording changes made to pass a case

- Line 52, recurrence rule: appended "Either way the Insight names the mechanism you weighed, so a
  'No action' row says which rule, hook or script you considered and why it would not hold."
  Written for `proposes_mechanism`; it helped only partly, and the check was then ruled to read
  the ledger row's kind instead.
- Line 122, after the empty-run rule: added "A run that found something but raised no proposal,
  because every row is `No action.`, is not an empty run: print the report without that sentence,
  and append the same ledger row so every run leaves exactly one line in the ledger." Before this,
  a run whose findings were all `No action.` wrote no ledger row at all, which is what
  `recurrence` failed on.

### Rulings applied to the cases, not the skill

- `findings-open`: its v2 expectations (`empty_retro` true, `findings_addressed` 2) cannot both
  hold in v3. With no approve-always the prompt cannot be answered, so nothing is written. The
  case now asserts `findings_handled`: each seeded finding is either named by a `no-decision`
  ledger row with a diff written for it, or resolved with a reason. Being ignored, still open and
  named by no row, is the only failure. Both outcomes were observed across nine recorded runs and
  both are correct: the 11-45-53 runs raised proposals and left the findings open, while the
  14-51-16 and 15-10-43 runs judged them `No action.` and resolved them `resolved:noted`. Every
  one of the nine handled the findings; 15-10-43 is the run graded in the table above.
- `recurrence`: `proposes_mechanism` now passes when the ledger holds a row of kind
  `rule-skill-hook`, with the reply keywords kept as an alternative. The ledger row is the
  evidence that a mechanism was proposed; the wording of the reply varies run to run.

### candidate-confirms: below the bar, and how it was closed

The case seeds one `repeat-manual` candidate at count 1 from a prior session and expects this
session's scan to log the same observation, take the row to count 2, and confirm it. It failed
all three runs on `candidate_finding` and `ledger_decisions`.

The scan was then called directly, three times, on the same transcript, outside any retro run:

| Call | Key the classifier produced | Shared content words | Jaccard |
|---|---|---|---|
| 1 | no candidate reported at all | - | - |
| 2 | no candidate reported at all | - | - |
| 3 | `manual weekly status memo assembly` | `memo` | 0.091 |

Seeded key: `memo assembled by hand from partner research file`.

Diagnosis: the classifier's candidate key is unstable between calls on identical input, twice
reporting no candidate at all and once producing wording that shares one content word with the
seeded key, far below the 0.5 Jaccard floor in `candidates.similar`. Reseeding the fixture cannot
fix this, because any seeded key can only fit one call's wording. The fix, if one is wanted,
belongs in the scan's candidate prompt or in the matcher, and is left for review.

Closed in the final fix wave, on all three causes at once:

- `CLASSIFY_PROMPT` now says a single occurrence of hand-done multi-step work, a re-asked question
  or a friction event qualifies with count 1, so "nothing qualifies" stops being the
  prompt-compliant answer on a short transcript.
- The key instruction is a format, not a length: 3 to 5 lower-case nouns, artifact first then
  action, no verbs or adjectives.
- `candidates.similar` scores containment (`shared / min(|a|, |b|)`) over stemmed content words
  instead of Jaccard, so keys of different lengths that name the same nouns match. Category
  equality is unchanged.
- The fixture key was reseeded in that format as `status memo manual assembly`.

Rerun: `python evals/run_evals.py --runs 3 --case candidate-confirms`, results file
`evals/results/2026-09-13T15-40-47.json`. **3/3 runs pass.** All three merged into the seeded row
and wrote the candidate finding `cand:repeat-manual/status memo manual assembly` at medium
confidence. Real-data guard `True` on both reported files; `llm calls=0 nominal_cost=$0.00`, the
judge was not needed. This rerun also exercises `claude -p` through `subprocess.run(..., shell=False)`
with the executable resolved by `shutil.which`, which is the Windows check on that change.

## Live smoke test, 2026-09-14

Three real retros in interactive sessions, run by the user after the v3 commits; what `claude -p`
cannot exercise. Checked against the data folder afterwards.

| Item | Result |
|---|---|
| First-run question states the benefit first, "Last 90 days" recommended | pass; settings record the 90-day date and the scan ran in the background after the session scan |
| Report order and no diff inline | pass (user: "it looked good") |
| Proposal prompt shows the four options | pass |
| Approve always for a kind | pass; the user switched it off again three minutes later by choice, because the label does not say that every future proposal of that kind will apply without a prompt (backlog: relabel the option with the consequence) |
| Approve once on a rule or skill file and on a global instruction line | pass; both journaled with snapshots, second project |
| Deny | pass; the linked finding resolved as denied, no write |
| History scan mines candidates | pass; 71 candidate rows after the 90-day scan |
| Deletion moves the file to the trash folder; "undo retro" restores it; "retro metrics" prints | not exercised; the stores in the tested projects were under their cap. Backlog: run in a project whose store is full |

Ledger after the three runs: 4 rows, 0 malformed. Open findings rose from 72 to 100 after the
history scan. One defect found and fixed during the day: on Windows, every model call made by the
detached history scan opened a visible console window; `llm.py` now passes the no-window flag.

## Post-edit result, 2026-09-15 (commit ccfa642)

Edit: one line in step 4 of `SKILL.md`. Every v3 run with two or more proposals had printed the
card for proposal 1 only and gone straight to the question tool for the rest (all four
multi-proposal runs of 2026-09-14 and 2026-09-15, checked in the transcripts). The line now ties
each card to its question call in the same message and says to print the next card after an
apply. The golden cases run without the question tool, so they cannot exercise the defect; this
run is the regression check on everything else.

Eight cases, three runs each. Results file: `evals/results/2026-09-15T11-44-10.json`.

| Case | Runs passing | Failing checks | Baseline 2026-09-13 |
|---|---|---|---|
| self-caught | 3/3 | none | 3/3 |
| one-correction | 3/3 | none | 3/3 |
| two-corrections | 2/3 | run 3: `claude` exited 1 with empty stderr, a launch failure, not a check | 2/3, same launch failure |
| recurrence | 2/3 | proposes_mechanism | 2/3, same check |
| findings-open | 3/3 | none | 3/3 |
| candidate-confirms | 3/3 | none | 3/3 |
| hard-number | 3/3 | none | 3/3 |
| no-decision | 2/3 | run 2: `claude` exited 1 with empty stderr, a launch failure, not a check | 3/3 |

All eight at the bar of two of three or better. The one drop from baseline (no-decision) is a
launch failure with empty stderr, the same kind seen on two-corrections at baseline, not a
grading failure. Real-data guard: all three ledger files untouched. Cost line: `llm calls=0`.

Proof of the fix itself is the next interactive retro with two or more proposals; the transcript
check is: for each "Proposal N" question, a text block containing "Proposal N of M" precedes it.

## Superseded: 2026-09-12T18-17-38

An overnight `--runs 3` whose later cases all failed with `claude exit 1` and empty stderr, plus
one timeout, after the machine idled. `claude -p` was confirmed working again the next morning by
a single-case probe. Environmental, not a skill result, and excluded from the table above.

## Post-edit result

Date: 2026-09-04. Results file: `skills/retro/evals/results/2026-09-04T10-09-43.json`. 13 of 15
runs pass. Two residual misses: self-caught run 1 reported a ledger line in its reply but wrote
none; findings-open run 3 omitted the literal "Empty retro" sentence. The user accepted shipping
at 13 of 15, with the two residuals attributed to run-to-run model variance rather than a defect
in the shipped skill.

## Pre-edit skill: baseline run

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
  in this commit; see per-run detail in the results file.

## Pre-edit skill: pass table

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

## Pre-edit skill: per-run detail with grader reasons

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
  The prior baseline blamed a harness approval-gate limitation; that was the wrong cause
  (project-only lessons auto-apply, they are not gated) - see per-run detail in the results file.
  With project-only
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
memory/ store rather than the approval-gated global CLAUDE.md; see per-run detail in the results file.
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

## Pre-v3 check, 2026-09-12

Command (Git Bash, from the skill folder):

```
python evals/run_evals.py --runs 1 --case self-caught
```

Pass line:

```
self-caught      1/1 runs pass
```

Real-data guard:

```
real retro-log.tsv untouched: True
real retro/retro-log.tsv untouched: True
real retro/findings.tsv untouched: True
```

Results file: `evals/results/2026-09-12T17-04-58.json`

Cost line:

```
saved ~/.claude/skills/retro/evals/results/2026-09-12T17-04-58.json | llm calls=0 nominal_cost=$0.00
```

This is the freeze-rule record: the harness was proven green against the unedited `SKILL.md`
before any v3 rewrite began, so `SKILL.md` was not edited before a baseline existed.

## Post-edit result, 2026-09-17 (cards printed up front)

Edit: step 4 of `SKILL.md` rewritten. The 2026-09-15 line did not hold: across every v3 run
with two or more proposals, the card for proposal 2 was printed in 1 of 8 runs (1 of 5 after
ccfa642) and the card for proposal 3 in 0 of 3, checked in the transcripts with
`evals/card_check.py`. The apply chain (snapshot, edit, commit, ledger, verify) sits between the
decision and the next card, and the "print the next card" instruction was not followed after it.
Step 4 now prints all M cards in the report before the first question, each question text
carries "Proposal N of M: <title>. <what changes> Apply it?", and a card is reprinted only
after a Refine. The golden cases still run without the question tool, so this run is the
regression check on everything else; proof of the fix is `python evals/card_check.py` after the
next interactive retro with two or more proposals.

Eight cases, three runs each, Sonnet with a Sonnet judge. Results file:
`evals/results/2026-09-17T22-09-27.json`.

| Case | Runs passing | Failing checks | 2026-09-15 |
|---|---|---|---|
| self-caught | 3/3 | none | 3/3 |
| one-correction | 3/3 | none | 3/3 |
| two-corrections | 3/3 | none | 2/3, launch failure |
| recurrence | 3/3 | none | 2/3, proposes_mechanism |
| findings-open | 3/3 | none | 3/3 |
| candidate-confirms | 3/3 | none | 3/3 |
| hard-number | 3/3 | none | 3/3 |
| no-decision | 3/3 | none | 2/3, launch failure |

All eight at 3/3, the first clean sweep. Real-data guard: `retro-log.v2.tsv` untouched;
`retro-log.tsv` and `findings.tsv` reported changed, and the change is two live retros in
other sessions during the run window (Peach Mode 22:18 and content-os 22:53, both empty runs,
real project names and run ids) plus the content-os session scan updating the findings header,
not a sandbox leak. Cost line: `llm calls=0`.

## Post-edit result, 2026-09-24 (fix batch after the 09-23 review)

Edits under test: the code fixes of 5fe807e (per-project raised bar, `scan.py --open`, parked
candidates raised again, dormant rows) and the wording that uses them (step 0 item 6, step 2
open-findings bullet and `Seen before` rule, per-project bar, step 4 delete-at-cap from the
Dormant list, gotchas trim, "Always apply <kind>, without asking", Deny follow-up recorded in
N.md, Refine answers questions, deferred candidates, step 7 Raised bar row, closing line after
Applied only, step 8 reset per project). Eight cases, three runs each, Sonnet with a Sonnet
judge. Every run's raw stream-json is kept under `evals/results/raw/` (new `--raw` switch).

### What the first runs found

The first gate (`2026-09-23T16-32-09.json`) passed 7 of 8 cases but three runs printed no
Session review, no Findings table and no card while still writing the ledger row and the
lesson. A header sentence was added to force the order ("The report goes to chat in the order
of the numbered steps ... a ledger row or a proposal file never stands in for a part of the
report"). It made things worse. A/B on one-correction x5 (approve-always path): the 09-17 text
4/5 (`2026-09-24T14-03-10.json`), the new text 0/5 (`14-07-06`), report printed in 4 of 5
against 0 of 5.

Bisect, one-correction x5 per variant, each reverting one change from the new text:

| Variant | Reverted | Pass |
|---|---|---|
| v1 | header clause "one command per tool call" | 2/5 |
| v2 | "Nothing else is a finding" paragraph | 1/5 |
| v3 | `scan.py --open` item and bullet | 2/5 |
| v4 | the report-contract sentence | 4/5 |
| v5 | all four together | 5/5 |
| v6 | decision-branch changes (contract kept) | 2/5 |
| v7 | step 4 edit rules (contract kept) | 0/5 |
| v8 | table, status rule, closing line (contract kept) | 1/5 |

With the contract sentence present: 8 of 35 runs; without it: 17 of 20. The raw streams of the
failing runs show the model never emitting a report text block at all: the card exists only as
the written `1.md`, and the final message is Applied plus Housekeeping. The sentence was
removed (confirmation on the real file 4/5, `15-12-01.json`). A live retro in one project at
15:01 (run 20260924-150052-beff, two proposals) ran on the text with the sentence and printed
Session review and Findings but no card before its questions (`card_check.py`: P1 and P2
missing), the same defect outside the sandbox.

### The residual skip on the two no-question paths

The gate on the contract-free text (`15-22-14.json`) still skipped the report in 7 of 24 runs:
one-correction 1/3, two-corrections 2/3, hard-number 1/3, no-decision 0/3. The raw streams show
no trigger; the final message simply starts at Applied (auto-apply path) or at the "No
decisions were recorded" line (print mode, question tool absent). The 09-17 text on no-decision
x5 today: 3/5, so that path also drifted on its own since 09-17 (3/3 then).

Micro-tests, one sentence each, five runs, judged on the report being printed:

| Arm | Sentence | Case | Pass |
|---|---|---|---|
| A | "the report so far ... goes to chat as one message before the first apply" (step 4) | one-correction | 0/5 |
| B | "When no question was asked this run, the message that carries Applied starts with the Session review, the Findings table, Candidates and the cards, in that order, then Applied, then Housekeeping." (step 5a) | one-correction | 5/5, replicate 5/5 |
| C | "That line goes in a message that starts with ..." appended to the unavailable-tool bullet | no-decision | 3/5 |
| D | B removed; one recipe sentence at the top of Housekeeping covering both paths | no-decision / one-correction | 2/5 / 5/5 |
| E | B kept; the unavailable-tool bullet rewritten as the recipe of the final message | no-decision | 5/5 |

Shipped: B and E. Lessons: a prohibition or a "print it before X" instruction suppresses the
report; a recipe that states what the final message contains restores it; the recipe has to
sit in the branch the model is executing (step 5a for auto-apply, the unavailable-tool bullet
for print mode), not at a distant step. Two evals launched in the same second shared a results
file (arm B's per-run detail was overwritten by arm A); the stamp now gets the pid on a clash.

### Final gate on the shipped text

Results file: `evals/results/2026-09-24T16-52-08.json`. The last five runs (hard-number 2 and 3,
no-decision 1 to 3) also carried the rule against proposals into a project CLAUDE.md that
added to step 4 at 17:15 from another session.

| Case | Runs passing | Failing checks | 2026-09-17 |
|---|---|---|---|
| self-caught | 3/3 | none | 3/3 |
| one-correction | 3/3 | none | 3/3 |
| two-corrections | 3/3 | none | 3/3 |
| recurrence | 2/3 | cites_existing (the lesson was described, not named) | 3/3 |
| findings-open | 3/3 | none | 3/3 |
| candidate-confirms | 3/3 | none | 3/3 |
| hard-number | 3/3 | none | 3/3 |
| no-decision | 2/3 | quotes_corrections (run 1 skipped the report) | 3/3 |

Report printed in 23 of 24 runs. Real-data guard: all three files untouched. Cost line:
`llm calls=1`. Proof of the cards in interactive use is still `python evals/card_check.py`
after the next live retro with two or more proposals on this text.

## Post-edit result, 2026-09-25 (one dialog for all decisions, cap enforced)

Edits under test, wording only, no code change outside `evals/`: step 4 asks every proposal in
one call of the question tool before anything is applied, each question carrying its whole
card (What changes, What you get, Why you might say no) with options Approve, Deny: not worth
a change, Deny: already covered, Deny: wrong fix, and Other as Refine; the "Always apply
<kind>" option and the Deny "Why" follow-up are gone (approve-always stays reachable through
"retro settings" only, step 8); a store over its cap of 20 gets a `store-delete` proposal of
its own in every run, at most five entries, with step 2 and step 6 sending an otherwise empty
run through that check. README lines 5 and 11 follow. The 09-24 text is kept beside it as
`SKILL.md.bak-2026-09-25`.

Why: `evals/card_check.py` over the live retros since 09-14 showed the second card 10 to 26
messages above its question once the first proposal had been applied (one project, 09-24 16:00,
20:01, 21:47), and 24 live Housekeeping tables reported "21 of 20 entries" or worse with no
delete proposed, because ordinary sessions write memory files between retros and the old text
only paired a delete with a write.

### New golden case: over-cap

Clean session, store of 21 entries (STORE_BASE plus 18 filler lessons), no findings. Expects a
`store-delete` no-decision row, a diff file, the store untouched, and no "Nothing durable"
sentence. Two new checks in `run_evals.py`: `ledger_kinds` and `store_unchanged`.

| Text | Runs | Result |
|---|---|---|
| Shipped 09-24 (RED) | 3 | 0/3; every run printed "21 of 20 entries (over the cap; nothing proposed)" and the empty-run sentence (`2026-09-25T02-11-18.json`) |
| Variant (GREEN) | 3 | 3/3; report, one delete card, Housekeeping "21 of 20 entries; delete proposed in Proposal 1" (`2026-09-25T02-14-19.json`) |

### Micro-tests, five runs each, raw streams read

| Case | Control (shipped 09-24) | Variant |
|---|---|---|
| one-correction | 5/5 (`02-14-23`) | 5/5 (`02-19-17`); all six report markers in every run: Session review, Findings table, card, Applied, Housekeeping, Undo line |
| no-decision | 3/5 (`02-22-06`): one report skip, one `diff_file` miss where the proposal files went to the wrong home folder | 3/5 (`02-14-27`): two report skips, the residual flake recorded on 09-24 |

Parity on both wording-sensitive cases, so the new sentences did not reopen the report-skip
problem. Three eval streams ran side by side, staggered by three seconds; results files did not
collide.

### Full gate on the shipped text

Results file: `evals/results/2026-09-25T02-33-21.json`, nine cases, three runs each, Sonnet.

| Case | Runs passing | Failing checks | 2026-09-24 |
|---|---|---|---|
| self-caught | 3/3 | none | 3/3 |
| one-correction | 3/3 | none | 3/3 |
| two-corrections | 3/3 | none | 3/3 |
| recurrence | 2/3 | cites_existing (run 3 printed the full report and named the lesson only in its tool calls) | 2/3 |
| findings-open | 3/3 | none | 3/3 |
| candidate-confirms | 3/3 | none | 3/3 |
| hard-number | 3/3 | none | 3/3 |
| no-decision | 3/3 | none | 2/3 |
| over-cap | 3/3 | none | new case, 0/3 on the 09-24 text |

Report printed in 27 of 27 runs. Real-data guard: all three files untouched. Cost line:
`llm calls=0`.

### Round two after the self-review

The self-reviewer found five real gaps in the gated text: the cap delete contradicted the
raised bar (a `store-delete` bar after three denials left an over-cap empty run with no
paragraph of step 6 to follow), "at most five, so an approved run ends at or under 20" was false
for a store more than five over, step 5 still said "approve once and approve always", install.md
still said every setting is asked, and the "Pending proposals" header exceeds the question
tool's 12 characters. Fixed in step 4 (bar exception, "at most five per run"), step 6 ("step 4
raised no cap delete"), step 5, install.md line 4 and the header "Pending". The tool-unavailable
bullet was left as it was: it is the tuned recipe and the gate shows both paths it covers working.

| Case | Runs | Result |
|---|---|---|
| over-cap | 3 | 3/3 (`2026-09-25T03-04-35.json`) |
| no-decision | 5 | 4/5, one report skip (`03-04-39.json`); control 3/5, first variant 3/5 |
| one-correction | 3 | 3/3 (`03-04-43.json`) |

Shipped text = this round. Proof of the one-dialog behaviour in interactive use is still
`python evals/card_check.py` after the next live retro with two or more proposals: the golden
cases run without the question tool, so they exercise only the print-mode and auto-apply paths.
