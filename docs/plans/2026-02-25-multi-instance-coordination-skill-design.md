# Multi-Instance Coordination Skill — Design

Date: 2026-02-25
Status: Approved

## Overview

A Claude Code skill for coordinating multiple AI agent instances on a shared codebase. Lifecycle-first: guides users from the decision to split work through active coordination to convergence.

Designed for the Claude Code skills marketplace. Self-contained, zero-setup defaults, works out of the box.

## Identity

```yaml
name: multi-instance-coordination
description: Use when work exceeds one context window, needs different thinking modes
  (design vs build), or requires parallel instances on a shared codebase
```

## Audience

Anyone running 2+ AI agent instances (Claude Code, Claude Desktop, Gemini, Cursor, etc.) on the same project. The coordination protocol is agent-agnostic — any instance that can read and write files can participate.

## Principles (Non-Negotiable)

1. **Append-only coordination** — the comms artifact is never edited, only appended. Prevents edit conflicts, preserves the full decision trail.
2. **Boot prompts survive context death** — every instance can be reinitialized from a document without the human re-explaining. If the document doesn't exist, the knowledge doesn't transfer.
3. **Documents are the API between instances** — if it's not in a doc, it doesn't transfer. Conversation history is ephemeral; artifacts are durable.
4. **Git log is the progress report** — don't burn context documenting what commits already show.
5. **Persist before death** — if below 15% context, stop working and start persisting (handoff doc, memory update, exit message with task list).

## Lifecycle

### Phase 1: Assess

Decision tree — should this be multi-instance?

- Will the work exhaust one context window? (many files to read, long build sessions)
- Do different parts need different thinking modes? (design is divergent, building is convergent — fresh context helps)
- Can workstreams proceed independently with defined interfaces?
- Is there a human available to initialize the second instance?

If yes to any: proceed. If no to all: stay single-instance, consider `dispatching-parallel-agents` or `subagent-driven-development` instead.

### Phase 2: Assign Roles

Two validated patterns:

**Architect + Builder** — one instance designs and reviews, the other implements. The architect holds the big picture and validates against the design. The builder gets fresh context per task and focuses on implementation quality. Best for: projects where design coherence matters, greenfield features, complex refactors.

**Parallel Specialists** — both instances build, different workstreams. Requires clean boundaries (different files/directories, no shared mutable state). Best for: independent modules, pack/plugin development, tasks that touch non-overlapping code.

The skill recommends a role for each instance and has the human confirm.

#### Team Growth

The protocol is agent-agnostic. When onboarding a new team member (Claude Desktop, Gemini, a different model):

1. **Write a boot prompt** — same format as Phase 3, scoped to the new member's role and capabilities. Declare what they can access (files? terminal? web?), what they can't, and how they communicate.
2. **Add them to the thread convention** — new sender tag at the top of `.comms/thread.md`.
3. **Scope their access** — Claude Desktop reads files and browses the web but can't run commands. A Codespace agent builds but can't browse. The boot prompt declares capabilities so other instances know what to delegate.
4. **Start narrow** — one well-defined task, review their first contribution before expanding scope.

### Phase 3: Bootstrap Coordination

Auto-generated, zero manual setup. The skill creates:

**`AGENTS.md`** — the agent-agnostic project coordination file:
- Project overview (what, why, current state)
- Team roster (roles, capabilities, sender tags, which tool each runs in)
- Comms protocol (thread location, message format, conventions)
- Scope boundaries and conventions
- Current task assignments
- How to onboard a new team member

**`.comms/thread.md`** — append-only coordination artifact:
- Header: sender tags, conventions
- Messages: `[date] **sender**: message` between `---` delimiters
- Append only — never edit previous messages

**`docs/<role>-boot-prompt.md`** — per-instance reinitialization document:
- Role and identity
- Read order (which files to load first, in what sequence)
- Current state (what's done, what's in progress)
- Task list (what this instance should work on)
- Comms protocol reference

**Tool-specific files:** The skill updates `CLAUDE.md` to reference `AGENTS.md` but does not create or modify other tools' config files (`GEMINI.md`, `.cursorrules`, etc.). Each tool creates its own using its own conventions, reading `AGENTS.md` first.

The only manual step: the human hands the boot prompt to the second instance.

### Phase 4: Operate

Protocol during active work:

- **Post to comms thread** before and after significant work (not every small change — use judgment)
- **Dispatch tasks** via the comms thread, tagged with target instance
- **Git log is the progress report** — don't duplicate what commits show
- **Surface blockers** through the thread, not through human relay
- **Monitor context** — if below 15%, trigger exit protocol: write handoff message to thread, update memory files, list remaining tasks with status
- **Handoff docs before context death** — persist knowledge while you still have it, not after

### Phase 5: Converge

When work is complete or an instance hits context limits:

- **Context death recovery:** the surviving instance (or human) writes a boot prompt from the dead instance's last thread message + git log + memory files
- **Work integration:** review each instance's output, run full test suite, verify no conflicts between workstreams
- **Closeout:** final comms thread message summarizing what was built, update project memory, archive boot prompts (or leave as documentation)

## File Convention

| File | Purpose | Who reads it |
|------|---------|-------------|
| `AGENTS.md` | Agent-agnostic team coordination | Every agent, first thing |
| `CLAUDE.md` | Claude Code-specific commands and guidance | Claude Code only |
| `GEMINI.md` / `.cursorrules` / etc. | Tool-specific, each tool owns its own | Respective tool only |
| `.comms/thread.md` | Append-only coordination artifact | All team members |
| `docs/<role>-boot-prompt.md` | Per-instance reinitialization | Target instance on init |

`AGENTS.md` is the lingua franca. Each tool creates its own config file using its own conventions but reads `AGENTS.md` first.

## Relationship to Other Skills

| Skill | Scope | When to use instead |
|-------|-------|-------------------|
| `dispatching-parallel-agents` | Intra-session subagent parallelism | 2+ independent tasks, single session, no persistent coordination needed |
| `subagent-driven-development` | Intra-session sequential execution with review | Implementation plan with independent tasks, single session |
| `multi-instance-coordination` | Inter-session instance coordination | Work exceeds one context window, needs role separation, or parallel instances on shared codebase |

Complementary, not competing. This skill may recommend dropping into `subagent-driven-development` for tasks that don't need a separate instance.

## Origin

Validated during the navi-bootstrap build: two Claude Code instances (alpha/architect, bravo/builder) and a human (Nelson) coordinated through `.comms/thread.md`, survived multiple context deaths with zero knowledge loss, built a 7-module engine + 7 template packs + an Agno-based AI reviewer in a single day. The full coordination trail is preserved at `navi-bootstrap/.comms/thread.md`.
