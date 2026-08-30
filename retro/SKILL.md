---
name: retro
description: End-of-session retrospective. Review the session honestly, keep only lessons that clear the bar (usually none), route each by scope, promote repeat lessons to hooks, prune to a budget, then auto-apply lesson-store writes and stop for anything larger. Run at the end of any working session.
---

Run a retrospective on THIS session. Be concise and honest; the loop must shrink as well as grow.

**Most sessions should produce zero lessons.** The store is a working set, not a journal.

## 1. Review the session

From the actual conversation: what was attempted, what failed or needed correction/rework from your human partner, what worked well. At most 3 bullets per category. Cite the specific mistakes and corrections, not generic observations or a rosy recap.

## 2. Decide whether anything is worth keeping

Bar: **would knowing this at the start of the session have changed what I actually did?** Not "is this true," not "is this interesting."

Keep 0-3 lessons. Zero is the expected result for a session that went normally, and "Empty retro: nothing durable surfaced" plus one sentence of why is a complete, valid retro. Justify each survivor in one sentence against the bar; if you cannot write that sentence, discard it.

## 3. Scope each lesson before routing it

Ask this **first**, before choosing a store: is this true only in this project, or on this machine and about your human partner generally?

- **Machine-level or person-level** (shell behavior, tool quirks, standing preferences, anything that would bite identically in any project) → one terse line in the user-level standing instruction file (`~/.claude/CLAUDE.md`), in a `## Machine gotchas` section or the topically correct existing section. Never a project store: a project store cannot be read from another project, which is how one machine-level lesson gets learned over and over in parallel silos.
  - Cap that section at about 10 lines. At cap, propose evicting the least-recently-bitten line in the same diff.
  - Do not invent a new global store directory. Persistent memory is usually scoped per project, so a global memory folder gets written but never read. Put person-level lessons where the tool reliably loads them.
- **Project-only** → the project's lesson store (step 5).

## 4. Recurrence check, run before writing anything

Grep the sibling stores for the lesson you are about to write:

```
grep -ril "<distinctive phrase>" ~/.claude/projects/*/memory/ <project>/CLAUDE.md
```

If a matching lesson already exists anywhere, **do not write a second entry.** A lesson recorded once and violated again is proof the instruction layer does not work for it. Propose a hook or a rule instead, cite both prior entries by path, and say plainly that this is recurrence N.

## 5. Route what survived

- **Context gap** (a fact/preference that would have changed the approach) → the lesson store chosen in step 3. For a project store, use what the project already has, in this order of preference: a typed entry in the project's persistent memory system if one exists (one fact per entry, with why it matters and how to apply it), or a one-line addition to `## Lessons Learned` in the project CLAUDE.md (respect any entry cap the project sets). Check for an existing entry that already covers it and UPDATE that instead of duplicating.
- **Recurring procedure** → propose creating/updating a skill under `.claude/skills/`.
- **Hard constraint (must ALWAYS/NEVER happen)** → propose a `.claude/rules/` file OR a deterministic hook. Prefer the hook: deterministic enforcement beats instructions.
- **Voice/style lesson** → route to the project's style loop if it has one (check the project CLAUDE.md for a style-learnings file or similar), never to the lesson store.
- **Session state, handoff notes, or anything whose filename wants a date in it** → NOT the lesson store. It belongs in the project's handoff or progress doc. If an entry only makes sense alongside "as of <date>," it is a journal entry and it will be stale before it is ever read.
- **One-off, not generalizable** → discard, and say why.

## 6. Prune to a budget

The lesson store is capped at **20 entries** per project. If it is over cap, you MUST propose enough deletions to get back under; this is not optional and not subject to "nothing looked stale."

Evict in this order:

1. Dated session snapshots and handoff notes (they violate step 5).
2. Entries about a different project that has its own store.
3. Entries already promoted to a rule, hook, or skill.
4. Entries contradicted by this session.
5. Redundant entries: merge into the better-written one.

A retro must not leave the store larger than it found it unless a lesson genuinely earned the slot.

## 7. Apply, then present

Tier the changes by blast radius. Do not put both tiers behind one prompt: that trains reflex approval and blunts the gate where it matters.

**AUTO-APPLY, no approval needed.** Write these, then report them as a done-list:

- Adding, editing, or deleting an entry in a project lesson store, plus its index pointer.

**STOP AND WAIT for explicit approval.** Never write these unasked:

- Skills, `.claude/rules/` files, hooks.
- Any CLAUDE.md, project or user-level, including a project's `## Lessons Learned`.

Present in this order, every time, so the output stays predictable:

1. **Session review** (the step 1 bullets).
2. **Applied**: the done-list of auto-applied store writes, one line each. Omit if empty.
3. **Summary table** of what needs approval, only when there is more than one proposal: `# | Action (add/edit/delete) | Target | Lesson (one line)`. A single proposal skips the table.
4. **Numbered proposals.** Each shows the change as a unified diff. When a proposal eliminates a repeated pattern (e.g., a hardcoded name or value across multiple files), grep every target file for that pattern before finalizing the diff: a proposal that only partially removes the pattern just relocates the bug, and gets approved as if it were fixed. Directly under each diff, add an **"In plain terms:"** block: 1-3 sentences for a reader who doesn't use git or a terminal, containing (a) the concrete moment this session where it went wrong, and (b) what will happen differently next time. Any technical term kept in the block gets a one-phrase gloss (e.g. "a pathspec, telling git exactly which files to include"). The plain-terms block is presentation only: stored lesson entries keep their store's terse one-line format.
5. **The reader's options, stated explicitly:** if there are proposals, approve all, approve by number (e.g. "1 and 3"), edit, or reject. Always state that any auto-applied write can be undone by naming its number.

If nothing cleared the bar in step 2 and nothing needed pruning, say "Empty retro: nothing durable surfaced" plus one sentence on why, and stop.
