# AGENTS.md Template

Use this template to create `AGENTS.md` in the project root. Fill in the bracketed sections. Remove this header and instructions before writing.

---

# AGENTS.md

Multi-agent coordination protocol for this project. Every agent reads this file first.

## Project

**Name:** [project name]
**Description:** [one-line description]
**Repository:** [repo path or URL]

## Team

| Sender Tag | Role | Tool | Capabilities | Scope |
|------------|------|------|-------------|-------|
| **[name]** | [role, e.g. architect] | [e.g. Claude Code] | [e.g. files, terminal, git] | [e.g. design docs, reviews] |
| **[name]** | [role, e.g. builder] | [e.g. Claude Code] | [e.g. files, terminal, git] | [e.g. src/, tests/] |
| **[name]** | [role, e.g. human] | — | all | final decisions |

## Communication

**Comms thread:** `.comms/thread.md`
**Format:** `[date] **sender**: message` between `---` delimiters
**Rule:** Append only. Never edit previous messages.

## Conventions

- [Commit style, e.g. conventional commits: feat:, fix:, chore:]
- [Quality checks to run before committing]
- [Scope boundaries — what each role can and cannot modify]
- [Branch strategy if applicable]

## Current State

**Done:**
- [completed items]

**In Progress:**
- [active work with owner]

**Next:**
- [upcoming tasks with assigned owner]

## Onboarding a New Agent

1. Read this file (`AGENTS.md`)
2. Read the comms thread (`.comms/thread.md`) from the last few messages
3. Read your boot prompt if one exists (`docs/<role>-boot-prompt.md`)
4. Post an introduction to the comms thread with your sender tag
5. Wait for a task assignment or pick up an unassigned task from the "Next" list
