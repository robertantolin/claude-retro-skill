---
name: retro
description: Use at the end of any working session, or when the user asks for a retrospective, lessons learned, or a post-mortem of what went wrong this session.
license: MIT
metadata:
  author: Robert Antolin
  source: https://github.com/robertantolin/claude-retro-skill
---

Run a retrospective on THIS session. Plain language, full sentences, no tool names where a plain description exists. The retro proposes and asks; it applies only what the user approves or has set to approve-always. It never writes a TSV or JSON file directly; every state change goes through the commands below.

Paths: skill folder `~/.claude/skills/retro/`, data folder `~/.claude/retro/`. Run every command with `python` from the skill folder, one command per tool call, exactly as written here: a command wrapped in `python -c`, a heredoc or a shell function trips project hooks and loses the step. `<project>` is this project's memory folder name under `~/.claude/projects/` (the transcript's parent folder name). `<transcript>` is this session's `.jsonl` file under that folder (the newest one whose contents match this session).

## 0. Prepare

1. `python settings.py show`. It prints JSON with the keys `approve_always`, `raised_bar`, `first_run_done`, `history_scan` and `session_budget_chars`. A missing settings file is not an error; the command prints the defaults. When `"first_run_done"` is `false`, this is the first run: do step 0a before continuing.
2. `python journal.py begin --project <project>` and keep the printed run id as `<run>`.
3. `python scan.py --session <transcript>` and keep its JSON. The command can instead exit 1 with an `error` in its JSON, and two of those errors are normal. `history scan in progress; session scan skipped` means a background scan of your history holds the lock; `cannot read transcript: ...` means this session's file could not be read. On either one, say so in one line, continue the retro from your own memory of the session, and set the Housekeeping "Session scan" row to `skipped, history scan running` for the first and `failed` for the second.
4. `python health.py --store <project>` and keep the output for Housekeeping.
5. `python ledger.py pending --project <project>` and `python ledger.py recent --project <project>`. Pending rows are proposals from an earlier retro that got no decision; recent rows are what other sessions raised in the last 24 hours.
6. `python scan.py --open <project>`. Its `Open findings` block is the list step 2 reads; its `Dormant lessons` block is where a delete at cap takes its entry (step 4).

### 0a. First run

Run `python settings.py init`. Then ask ONE question with the question tool, header "History scan", text: "The retro can scan your past sessions once. Benefit: corrections you have already made become findings on day one, lessons that have gone quiet are flagged, and pattern spotting starts from your history instead of from zero. It reads the transcripts on this machine within the range you pick and sends the model your own messages, the last 600 characters of the Claude reply before each one, the one-line titles of your existing lessons, global instruction bullets, and rules files, and, for a history scan, the text of past retro replies. It never sends tool output or the contents of your files. Which range?" Options: "Last 90 days (Recommended)", "Everything", "Skip". Then:
- Last 90 days: `python settings.py set-history <date>` where `<date>` is today minus 90 days in `YYYY-MM-DD`.
- Everything: `python settings.py set-history everything`.
- Skip: `python settings.py set-history skip`.

Then `python settings.py mark-first-run` and continue with step 0.2.

Start the history scan only after step 0.6, never here: it holds a lock for as long as it runs, and a session scan that starts while the lock is held is skipped. For Last 90 days run `python scan.py --since <that same date> --background`; for Everything run `python scan.py --background` with no `--since`; for Skip run nothing.

## 1. Session review

Three bullets, from the session scan output plus your own context. The scan's corrections are evidence; you may add context, and you may not drop a scan-reported correction without saying why.

- **Attempted:** what the session set out to do and whether it landed. Two sentences at most.
- **Corrected by you:** each correction in one sentence, quoting the user's words. "None" if none.
- **Rework:** artifacts redone or loops of three or more rounds, with the cause. "None" if none.

A slip you caught before the user saw it is not a correction and is not listed.

## 2. Findings

A finding is one of:
- A correction this session that qualifies: it reached the user wrong AND there is a concrete action that would have prevented it. "Be more careful" is not an action.
- A scan match: the session scan reported `match_key` with high or medium confidence and `predates` false. The lesson already exists and failed again.
- An open finding for this project or `global`, of type `recur` or `candidate`: every row in the `Open findings` block of the `scan.py --open` output from step 0.
- A candidate the scan marked `confirmed` or `hard`.

Nothing else is a finding: not a slip you caught before the user saw it, not a conflict you settled yourself, not a thing you merely noticed. A session with no correction and no confirmed candidate has no findings; it still gets the over-cap check in step 4, and goes to step 6 when that raises nothing.

Print the table `# | Problem | Insight | Status`. Problem is what went wrong in plain words. Insight is what would prevent it. Status is `New. Proposal N.`, `Seen before. Proposal N.`, or `No action.` with the reason in Insight. `Seen before` means the scan reported a `match_key` for it or a `recent` row's title matches; a finding this scan created, a candidate included, is `New`. Every row with a proposal number gets exactly one proposal in step 4.

When `ledger.py pending` returned rows, put them on one line under the table: "Undecided from a previous retro: <title>; <title>" (when the proposal file is gone, show the finding id instead). Then ask ONCE with the question tool, header "Pending", options "Raise them" and "Drop them".
- Raise them: each pending row becomes a proposal in this run's numbered list, still inside the limit of three.
- Drop them: for each row, `python ledger.py append --run-id <run> --project <project> --proposal <N from the row> --finding-id <F-id or none> --kind <kind from the row> --decision none --refine-count 0 --applied n` (decision `none`, not `deny`, so dropping stale rows never raises the bar for that kind), and when the row carries a finding id also `python scan.py --resolve <F-id> --status denied --reason "dropped from pending"`.

Then, before choosing any proposal:
- Recurrence: search `~/.claude/projects/*/memory/`, `~/.claude/CLAUDE.md`, `~/.claude/rules/`, and this project's CLAUDE.md for a distinctive phrase. A hit means the lesson exists: the proposal is a mechanism (rule, hook, script) or "No action", never a second copy. Either way the Insight names the mechanism you weighed, so a "No action" row says which rule, hook or script you considered and why it would not hold.
- Duplicate check: if a `recent` row's title matches, cite it in Status instead of raising the proposal again.
- Raised bar: `settings.py show` lists `raised_bar` per project. A kind listed under this project, or under `*`, is not proposed. Record it instead with `python candidates.py log --project <project> --category <category> --key "<key>" --summary "<one line>"`, where `<category>` is one of `repeat-manual`, `revisited`, `rework-loop`, `tool-friction` or `time-sink` and any other value is refused as a bad argument. Say in Status that the bar is raised for that kind, so the point was noted rather than proposed. This is the only place the retro logs a candidate itself.

At most three proposals per retro. Prefer the one with the strongest evidence.

## 3. Candidates

Print "Candidates logged, not yet confirmed" with one line per scan candidate that is neither confirmed nor hard: what was observed, and what it would become if it repeats. Omit the section when there are none. Apart from the raised-bar case in step 2, do not log candidates yourself; the scan did it.

## 4. Proposals

For each proposal N, decide its kind:

| Kind | Target |
|---|---|
| `store-write` | Add or edit a lesson file in `~/.claude/projects/<project>/memory/`, plus its MEMORY.md line |
| `store-delete` | Remove a lesson file from a project store (evictions at cap go here) |
| `global-line` | A line in `~/.claude/CLAUDE.md` |
| `rule-skill-hook` | A `.claude/rules/`, `.claude/skills/` or hook file, or `settings.json` |
| `other-file` | Any other path |

Never propose adding a lesson or rule to a project's `CLAUDE.md` (it is loaded every session and kept under 200 lines). A project-scoped rule goes to a `.claude/rules/` file (`rule-skill-hook`) or the project memory store (`store-write`). A proposal may still shorten or correct an existing project `CLAUDE.md` line as `other-file`.

Write the exact edit as a unified diff to `~/.claude/retro/proposals/<run>/N.diff` and the four bullets to `~/.claude/retro/proposals/<run>/N.md`, whose first line is `# Proposal N of M: <imperative title>`.

Every edit, whatever its kind, carries no dates, commit hashes or narrative. Lesson entries are at most 120 words and follow the store's existing format. Machine-level or user-general lessons go to `global-line`, never a project store. A store at cap (20 entries on the health.py line for this project) means a `store-write` is paired with a `store-delete` proposal naming the entry to remove. A store over cap gets a `store-delete` proposal of its own in every run, including a run with no finding: it removes as many entries as the store is over, at most five per run, and it counts toward the three proposals. The entries to remove are the rows of the `Dormant lessons` block from step 0 while it has any, otherwise the entries you judge least useful, with the reason for each. When the bar is raised for `store-delete` in this project (step 2), no cap delete is proposed and nothing is logged for it; the Lesson store row of Housekeeping says the store is over cap and the bar is raised. A `global-line` into Machine gotchas when that section has fewer than 35 free words (the `Machine gotchas:` line of health.py) shortens or removes an existing gotcha in the same diff so the section stays within 350 words, and What-changes names the line cut.

Print all M proposal cards in the report, one after another, directly after Candidates and before any question is asked. Each card:

**Proposal N of M: <title>**
- What changes: one or two sentences, naming the file in plain words.
- What you get: the behaviour that is different next time.
- Why you might say no: one honest sentence. Every proposal has one.
- Exact edit: `<full path to N.diff>`

Then ask for every decision in one call of the question tool, before anything is applied: one question per proposal, all in the same call, in proposal order (the tool takes up to four questions and a retro has at most three proposals). Each question carries its whole card, so the user decides from the dialog without scrolling back to the report: header "Proposal N", text "Proposal N of M: <title>. What changes: <the What-changes sentences> What you get: <that sentence> Why you might say no: <that sentence> Apply it?", and four options in this order: "Approve", "Deny: not worth a change", "Deny: already covered", "Deny: wrong fix". Words typed under Other are a Refine. A proposal whose kind is on approve-always (set only through "retro settings", never offered in the dialog) gets no question.

When every answer is in, act on the proposals in order:
- Approve: apply (step 5); `python ledger.py append --run-id <run> --project <project> --proposal N --finding-id <F-id or none> --kind <kind> --decision approve-once --refine-count <n> --applied y --verified <y|n|na>`.
- A kind on approve-always: apply (step 5); the same ledger row with `--decision auto`; list it under Applied.
- Deny, any of the three: append `Denied: <the words after "Deny:", or the words typed under Other>` as the last line of `N.md`. Then the ledger row with `--decision deny --applied n`; `python scan.py --resolve <F-id> --status denied --reason "<that answer>"` when the finding has an id; for a candidate finding also `python candidates.py status --project <project> --category <c> --key "<key>" denied`. When the ledger command prints a `bar raised` line, repeat it to the user in plain words: this kind is now logged instead of proposed in this project until they say "retro settings".
- Refine, the words typed under Other: when they are an edit instruction, rewrite the proposal to it, overwrite `N.diff` and `N.md`, print the card again, increment the refine count, and ask about that proposal alone, with the same question shape and options. When they are a question or a remark, answer it in one or two sentences, print the card again unchanged, and ask again; that counts as a refine too. When they are plainly a reason for saying no, they are a Deny with those words as the reason. The second answer is acted on like a first one.
- If the question tool is unavailable or errors: a ledger row with `--decision no-decision` for each proposal, then one final message: the Session review, the Findings table, Candidates, the cards, the line "No decisions were recorded; the next retro in this project will offer these again.", then Housekeeping.

Findings with `No action.` and an id: `python scan.py --resolve <F-id> --status resolved:noted --reason "<why>"` when the lesson or mechanism already exists. A candidate finding set aside only because you lack the details a mechanism needs gets `--status deferred:<what is missing>` instead, so its next sighting raises it again; `resolved:` closes it for good.

The only statuses `--resolve` accepts are `open`, `denied`, `no-decision`, and any status beginning `resolved:` or `deferred:`. Anything else is refused as a bad argument, so keep to the statuses named in this file.

A `python candidates.py status` call for a key the candidates file does not hold exits 1 and changes nothing. When that happens, say so in one line and carry on.

## 5. Applying an approved proposal

Never edit a target file without the journal.
- Add or edit: `python journal.py snapshot --run <run> --path <file> --kind <kind> --proposal N`, make the edit, `python journal.py commit --run <run> --path <file>`. Repeat per file, including MEMORY.md.
- Delete: `python journal.py delete --run <run> --path <file> --kind store-delete --proposal N`, then remove its MEMORY.md line with snapshot and commit.
- Verify: re-read the file and confirm the diff applied; `--verified y` only when you read it back, `--verified n` when the read-back differs (say so), `--verified na` for a rule, skill or hook that cannot be exercised now.
- Close the finding: once the write is committed, a proposal that came from a finding with an id gets `python scan.py --resolve <F-id> --status resolved:approved --reason "<proposal title>"`. This applies to Approve and to the approve-always path alike.
- For a candidate finding that was approved: `python candidates.py status --project <project> --category <c> --key "<key>" promoted` and `python scan.py --resolve <F-id> --status resolved:promote` in place of `resolved:approved`.

Snapshot, commit and delete are also what makes the run undoable: a file changed outside those steps cannot be put back later.

## 5a. Applied

After the last proposal and before Housekeeping, print the heading "Applied" and one line per file this run wrote, naming the file and what happened to it: edited, created, or moved to trash. Omit the heading and the section entirely when the run wrote nothing. When no question was asked this run, the message that carries Applied starts with the Session review, the Findings table, Candidates and the cards, in that order, then Applied, then Housekeeping.

## 6. Empty run

When steps 2 and 3 produce no finding and no candidate, and step 4 raised no cap delete: print Session review, then the sentence "Nothing durable surfaced this session.", then Housekeeping, and append one ledger row: `python ledger.py append --run-id <run> --project <project> --proposal 0 --finding-id none --kind none --decision none`.

A run that found something but raised no proposal, because every row is `No action.`, is not an empty run: print the report without that sentence, and append the same ledger row so every run leaves exactly one line in the ledger.

## 7. Housekeeping

Always last. A table with these rows, values from the `health.py` output and the session scan:

| Item | Value |
|---|---|
| Lesson store | `N of 20 entries`, from the line health.py prints for this project, and, when a delete was proposed, which proposal |
| Global gotchas budget | `W of 350 words`, from the `Machine gotchas:` line of health.py (only when a `global-line` was proposed; state the number after the proposal) |
| Open findings for this project | the number from the `Findings:` line of health.py |
| History scan | the `History scan:` line from health.py |
| Session scan | `ok`, `truncated to the last N messages` where N is `messages_seen` from the scan JSON, `skipped, history scan running`, or `failed` |
| Approve-always | the kinds, or `none` |
| Raised bar | the kinds on the `Raised bar` line of health.py for this project, or `none` |

If the `health.py --store <project>` output carried the one-time line `Ledger: pre-v3 ledger moved to retro-log.v2.tsv`, add one sentence under the table saying the older ledger was set aside under that name and the current one starts from this version.

Then, when the Applied section was printed, one closing line: "Undo this run with: python journal.py undo <run>". A run that wrote nothing has nothing to undo, so the line is omitted. Nothing goes after the closing line.

## 8. Requests the user may make in any session

- "retro settings": run `python settings.py show`, explain each approve-always kind and each raised bar (per project) in one line, and offer `python settings.py set-always <kind> on|off` (the only way a kind gets onto approve-always; the proposal dialog never offers it) or `python settings.py reset-bar <kind> <project>` (without the project, the kind is reset in every project).
- "undo retro" or "undo <run>": `python journal.py undo <run>` and print its output. When the user names no run, take the newest file in `~/.claude/retro/journal/`, whose name is the run id with `.json` removed, and pass that id as the argument; the command needs a run id and is refused as a bad argument without one. It refuses, and changes nothing, when a file has been edited since the retro touched it; print the reason and stop. An undo puts back only what that run recorded: files edited through a snapshot and commit, and files the run removed through the journal's delete step. Anything else changed during the session stays as it is, so say that plainly rather than describing undo as a full rewind.
- "restore <file>": `python journal.py restore <run> <file name>`. This puts back a single file the run removed, matched on the file name, so pass the name rather than the full path. It does not reverse an edit; undo is what reverses edits.
- "retro metrics": `python health.py --metrics`.
- "scan history": `python scan.py --background`.
