# Grippy PR UX Redesign — Full PR Review API + Graph-Powered Resolution

**Date:** 2026-02-26
**Author:** Alpha (engine architect)
**Reviewer:** Bravo (implementation lead)
**Status:** Draft — pending Bravo review

## Problem

PR #6 dogfood exposed three interconnected pain points:

1. **Comment flood:** 5 review rounds = 5 separate 3-5KB markdown walls in the PR timeline, drowning actual conversation.
2. **No finding lifecycle:** Grippy doesn't track which findings were fixed. Re-raises similar issues, contradicts itself (cache key flip-flop across rounds 2-4).
3. **Missing actionability:** Findings are prose paragraphs in issue comments, not inline code annotations. No resolve threads, no diff-line context, no checkbox tracking.

## Design

### 1. Two-Layer Comment Architecture

Replace the current single issue comment with a two-layer system:

**Layer 1 — Summary Dashboard (issue comment)**
- One per PR, upserted on every push (keyed on `<!-- grippy-summary-{pr_number} -->`)
- Compact format: score, verdict, finding counts, delta from prior round
- Collapsible history section showing score progression across rounds
- Links to inline comments for each finding
- Off-diff findings (lines outside hunk) go here in a collapsible section

**Layer 2 — Inline Review Comments (PR Review API)**
- One per finding, placed on the exact file/line via `pr.create_review()`
- Posted as atomic batch with `event="COMMENT"`
- Each comment contains: severity badge, title, suggestion, finding ID, Grippy note
- Hidden marker with finding fingerprint for cross-round matching
- Capped at 25 comments per `create_review()` call (GitHub secondary rate limit)

**On subsequent pushes:**
- Resolved findings: inline threads auto-resolved via GraphQL `resolveReviewThread` (called via `gh api graphql`)
- Persisting findings: inline comment body edited with "PERSISTS (round N)" badge
- New findings: new inline review comments
- Summary comment: upserted with updated delta section

**Fallbacks:**
- 422 on inline comment (line not in hunk): finding moves to summary's off-diff section
- Fork PRs: fall back to issue-comment-only mode (GITHUB_TOKEN is read-only for forks)
- \>25 findings: split across multiple `create_review()` calls

### 2. Finding Lifecycle — Graph-Powered Resolution

**Finding Fingerprint:**
Each finding gets a deterministic fingerprint: `sha256(file + category + title_normalized)[:12]`. Stable across line number shifts. Embedded as HTML comment in each inline review comment.

**Resolution Algorithm (per push):**
```
1. Run new review → get new findings with fingerprints
2. Query GrippyStore for prior round's findings (same PR session)
3. For each prior finding fingerprint:
   a. Exact fingerprint match in new findings → PERSISTS
   b. No exact match → vector similarity search (embed title+description)
      - similarity > 0.85 → PERSISTS (finding evolved, line moved)
      - similarity < 0.85 → RESOLVED
4. New findings with no prior match → NEW
```

**Graph Extensions:**
- New edge types: `RESOLVES` (review → finding), `PERSISTS_AS` (finding → finding)
- New FINDING node properties: `status` (open/resolved/persists), `fingerprint`, `thread_id` (GitHub review thread ID for resolution)
- Session scoping: findings queried by `session_id=f"pr-{pr_number}"` via existing Agno SqliteDb persistence

**Downstream capabilities enabled:**
- Author tendency tracking: recurring finding patterns per author
- File hotspot detection: finding density per file over time
- Resolution rate metrics: % findings resolved within N pushes

### 3. GitHub API Integration Layer

New module: `src/grippy/github_review.py`

**Key functions:**

```python
def post_review(
    token: str, repo: str, pr_number: int,
    review: GrippyReview, *,
    prior_findings: list[dict], head_sha: str, diff: str,
) -> ReviewPostResult:
    """Post review as inline comments + summary dashboard."""

def resolve_findings(
    token: str, repo: str, pr_number: int,
    resolved: list[ResolvedFinding],
) -> int:
    """Auto-resolve inline threads for fixed findings via GraphQL."""

def parse_diff_lines(diff_text: str) -> dict[str, set[int]]:
    """Parse unified diff → {file: set of addressable RIGHT-side lines}."""
```

`post_review()` flow:
1. `parse_diff_lines(diff)` → addressable lines map
2. Classify findings: inline-eligible vs off-diff
3. Build `ReviewComment` dicts for eligible findings
4. `pr.create_review(event="COMMENT", comments=[...])` (batched at 25)
5. Upsert summary issue comment
6. Store thread IDs in graph for later resolution

`resolve_findings()` flow:
1. For each resolved finding, look up thread_id from graph
2. Call `gh api graphql -f query='mutation { resolveReviewThread(...) }'` via subprocess
3. Optionally edit inline comment body with RESOLVED badge

**Permissions:** Current workflow already has `pull-requests: write` + `contents: read`. No changes needed.

### 4. GrippyStore → Agno Knowledge Migration

**Current:** Raw `lancedb.connect()` + custom `make_embed_fn()` with manual HTTP auth logic.

**Target:** Agno's native `Knowledge` + `LanceDb` backend with built-in embedder.

```python
# Before
store = GrippyStore(graph_db_path=..., lance_dir=..., embed_fn=make_embed_fn(base_url, model))

# After
from agno.knowledge.embedder.openai import OpenAIEmbedder
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb, SearchType

embedder = create_embedder(transport, embedding_model, base_url)
store = GrippyStore(graph_db_path=..., lance_dir=..., embedder=embedder)
# Internally uses Knowledge(vector_db=LanceDb(embedder=embedder, search_type=SearchType.hybrid))
```

**Embedder factory** (`src/grippy/embedder.py`):
```python
def create_embedder(transport: str, model: str, base_url: str) -> OpenAIEmbedder:
    if transport == "openai":
        return OpenAIEmbedder(id=model)  # reads OPENAI_API_KEY from env
    return OpenAIEmbedder(id=model, base_url=base_url, api_key="lm-studio")
```

Replaces `make_embed_fn()` entirely. Drops manual `requests.post()`, host-checking, auth logic.

**GrippyStore changes:**
- Constructor takes `embedder` instead of `embed_fn`
- Internally wraps `Knowledge(vector_db=LanceDb(...))` for vector storage
- Keeps SQLite for edges + node_meta (Agno has no graph abstraction)
- New methods: `find_matching_findings()`, `get_prior_findings()`
- `search_nodes()` now uses Agno's hybrid search

### 5. Round-5 Polish (bundled)

**F1 — Strict embedding auth:**
With the Agno embedder migration, the manual auth logic disappears. `OpenAIEmbedder` handles auth natively. For non-OpenAI endpoints, we pass explicit `api_key`. No silent unauth fallback possible.

**F4 — Transport error UX:**
Wrap `create_reviewer()` in `try/except ValueError` in `main()`. On failure, post "CONFIG ERROR" issue comment with error message + valid transport values, then `sys.exit(1)`.

**F2 + F3 (workflow_dispatch runner + cache):** Deferred — cosmetic, doesn't affect UX redesign.

## File Changes

### New files
| File | Purpose |
|------|---------|
| `src/grippy/github_review.py` | PR Review API layer (post_review, resolve_findings, parse_diff_lines) |
| `src/grippy/embedder.py` | `create_embedder()` factory, replaces `make_embed_fn()` |
| `tests/test_grippy_github_review.py` | Tests for review posting, diff parsing, resolution |
| `tests/test_grippy_embedder.py` | Tests for embedder factory |

### Modified files
| File | Changes |
|------|---------|
| `src/grippy/review.py` | `main()` rewired: `post_review()` replaces `post_comment()`, `create_embedder()` replaces `make_embed_fn()`, transport error handling |
| `src/grippy/persistence.py` | `GrippyStore` → Agno `Knowledge` + `LanceDb`, new resolution methods |
| `src/grippy/graph.py` | `RESOLVES` + `PERSISTS_AS` edge types, `fingerprint` + `status` + `thread_id` on FINDING nodes |
| `src/grippy/schema.py` | `Finding.fingerprint` computed property |
| `src/grippy/__init__.py` | Updated exports |
| `tests/test_grippy_review.py` | Updated for new API |
| `tests/test_grippy_persistence.py` | Updated for Knowledge-based GrippyStore |
| `pyproject.toml` | Verify `agno[lancedb]` in grippy-persistence extras |

## Build Order

1. `create_embedder()` + tests (no dependencies)
2. `GrippyStore` Knowledge migration + resolution methods + tests
3. `github_review.py` (diff parser, post_review, resolve_findings) + tests
4. Wire into `main()` + transport error handling
5. Round-5 fixes (F1 strict auth solved by migration, F4 transport UX)
6. Update workflow if needed
7. Integration test on PR

## Ownership

- **Alpha:** Design doc, implementation plan, implementation
- **Bravo:** Design review (critique before implementation begins)
- **Nelson:** Final approval, secrets/infra if needed

## API References

- PyGithub `pr.create_review()`: atomic batch review with inline comments
- GitHub REST: `POST /repos/{owner}/{repo}/pulls/{number}/reviews` (event=COMMENT)
- GitHub GraphQL: `resolveReviewThread(input: {threadId})` via `gh api graphql`
- Agno `Knowledge(vector_db=LanceDb(..., search_type=SearchType.hybrid, embedder=OpenAIEmbedder(...)))`
- Agno `SqliteDb` for session persistence (already wired)
- Inline comments require lines within diff hunks (422 on out-of-hunk lines)
- Cap 25 comments per review to avoid secondary rate limits
