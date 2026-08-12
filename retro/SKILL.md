---
name: retro
description: End-of-session retrospective. Review the session honestly, extract at most 3 durable lessons, route each to the project's lesson store / skills / rules / hooks, prune stale entries, then present a diff and wait for approval. Run at the end of any working session.
---

Run a retrospective on THIS session. Be concise and honest; the loop must shrink as well as grow.

## 1. Review the session

From the actual conversation: what was attempted, what failed or needed correction/rework from your human partner, what worked well. At most 3 bullets per category. Cite the specific mistakes and corrections, not generic observations or a rosy recap.

## 2. Extract at most 3 candidate lessons

Classify and route each one:

- **Context gap** (a fact/preference that would have changed the approach) → propose an entry in the project's lesson store. Use the store the project already has, in this order of preference: a typed entry in the project's persistent memory system if one exists (one fact per entry, with why it matters and how to apply it), or a one-line addition to `## Lessons Learned` in the project CLAUDE.md (respect any entry cap the project sets). Check for an existing entry that already covers it and UPDATE that instead of duplicating.
- **Recurring procedure** → propose creating/updating a skill under `.claude/skills/`.
- **Hard constraint (must ALWAYS/NEVER happen)** → propose a `.claude/rules/` file OR a deterministic hook. Prefer the hook: deterministic enforcement beats instructions.
- **Voice/style lesson** → route to the project's style loop if it has one (check the project CLAUDE.md for a style-learnings file or similar), never to the lesson store.
- **One-off, not generalizable** → discard, and say why.

## 3. Prune

Scan the project's lesson store for entries that are stale, redundant, contradicted by this session, or already promoted to a rule/hook/skill. Propose deletions/edits. Do not let the store only grow.

## 4. Present the retro and STOP

Present in this order, every time, so the output stays predictable:

1. **Session review** (the step 1 bullets).
2. **Summary table**, only when there is more than one proposal: `# | Action (add/edit/delete) | Target | Lesson (one line)`. A single proposal skips the table.
3. **Numbered proposals.** Each shows the change as a unified diff. Directly under each diff, add an **"In plain terms:"** block: 1-3 sentences for a reader who doesn't use git or a terminal, containing (a) the concrete moment this session where it went wrong, and (b) what will happen differently next time. Any technical term kept in the block gets a one-phrase gloss (e.g. "a pathspec, telling git exactly which files to include"). The plain-terms block is presentation only: stored lesson entries keep their store's terse one-line format.
4. **The reader's options, stated explicitly:** approve all, approve by number (e.g. "1 and 3"), edit, or reject.

WAIT for your human partner's explicit approval before writing anything; never silently edit CLAUDE.md, memory, skills, rules, or hooks. If nothing worth keeping surfaced, present it as "Empty retro: nothing durable surfaced" plus one sentence on why; an empty retro is a valid outcome.
