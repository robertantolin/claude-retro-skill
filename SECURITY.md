# Security policy

## What this skill touches

The skill runs locally inside Claude Code. It reads your session transcripts under `~/.claude/projects/`, sends your own messages (never tool output or file contents) to the model through your own `claude` login, and writes only under `~/.claude/retro/` plus the files you approve in a proposal. Nothing is sent anywhere else. The README's first paragraph describes exactly what leaves your machine.

## Supported versions

| Version | Supported |
|---|---|
| 4.x | Yes |
| 3.x and older | No, upgrade to 4.x |

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting form for this repository: **Security** tab, then **Report a vulnerability** (https://github.com/robertantolin/claude-retro-skill/security/advisories/new). Include the version, what the skill did, and how to reproduce it.

You will get an acknowledgement within seven days. A fix, or an explanation of why no fix is needed, follows as a patch release and an entry in the changelog.
