# claude-retro-skill

A `/retro` skill for [Claude Code](https://claude.com/claude-code): an end-of-session retrospective the agent runs on itself, with a human approval gate on every change.

**In plain terms:** your AI assistant reviews its own work at the end of each session, suggests what it should learn, and you approve what sticks.

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
2. **Extracts at most 3 candidate lessons** and routes each to the one place it will actually change behavior (see the routing table below).
3. **Prunes.** It scans the existing lesson store for entries that are stale, redundant, contradicted by the current session, or already promoted into automation, and proposes deletions.
4. **Presents a diff and stops.** A diff is a line-by-line list of its proposed changes. Nothing is written until the human approves.

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

## The three constraints that make it work

**1. A hard cap, with receipts.** Three lessons per session, maximum, and each must trace to a specific mistake in the session. Zero lessons is a valid outcome. The cap forces triage; the receipts rule kills generic filler like "communicate more clearly."

**2. Lessons route to where they change behavior.** A saved lesson only matters if it fires at the right moment, so each one is classified:

| Lesson type | Where it goes |
|---|---|
| Context gap (a fact that would have changed the approach) | The project's lesson store (memory entry or a `## Lessons Learned` line in CLAUDE.md, the project's standing instruction file) |
| Recurring procedure | A skill under `.claude/skills/` (a reusable how-to the agent loads when needed) |
| Hard constraint (must ALWAYS / NEVER happen) | A deterministic hook (a small piece of code that runs automatically, so the rule can't be forgotten), preferred over a rules file: code that blocks the action beats an instruction asking nicely |
| Voice/style preference | The project's style loop, if it has one |
| One-off, not generalizable | Discarded, with the reason stated |

**3. The store must shrink as well as grow.** Every retro proposes deletions alongside additions. A capped store (about 15 entries per project works well) stays small enough that every entry still gets read and respected. Without pruning, saved lessons become the same noise that caused the issue this skill was created to address.

## The human gate

The agent never edits its own instructions, memory, skills, or hooks silently. It proposes every change as a unified diff, and each diff carries an **"In plain terms"** block: one to three sentences stating the concrete moment the session went wrong and what will happen differently next time, readable by any non-technical user.

You accept, reject, or edit. The skill improves your project; you stay the editor of how.

## Beyond Claude Code

The skill is a single prompt file with no code dependencies, and the four-step loop is model-agnostic: any agent that keeps standing instruction files can run it. Keep the structure (honest review, at most 3 routed lessons, pruning) and the approval gate, and swap the routing targets for your tool's equivalents: Cursor's rules files, AGENTS.md for the OpenAI Codex CLI, GEMINI.md for the Gemini CLI, or simply a pinned document you maintain by hand. Conventions move fast, so the durable rule is: lessons go wherever your agent reliably reads standing instructions, and automation goes wherever your tool can enforce a check without being asked.

## License

MIT, see [LICENSE](LICENSE).
