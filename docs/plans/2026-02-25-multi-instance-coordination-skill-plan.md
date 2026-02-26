# Multi-Instance Coordination Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a marketplace-ready Claude Code skill for coordinating multiple AI agent instances on a shared codebase.

**Architecture:** Single SKILL.md with bundled template files for auto-generated coordination artifacts (AGENTS.md, comms thread, boot prompt). Lifecycle-first structure following superpowers plugin conventions.

**Tech Stack:** Markdown skill files, YAML frontmatter, dot diagrams for decision flows.

**Design doc:** `docs/plans/2026-02-25-multi-instance-coordination-skill-design.md`

---

### Task 1: Create skill directory structure

**Files:**
- Create: `skills/multi-instance-coordination/SKILL.md` (empty placeholder)
- Create: `skills/multi-instance-coordination/templates/agents-md.md`
- Create: `skills/multi-instance-coordination/templates/comms-thread.md`
- Create: `skills/multi-instance-coordination/templates/boot-prompt.md`

**Step 1: Create directories**

Run: `mkdir -p skills/multi-instance-coordination/templates`

**Step 2: Verify structure**

Run: `find skills/ -type f`
Expected: Four paths listed

---

### Task 2: Write SKILL.md — frontmatter and overview

**Files:**
- Create: `skills/multi-instance-coordination/SKILL.md`

**Step 1: Write the frontmatter and overview section**

```markdown
---
name: multi-instance-coordination
description: Use when work exceeds one context window, needs different thinking modes
  (design vs build), or requires parallel instances on a shared codebase. Use this
  skill whenever you need to coordinate with another Claude Code instance, split work
  across multiple sessions, recover from context death mid-project, or onboard a new
  agent (Claude Desktop, Gemini, Cursor) into an existing multi-agent workflow.
---

# Multi-Instance Coordination

Coordinate multiple AI agent instances on a shared codebase through
durable artifacts — not shared memory, not conversation history.

**Core insight:** Conversation history is ephemeral. Documents survive context
death. Build coordination on documents, and instances become replaceable.
```

**Step 2: Verify frontmatter parses**

Read back the file, confirm `name` and `description` are present in YAML frontmatter.

---

### Task 3: Write SKILL.md — Phase 1 (Assess) and Phase 2 (Assign Roles)

**Files:**
- Modify: `skills/multi-instance-coordination/SKILL.md`

**Step 1: Add Phase 1 — Assess**

The decision tree as a dot diagram. Conditions for going multi-instance vs staying single. Clear pointers to `dispatching-parallel-agents` and `subagent-driven-development` for intra-session work.

**Step 2: Add Phase 2 — Assign Roles**

Two patterns: Architect+Builder and Parallel Specialists. When to use each. Role recommendation logic. Team growth protocol for onboarding non-Claude-Code agents.

**Step 3: Read back and verify**

Confirm dot diagrams render, patterns are distinct, team growth section covers agent-agnostic onboarding.

---

### Task 4: Write SKILL.md — Phase 3 (Bootstrap)

**Files:**
- Modify: `skills/multi-instance-coordination/SKILL.md`

**Step 1: Add Phase 3 — Bootstrap Coordination**

Auto-generation instructions: the skill creates `AGENTS.md`, `.comms/thread.md`, and `docs/<role>-boot-prompt.md` from bundled templates. Zero manual setup. Reference the templates in `./templates/`.

**Step 2: Add the AGENTS.md convention**

Explain the split: `AGENTS.md` is the lingua franca (every agent reads it). Tool-specific files (`CLAUDE.md`, `GEMINI.md`, `.cursorrules`) are owned by their respective tools and reference `AGENTS.md`.

**Step 3: Read back and verify**

Confirm the bootstrap creates all three artifacts, templates are referenced correctly.

---

### Task 5: Write SKILL.md — Phase 4 (Operate) and Phase 5 (Converge)

**Files:**
- Modify: `skills/multi-instance-coordination/SKILL.md`

**Step 1: Add Phase 4 — Operate**

The protocol during active work: posting conventions, task dispatch, context monitoring, the 15% rule, persist-before-death.

**Step 2: Add Phase 5 — Converge**

Context death recovery, work integration, closeout. Boot prompt generation for reinitialization.

**Step 3: Add principles section**

The five non-negotiable principles from the design doc, presented as the "why" behind each phase.

**Step 4: Read back and verify**

Full skill reads coherently from Phase 1 through Phase 5. Under 500 lines (skill-creator guidance).

---

### Task 6: Write template files

**Files:**
- Create: `skills/multi-instance-coordination/templates/agents-md.md`
- Create: `skills/multi-instance-coordination/templates/comms-thread.md`
- Create: `skills/multi-instance-coordination/templates/boot-prompt.md`

**Step 1: Write AGENTS.md template**

Fillable template with sections: Project Overview, Team Roster, Comms Protocol, Scope Boundaries, Current Assignments, Onboarding.

**Step 2: Write comms thread template**

Header with sender tag convention, message format between `---` delimiters, append-only rule.

**Step 3: Write boot prompt template**

Fillable template: Role, Read Order, Current State, Task List, Comms Protocol Reference.

**Step 4: Verify all three templates are self-explanatory**

Read each template. A new instance receiving it should understand the format without external explanation.

---

### Task 7: Final review and commit

**Step 1: Read full SKILL.md end to end**

Verify: under 500 lines, follows superpowers conventions, dot diagrams present, no references to navi-bootstrap-specific details (must be generic).

**Step 2: Verify template references**

All `./templates/` references in SKILL.md point to files that exist.

**Step 3: Commit**

```bash
git add skills/
git commit -m "feat: add multi-instance-coordination skill"
```
