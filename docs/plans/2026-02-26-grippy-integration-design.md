# Grippy Integration Design — Phase 1 → CI Pipeline

**Date:** 2026-02-26
**Status:** Approved
**Authors:** Alpha (architect), Nelson (owner)
**Scope:** Wire Grippy Phase 1 modules into CI pipeline, fix remaining audit items, dogfood on navi-bootstrap PRs

## Context

Grippy's Phase 1 modules (graph.py, retry.py, persistence.py, agent.py evolution) are built and tested (74 tests, Bravo). The CI entry point (review.py, action.yml, workflow) is built and tested (26 tests, Alpha). The pieces exist but aren't connected — `review.py main()` still calls the old `create_reviewer()` API without persistence, retry, or graph features.

**Goal:** Assemble the full pipeline so every PR review builds the knowledge graph from day one.

## Architecture: Current vs. Target

### Current flow (review.py main)

```
load_pr_event() → fetch_pr_diff() → truncate_diff()
  → create_reviewer(model_id, base_url, mode)
  → agent.run(message)
  → parse_review_response(content)
  → format_review_comment(review) → post_comment()
```

### Target flow

```
load_pr_event() → fetch_pr_diff() → truncate_diff()
  → create_reviewer(model_id, base_url, mode, db_path, session_id)
  → run_review(agent, message)          # retry + validation (replaces agent.run + parse_review_response)
  → review_to_graph(review)             # transform to typed nodes + edges
  → GrippyStore.store_review(graph)     # persist to SQLite + LanceDB
  → format_review_comment(review) → post_comment()
```

Key change: `run_review()` replaces both `agent.run()` and `parse_review_response()`. It returns a validated `GrippyReview` directly. `ReviewParseError` replaces the current `ValueError` catch.

## New Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GRIPPY_EMBEDDING_MODEL` | `text-embedding-qwen3-embedding-4b` | Model name for `/v1/embeddings` endpoint |
| `GRIPPY_DATA_DIR` | `./grippy-data` | Persistent directory for graph DB + LanceDB |
| `GRIPPY_TIMEOUT` | `300` | Seconds before review is killed |

## Embedding Function

GrippyStore requires an `embed_fn: Callable[[str], list[float]]`. For LM Studio:

```python
def make_embed_fn(base_url: str, model: str) -> EmbedFn:
    """Create embedding function that calls LM Studio /v1/embeddings."""
    import requests
    def embed(text: str) -> list[float]:
        resp = requests.post(
            f"{base_url}/embeddings",
            json={"model": model, "input": text},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    return embed
```

Bravo creates this as part of the wiring task.

## Persistence in CI

Self-hosted runners persist between runs. Data lives at `$GRIPPY_DATA_DIR/`:
- `grippy-session.db` — Agno session store (review continuity per PR)
- `grippy-graph.db` — SQLite edge junction table
- `lance/` — LanceDB vector store (node embeddings for semantic search)

For external repos using `grippy-action`, data defaults to workspace-relative (ephemeral per run). Persistent storage requires the user to configure `data-dir` input.

## Audit Fixes (M1-M3)

### M1: Agent timeout

Wrap `run_review()` in a signal-based timeout (SIGALRM on Linux). Configurable via `GRIPPY_TIMEOUT` env var. On timeout: post failure comment, exit 1.

### M2: Fork diff fetch

The raw diff API (`application/vnd.github.v3.diff`) works for fork PRs. Add explicit test coverage. Handle 403 (token lacks fork access) with a friendly error message instead of traceback.

### M3: main() integration tests

Mock-based tests of the full `main()` orchestration:
1. Happy path: mock event + mock diff + mock agent → comment posted, graph stored
2. Agent failure: mock agent raises → failure comment posted
3. Parse failure: mock agent returns garbage → parse error comment posted
4. Merge-blocking: mock agent returns FAIL verdict → exit code 1

## Work Breakdown

| # | Task | Owner | Depends on | New tests |
|---|------|-------|------------|-----------|
| W1 | Wire `run_review()` + `review_to_graph()` + `GrippyStore` into `main()` | Bravo | — | Update existing |
| W2 | Create `embed_fn` helper (LM Studio `/v1/embeddings`) | Bravo | W1 | +3 |
| W3 | Add env vars: `GRIPPY_EMBEDDING_MODEL`, `GRIPPY_DATA_DIR`, `GRIPPY_TIMEOUT` | Bravo | W1 | — |
| W4 | Update `grippy-review.yml` + `action.yml` with new env vars | Alpha | W3 | — |
| W5 | M1: Timeout wrapper for `run_review()` | Alpha | W1 | +2 |
| W6 | M2: Fork diff fetch graceful 403 handling | Alpha | — | +2 |
| W7 | M3: `main()` integration tests (mock-based) | Alpha | W1 | +4 |
| W8 | Code review Bravo's wiring | Alpha | W1 | — |
| W9 | Configure secrets + persistent data dir on runner | Nelson | W4 | — |
| W10 | Dogfood: open test PR, verify end-to-end | All | W1-W9 | Manual |

**Build order:** W1-W3 (Bravo) + W6 (Alpha, parallel) → W4-W5, W7-W8 (Alpha) → W9 (Nelson) → W10 (all)

## Dogfood Test Plan

1. Create test branch with a small deliberate change
2. Open PR → triggers `grippy-review.yml`
3. Verify: Grippy posts review comment with score, findings, personality
4. Verify: Graph DB and LanceDB populated on runner
5. Push follow-up commit → verify comment is **upserted** (not duplicated)
6. Close/merge → verify final state

**Failure modes to watch:**
- LM Studio timeout → M1 handles
- Devstral returns invalid JSON → retry.py handles
- Embedding model returns wrong dimension → need dim config
- Runner can't reach LM Studio over Tailscale → infra, not code

## Success Criteria

- [ ] `review.py main()` uses `run_review()` instead of `agent.run()`
- [ ] Every PR review persists a `ReviewGraph` to SQLite + LanceDB
- [ ] Timeout prevents hung CI jobs
- [ ] Fork PRs get friendly error instead of traceback on 403
- [ ] main() has mock-based integration tests for happy path + 3 failure modes
- [ ] Successful dogfood run on a real navi-bootstrap PR
- [ ] ~461 tests total (450 + ~11 new), all green
