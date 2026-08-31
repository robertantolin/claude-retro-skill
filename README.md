# claude-retro-skill

A `/retro` skill for [Claude Code](https://claude.com/claude-code): an end-of-session retrospective the agent runs on itself, with a human approval gate on anything that changes how the agent behaves.

**In plain terms:** your AI assistant reviews its own work at the end of each session, suggests what it should learn, and you approve anything that would change how it works.

## Install

Two ways to install: run the commands yourself, or paste the prompt below and Claude does it for you.

Copy the `retro` folder into your Claude Code skills directory:

```bash
git clone https://github.com/robertantolin/claude-retro-skill.git
cp -r claude-retro-skill/retro ~/.claude/skills/retro
```

Use `~/.claude/skills/` to make it available in every project, or a project's `.claude/skills/` to scope it to that project.

**Or ask Claude Code to install it.** Paste this into a session and the agent handles the paths and platform differences:

```
Clone https://github.com/robertantolin/claude-retro-skill and copy its retro/
folder verbatim into my user-level Claude Code skills directory
(~/.claude/skills/retro on Mac/Linux, %USERPROFILE%\.claude\skills\retro on
Windows). Do not modify SKILL.md. Confirm the file exists, then tell me how
to invoke the skill.
```

Either way, end any working session with:

```
/retro
```

## What /retro does

1. **Reviews the session honestly.** What was attempted, what failed or needed correction, what worked. It must cite the specific mistakes from the actual conversation, not produce a rosy recap.
2. **Keeps only what clears the bar.** The test is "would knowing this at the start of the session have changed what I actually did?" Zero lessons is the expected result for a session that went normally.
3. **Scopes each lesson before storing it.** A lesson about your machine or your standing preferences goes in your user-level instruction file, where every project can read it. Only project-specific lessons go in a project store.
4. **Checks for recurrence.** Before writing, it greps the other stores. If the lesson is already written down somewhere, writing it again is pointless: the instruction layer already failed, so it proposes a hook instead.
5. **Prunes to a budget.** The store is capped. Over cap, the agent must propose deletions to get back under, in a fixed eviction order.
6. **Applies the cheap changes and stops for the rest.** Lesson-store entries are written and reported. Skills, rules, hooks, and any instruction file wait for your approval as a diff. A diff is a line-by-line list of proposed changes.

## Example output

In the diffs below, lines starting with `+` are what the agent proposes to add and lines starting with `-` are what it proposes to delete. You approve or reject.

A typical proposed addition:

```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ ## Lessons Learned
+- Never pass multi-line text (commit messages, JSON payloads) inline to a
+  shell command; the shell re-parses quotes and backslashes. Write it to a
+  file and pass the file (git commit -F msg.txt).
```

**In plain terms:** today's commit message contained quote marks, and the shell split it into bogus file paths, so the commit failed twice before we caught it. Next time the message gets written to a file first and handed to git as a file, which skips the re-parsing entirely.

And a typical proposed deletion:

```diff
--- a/CLAUDE.md
+++ b/CLAUDE.md
@@ ## Lessons Learned
-- Run the content linter manually before finishing website edits.
```

**In plain terms:** this reminder was promoted to a hook last month (the linter now runs automatically after every edit), so the written lesson is dead weight and comes out.

## The problem

Large language models and AI agents make mistakes. They hallucinate, miss project context or instructions, and deliver diminishing returns as context rot and bloat set in.

Saving every lesson into project memory or instruction files doesn't solve the problem. As the file system grows, so does token consumption, and stale context degrades model performance as much as the original mistakes did. This skill treats the lesson store as something to curate, not just append to: a human-in-the-loop mechanism that turns the way you actually work into rules, skills, and automations.

## The five constraints that make it work

**1. A hard cap, with receipts, and zero as the default.** Three lessons per session, maximum, and each must trace to a specific mistake in the session and clear an explicit bar: would knowing this yesterday have changed what the agent did? The cap forces triage; the receipts rule kills generic filler like "communicate more clearly"; the bar is what makes "no lessons this time" a normal outcome instead of an awkward one. A cap on its own tends to get read as a quota.

**2. Scope is decided before storage.** Most agent memory is scoped per project, so a lesson about your shell, your tooling, or your preferences gets filed where only one project can see it, and every other project rediscovers it the hard way. The skill asks whether a lesson is project-level or person-level first, and sends person-level lessons to the user-level instruction file that loads everywhere.

**3. A repeated lesson becomes automation, not a second note.** If the same lesson is already written down somewhere, writing it again has already been proven not to work. The skill greps sibling stores before writing and, on a match, proposes a deterministic hook and cites the earlier entries. Repetition is the signal that instructions are the wrong tool.

**4. Lessons route to where they change behavior.** A saved lesson only matters if it fires at the right moment, so each one is classified:

| Lesson type | Where it goes |
|---|---|
| Machine-level or person-level fact (shell quirks, standing preferences) | The user-level instruction file, so every project reads it |
| Project-specific context gap | That project's lesson store (memory entry or a `## Lessons Learned` line in CLAUDE.md, the project's standing instruction file) |
| Recurring procedure | A skill under `.claude/skills/` (a reusable how-to the agent loads when needed) |
| Hard constraint (must ALWAYS / NEVER happen) | A deterministic hook (a small piece of code that runs automatically, so the rule can't be forgotten), preferred over a rules file: code that blocks the action beats an instruction asking nicely |
| Voice/style preference | The project's style loop, if it has one |
| Session state, handoff notes, anything dated | The project's handoff or progress doc, never the lesson store |
| One-off, not generalizable | Discarded, with the reason stated |

**5. The store must shrink as well as grow.** Every retro proposes deletions alongside additions, and pruning is a budget rather than a judgment call: about 20 entries per project, with a fixed eviction order that takes dated session snapshots first. A capped store stays small enough that every entry still gets read and respected. Without pruning, saved lessons become the same noise that caused the issue this skill was created to address.

## The human gate

The agent never edits its own instructions, skills, or hooks silently. Those are proposed as a unified diff and wait for you.

The gate is tiered on purpose. Adding or deleting an entry in a project lesson store is cheap and reversible, so the agent does it and reports it in a done-list you can undo by number. Skills, rules, hooks, and instruction files change how the agent behaves everywhere, so those always stop and wait.

That split exists because an approval prompt on every trivial write trains you to approve on reflex, which is exactly when the gate stops protecting the changes that matter. Every proposal still carries an **"In plain terms"** block: one to three sentences stating the concrete moment the session went wrong and what will happen differently next time, readable by any non-technical user.

You accept, reject, or edit. The skill improves your project; you stay the editor of how.

## Beyond Claude Code

The skill is a single prompt file with no code dependencies, and the loop is model-agnostic: any agent that keeps standing instruction files can run it. Keep the structure (honest review, a bar that permits zero lessons, scope before storage, recurrence into automation, routed lessons, budgeted pruning) and the tiered gate, then swap the routing targets for your tool's equivalents: Cursor's rules files, AGENTS.md for the OpenAI Codex CLI, GEMINI.md for the Gemini CLI, or simply a pinned document you maintain by hand. Conventions move fast, so the durable rule is: lessons go wherever your agent reliably reads standing instructions, and automation goes wherever your tool can enforce a check without being asked.

## License

MIT, see [LICENSE](LICENSE).
