---
name: retro
description: Use at the end of any working session, or when the user asks for a retrospective, lessons learned, or a post-mortem of what went wrong this session.
---

Run a retrospective on THIS session. Be concise and honest; the loop must shrink as well as grow.

**The expected result is an empty retro.** The store is a working set, not a journal. The cap on lessons is a ceiling, not a quota; an empty retro is the normal, expected result.

## 1. Review the session
From the actual conversation: what was attempted, what failed or needed the user's correction or rework, what worked. At most 3 bullets per category. Cite the specific mistakes and corrections, never a rosy recap.

## 2. Decide whether anything is worth keeping
A lesson qualifies only if BOTH hold:
- **Trigger:** it reached the user wrong. Either the user corrected it (quote the correction), or an artifact had to be redone (name it), or a recorded lesson recurred (cite the entry, or the findings row from step 4). A slip you caught yourself before it reached the user is the system working; discard it.
- **Counterfactual:** name the concrete action that would have been different had this been known at the start. "I would have been more careful" is not an action.

**At most ONE new lesson per retro.** A second new lesson is allowed only if it quotes a different correction from the user in the same session; rework and self-caught slips never earn a second slot. Beyond that, further items are allowed only if each is a recurrence promotion (step 4) or a deletion (step 6). Zero is the normal result: write "Empty retro: nothing durable surfaced" plus one sentence of why, then still do steps 4 and 6.

## 3. Scope each lesson before routing it
Ask this **first**, before choosing a store: is this true only in this project, or on this machine / about the user generally?

- **Machine-level or user-general** (shell behavior, tool quirks, the user's preferences, anything that would bite identically in any project) → one terse line in `~/.claude/CLAUDE.md`, in `## Machine gotchas` or the topically-correct existing section. Never a project store: a project store cannot be read from another project, which is how the same lesson gets learned six times.
  - `## Machine gotchas` is budgeted by **words, not lines: 350 total, 35 per line.** Run `python ~/.claude/skills/retro/health.py --store <this project's memory folder name>` and paste its output. At 280 or above, every addition is paired with an eviction or a trim of the least-recently-bitten line in the same diff.
  - Do not create `~/.claude/memory/`. The memory loader is project-scoped (`~/.claude/projects/<slug>/memory/`); a global memory dir is never read.
- **Project-only** → the store of the project whose files the session changed, not the store of the directory the session was launched from. When several projects were touched, the one where the lesson applies.

## 4. Recurrence check, run before writing anything
Grep every place a lesson can already live, including the places promoted lessons go:

```
grep -ril "<distinctive phrase>" ~/.claude/projects/*/memory/ ~/.claude/CLAUDE.md ~/.claude/rules/ <project>/CLAUDE.md
```

A hit anywhere means **do not write a second copy.** A hit in `~/.claude/CLAUDE.md` or `~/.claude/rules/` means the lesson was already promoted and still failed: say so, cite the path, and propose a deterministic mechanism (hook, script, or rule) in its place. A hit in a project store means recurrence N: cite both entries by path and propose the mechanism.

Then read `~/.claude/retro/findings.tsv`. Print its last-scan date; if older than 14 days, say the scan is stale. Every row with status `open` whose store is this project's memory folder or `global` must be resolved in this retro: `promote` to a mechanism, `rewrite` the lesson, `evict` it, or `defer` with a one-line reason. Set the row's status to `resolved:promote`, `resolved:rewrite`, `resolved:evict`, or `deferred:<reason>` and its resolved date to today. A finding is evidence for the step 2 trigger; a lesson that recurs in the findings file qualifies without a fresh correction this session. If the file is missing, print "no findings file; scan has never run" and continue.

## 5. Route what survived
- **Context gap** → the store chosen in step 3. For a project store, use what the project already has, preferring a typed `memory/` file (frontmatter, one fact, `**Why:**`/`**How to apply:**`, `[[links]]`, plus a one-line MEMORY.md pointer), else one line in `## Lessons Learned` in the project CLAUDE.md (respect any cap the project sets). Update an existing entry that covers the topic instead of adding a sibling.
  - A memory entry is **at most 120 words** and carries no commit hashes, dates, or incident narrative; that detail goes to the project's progress or archive doc. The MEMORY.md pointer is at most 120 characters.
- **Recurring procedure** → propose a skill under `.claude/skills/`.
- **Hard constraint (must ALWAYS/NEVER happen)** → propose a `.claude/rules/` file or a deterministic hook. Prefer the hook. A project-only fact phrased as a prohibition is a context gap, not a hard constraint; it goes to the store.
- **Voice/style lesson** → the project's own style file, if it has one, never the lesson store.
- **Session state, handoff notes, anything whose filename wants a date** → the project's handoff or progress doc, never the lesson store.
- **One-off** → discard, and say why.

**The retro proposes; it does not build.** A proposal for a script, hook, or rule shows the diff and states how it will be verified after approval. Do not run, iterate, or prototype it inside the retro, and never write a probe file into the project tree; "verify before done" applies to the build session that follows approval, not to the proposal. The one permitted probe is a read-only command that confirms the defect exists, run from the scratchpad.

## 6. Prune on printed evidence
Use the health.py output from step 3 for this store: entries and dated files. Paste the two numbers into the retro; "nothing to prune" without the numbers is not a valid statement.

The cap is **20 entries** and **zero dated filenames**. Over cap, evict in this order:
1. Dated session snapshots and handoff notes.
2. Entries about a different project that has its own store.
3. Entries already promoted to a rule, hook, or skill.
4. Entries contradicted by this session.
5. Redundant entries, merged into the better-written one.
6. Among equals, a lesson listed as `dormant` in the findings file goes first.

A retro must not leave the store larger than it found it unless a lesson earned the slot in step 2.

## 7. Apply, then present
Tier the changes by blast radius. Do not put both tiers behind one prompt.

**AUTO-APPLY, no approval needed**, then report as a done-list:
- Adding or editing a memory file in a project's `memory/` store, plus its MEMORY.md pointer.
- Deleting **at most 3** memory files per run. If the store is over cap by more than 3, delete the 3 clearest, list the rest as one batch proposal, and say a separate cleanup task is warranted.
- Updating the `status` and `resolved` columns of rows in `~/.claude/retro/findings.tsv`.
- Appending one line to the ledger `~/.claude/retro/retro-log.tsv`, always, even for an empty retro: `timestamp<TAB>store<TAB>proposed<TAB>auto-applied<TAB>deleted<TAB>empty(yes|no)<TAB>findings-resolved<TAB>findings-deferred`. `timestamp` is ISO date plus hour and minute; `store` is the memory folder name (for example `C--projects-newsletter`), or `global` when only `~/.claude/CLAUDE.md` was proposed. `empty` is yes when no new lesson was proposed or applied, regardless of findings resolved or entries pruned.

**STOP AND WAIT for the user's explicit approval**, never written unasked:
- Skills, `.claude/rules/` files, hooks, `settings.json`.
- Any CLAUDE.md, project or global, including a `## Lessons Learned` section serving as the store.

Present in this order, every time:
1. **Session review** (the step 1 bullets).
2. **Store check:** `N of 20 entries, D dated files` for the store, `W of 350 words` for Machine gotchas when a global line is proposed, and `Findings: N open, R resolved, D deferred, scan S days old`.
3. **Applied**: the done-list, one line each. A line that adds or edits a lesson quotes verbatim the user's correction it came from; findings updates and the ledger line do not. Omit if empty.
4. **Summary table** when there is more than one proposal: `# | Action | Target | Lesson`.
5. **Numbered proposals**, each as a unified diff. When a diff removes a repeated pattern, grep every target file first so the removal is complete. Under each diff:
   - **In plain terms:** 1-3 sentences for a reader who does not use git or a terminal: the moment this session where it went wrong, and what happens differently next time. Gloss any technical term kept.
   - **Why you might say no:** one honest sentence. Every proposal has one.
6. **Closing line.** One proposal: "approve, edit, or reject." Several: "approve by number, edit, or reject." Never offer approve-all. State that any auto-applied write can be undone by naming its number.

Whenever no new lesson qualified in step 2, write the sentence "Empty retro: nothing durable surfaced" with its reason, even if findings were resolved or entries pruned. An empty retro with nothing to prune is items 1, 2, that sentence, plus the ledger line. Stop there.
