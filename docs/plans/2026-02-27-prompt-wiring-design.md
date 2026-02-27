# Grippy Prompt Wiring Design

**Date:** 2026-02-27
**Author:** Alpha (session 16)
**Approved by:** Nelson

## Problem

Only 6 of 21 prompt files are wired into Grippy's review pipeline. 12 sit on the shelf. Grippy is "half-brain dead" — the schema expects personality fields (tone_register, ascii_art_key, catchphrases, disguise) and quality gates (confidence filter, escalation) but the LLM has no instructions for producing them.

## Decision

Wire 10 of 12 unwired prompts as LLM instructions. No post-processing code. The LLM self-filters, self-triages, and self-calibrates based on the instruction chain. Two files excluded: `sdk-easter-egg.md` (separate SDK project) and `README.md` (documentation only).

## Architecture: Shared Layer + Mode-Specific

### Composition order

```
IDENTITY (Agno description param)
  └─ CONSTITUTION.md + PERSONA.md

INSTRUCTIONS (Agno instructions param — list of strings)
  ├─ system-core.md              ← always first
  ├─ <mode-prompt>.md            ← mode-specific
  ├─ SHARED_PROMPTS:
  │   ├─ tone-calibration.md     ← score → tone register mapping
  │   ├─ confidence-filter.md    ← suppress low-confidence findings
  │   ├─ escalation.md           ← when to produce Escalation objects
  │   ├─ context-builder.md      ← how to triage context depth
  │   ├─ catchphrases.md         ← catalog for personality fields
  │   ├─ disguises.md            ← conditional activation (surprise_audit or "production ready")
  │   ├─ ascii-art.md            ← score-gated art selection
  │   └─ all-clear.md            ← zero-findings output behavior
  ├─ scoring-rubric.md           ← always second-to-last
  └─ output-schema.md            ← always last (anchors output format)
```

### 6 modes (4 existing + 2 new)

| Mode | Mode prompt | Status |
|------|------------|--------|
| `pr_review` | pr-review.md | Existing, default |
| `security_audit` | security-audit.md | Existing |
| `governance_check` | governance-check.md | Existing |
| `surprise_audit` | surprise-audit.md | Existing |
| `cli` | cli-mode.md | New (future transport) |
| `github_app` | github-app.md | New (future transport) |

### Code structure in prompts.py

```python
SHARED_PROMPTS = [
    "tone-calibration.md",
    "confidence-filter.md",
    "escalation.md",
    "context-builder.md",
    "catchphrases.md",
    "disguises.md",
    "ascii-art.md",
    "all-clear.md",
]

MODE_CHAINS = {
    "pr_review": ["system-core.md", "pr-review.md"],
    "security_audit": ["system-core.md", "security-audit.md"],
    "governance_check": ["system-core.md", "governance-check.md"],
    "surprise_audit": ["system-core.md", "surprise-audit.md"],
    "cli": ["system-core.md", "cli-mode.md"],
    "github_app": ["system-core.md", "github-app.md"],
}

CHAIN_SUFFIX = ["scoring-rubric.md", "output-schema.md"]
```

`load_instructions(mode)` composes: `MODE_CHAINS[mode] + SHARED_PROMPTS + CHAIN_SUFFIX`

## File classification

| File | Wiring | Rationale |
|------|--------|-----------|
| tone-calibration.md | SHARED_PROMPTS | Always-on. Maps score → tone register. |
| confidence-filter.md | SHARED_PROMPTS | LLM self-filters below threshold. |
| escalation.md | SHARED_PROMPTS | Instructs when to produce Escalation objects. |
| context-builder.md | SHARED_PROMPTS | How to triage context depth per complexity tier. |
| catchphrases.md | SHARED_PROMPTS | Catalog for opening_catchphrase, closing_line. |
| disguises.md | SHARED_PROMPTS | Conditional: activates on surprise_audit or "production ready". |
| ascii-art.md | SHARED_PROMPTS | Score-gated art selection for ascii_art_key. |
| all-clear.md | SHARED_PROMPTS | Zero-findings celebration output. |
| cli-mode.md | New mode "cli" | Output formatting for terminal transport. |
| github-app.md | New mode "github_app" | Output formatting for webhook transport. |
| sdk-easter-egg.md | **NOT WIRED** | Separate project (Navi SDK runtime). |
| README.md | **NOT WIRED** | Documentation index. |

## Files to modify

1. **`src/grippy/prompts.py`** — Add `SHARED_PROMPTS`, `CHAIN_SUFFIX`, refactor `MODE_CHAINS`, update `load_instructions()`
2. **`tests/test_grippy_prompts.py`** — Tests for new structure, modes, composition
3. **`tests/test_grippy_agent_evolution.py`** — Tests for new modes creating valid agents

## Files NOT modified

- `agent.py` — already calls `load_instructions(mode=mode)`, no changes needed
- `review.py` — passes `mode` from env, no changes needed
- `schema.py` — already has all needed fields (ToneRegister, AsciiArtKey, Escalation, etc.)

## Test coverage targets

- All `SHARED_PROMPTS` files exist in real `prompts_data/`
- All 6 modes produce valid instruction chains
- Chain composition: system-core always first, output-schema always last
- Shared prompts appear in every mode's instruction chain
- `load_instructions()` backward-compatible for existing 4 modes
- New modes "cli" and "github_app" work in `create_reviewer()`
- Chain length = len(MODE_CHAINS[mode]) + len(SHARED_PROMPTS) + len(CHAIN_SUFFIX)

## Future considerations

- **Post-processing:** If LLM self-filtering proves insufficient, add a `ConfidenceFilter` class in review.py that drops findings below threshold after LLM output. Not for v1.
- **Token budget:** 8 shared prompts add ~15-20K tokens. Monitor via `meta.tokens_used`. If problematic, consider summarizing reference data in prompt files.
- **State persistence:** Catchphrase rotation and disguise rotation need persistent state. Deferred to Actions cache work.
