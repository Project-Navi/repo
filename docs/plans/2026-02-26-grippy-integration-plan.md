# Grippy Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire Grippy Phase 1 modules (run_review, review_to_graph, GrippyStore) into the CI pipeline so every PR review builds the knowledge graph from day one.

**Architecture:** `review.py main()` replaces `agent.run()` + `parse_review_response()` with `run_review()` (retry + validation), then pipes the result through `review_to_graph()` → `GrippyStore.store_review()`. New env vars control embedding model, data directory, and timeout.

**Tech Stack:** Python 3.12, Agno, Pydantic, LanceDB, SQLite, PyGithub, GitHub Actions

**Design doc:** `docs/plans/2026-02-26-grippy-integration-design.md`

---

## Ownership

- **Bravo:** Tasks 1-3 (wiring, embed_fn, env vars)
- **Alpha:** Tasks 4-8 (workflow update, timeout, fork handling, integration tests, code review)
- **Nelson:** Task 9 (runner secrets + data dir)
- **All:** Task 10 (dogfood)

---

## Task 1: Wire `run_review()` + `review_to_graph()` + `GrippyStore` into main() [Bravo]

**Files:**
- Modify: `src/grippy/review.py:240-368` (main function)

**Context:**
- `run_review(agent, message)` returns `GrippyReview` directly (from `grippy.retry`)
- `review_to_graph(review)` returns `ReviewGraph` (from `grippy.graph`)
- `GrippyStore(graph_db_path, lance_dir, embed_fn, embed_dim)` — constructor
- `GrippyStore.store_review(graph)` — persists ReviewGraph
- `EmbedFn = Callable[[list[str]], list[list[float]]]` — batch embedding function
- `ReviewParseError` replaces `ValueError` in error handling

**Step 1: Write failing test for new main() flow**

Add to `tests/test_grippy_review.py`:

```python
class TestMainIntegrationNewAPI:
    """Tests that main() uses run_review instead of agent.run."""

    @patch("grippy.review.post_comment")
    @patch("grippy.review.fetch_pr_diff")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    def test_main_calls_run_review_not_agent_run(
        self, mock_create, mock_run_review, mock_to_graph, mock_store_cls,
        mock_fetch, mock_post, tmp_path, monkeypatch,
    ):
        """main() should call run_review(agent, message), not agent.run(message)."""
        # Setup: event file
        event = {
            "pull_request": {
                "number": 1, "title": "test", "user": {"login": "dev"},
                "head": {"ref": "feat"}, "base": {"ref": "main"}, "body": "",
            },
            "repository": {"full_name": "org/repo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        # Mock returns
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        review = _make_review()
        mock_run_review.return_value = review
        mock_to_graph.return_value = MagicMock()  # ReviewGraph
        mock_store_cls.return_value = MagicMock()  # GrippyStore instance

        # Env
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))

        from grippy.review import main
        main()

        # Verify: run_review was called, not agent.run
        mock_run_review.assert_called_once()
        mock_create.return_value.run.assert_not_called()  # old API not used
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_review.py::TestMainIntegrationNewAPI -v`
Expected: FAIL — main() still calls agent.run()

**Step 3: Update main() to use new API**

In `src/grippy/review.py`, update `main()`:

1. Add new env var reads after existing ones:
   ```python
   data_dir_str = os.environ.get("GRIPPY_DATA_DIR", "./grippy-data")
   embedding_model = os.environ.get("GRIPPY_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-4b")
   timeout_str = os.environ.get("GRIPPY_TIMEOUT", "300")
   ```

2. Create data dir:
   ```python
   data_dir = Path(data_dir_str)
   data_dir.mkdir(parents=True, exist_ok=True)
   ```

3. Add embed_fn import and creation (see Task 2 for the actual function):
   ```python
   from grippy.review import make_embed_fn
   embed_fn = make_embed_fn(base_url, embedding_model)
   ```

4. Update create_reviewer call:
   ```python
   agent = create_reviewer(
       model_id=model_id,
       base_url=base_url,
       mode=mode,
       db_path=data_dir / "grippy-session.db",
       session_id=f"pr-{pr_event['pr_number']}",
   )
   ```

5. Replace the `agent.run()` + `parse_review_response()` blocks (lines 306-341) with:
   ```python
   from grippy.retry import ReviewParseError, run_review
   from grippy.graph import review_to_graph
   from grippy.persistence import GrippyStore

   print(f"Running review (model={model_id}, endpoint={base_url})...")
   try:
       review = run_review(agent, user_message)
   except ReviewParseError as exc:
       print(f"::error::Grippy review failed after {exc.attempts} attempts: {exc}")
       raw_preview = exc.last_raw[:500]
       try:
           failure_body = (
               f"## ❌ Grippy Review — PARSE ERROR\n\n"
               f"Failed after {exc.attempts} attempts.\n\n"
               f"```\n{raw_preview}\n```\n\n"
               f"{COMMENT_MARKER}"
           )
           post_comment(token, pr_event["repo"], pr_event["pr_number"], failure_body)
       except Exception:
           pass
       sys.exit(1)
   except Exception as exc:
       print(f"::error::Grippy agent failed: {exc}")
       try:
           failure_body = (
               f"## ❌ Grippy Review — ERROR\n\n"
               f"Review agent failed: `{exc}`\n\n"
               f"Model: {model_id} at {base_url}\n\n"
               f"{COMMENT_MARKER}"
           )
           post_comment(token, pr_event["repo"], pr_event["pr_number"], failure_body)
       except Exception:
           pass
       sys.exit(1)
   ```

6. After the review score print, add graph + persistence:
   ```python
   # 5. Build graph and persist
   print("Persisting review graph...")
   try:
       graph = review_to_graph(review)
       store = GrippyStore(
           graph_db_path=data_dir / "grippy-graph.db",
           lance_dir=data_dir / "lance",
           embed_fn=embed_fn,
           embed_dim=embed_dim,
       )
       store.store_review(graph)
       print(f"  Graph: {len(graph.nodes)} nodes persisted")
   except Exception as exc:
       # Persistence failure is non-fatal — review still gets posted
       print(f"::warning::Graph persistence failed: {exc}")
   ```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_review.py::TestMainIntegrationNewAPI -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All 450+ tests pass

**Step 6: Commit**

```bash
git add src/grippy/review.py tests/test_grippy_review.py
git commit -m "feat: wire run_review + review_to_graph + GrippyStore into CI pipeline"
```

---

## Task 2: Create embed_fn helper [Bravo]

**Files:**
- Modify: `src/grippy/review.py` (add `make_embed_fn` function)
- Test: `tests/test_grippy_review.py` (add embed_fn tests)

**Context:**
- `EmbedFn = Callable[[list[str]], list[list[float]]]` — takes list of strings, returns list of vectors
- LM Studio serves OpenAI-compatible `/v1/embeddings` at the same base URL
- `requests` is already a lazy import in review.py (used by fetch_pr_diff)

**Step 1: Write failing test**

```python
class TestMakeEmbedFn:
    @patch("requests.post")
    def test_calls_embeddings_endpoint(self, mock_post):
        """embed_fn hits /v1/embeddings with correct model and input."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn
        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        result = fn(["hello world"])

        assert result == [[0.1, 0.2, 0.3]]
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert call_json["model"] == "test-model"
        assert call_json["input"] == ["hello world"]

    @patch("requests.post")
    def test_batch_embedding(self, mock_post):
        """embed_fn handles multiple texts in one call."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn
        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        result = fn(["text1", "text2"])

        assert len(result) == 2

    @patch("requests.post")
    def test_http_error_propagates(self, mock_post):
        """HTTP errors from embedding endpoint propagate."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn
        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        with pytest.raises(Exception, match="503"):
            fn(["hello"])
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_review.py::TestMakeEmbedFn -v`
Expected: FAIL — make_embed_fn doesn't exist

**Step 3: Implement make_embed_fn**

Add to `src/grippy/review.py` (after the `truncate_diff` function, before `format_review_comment`):

```python
def make_embed_fn(base_url: str, model: str) -> Callable[[list[str]], list[list[float]]]:
    """Create batch embedding function that calls LM Studio /v1/embeddings.

    Args:
        base_url: OpenAI-compatible API base URL (e.g. http://localhost:1234/v1).
        model: Embedding model name (e.g. text-embedding-qwen3-embedding-4b).

    Returns:
        Callable that takes list[str] and returns list[list[float]].
    """
    import requests  # type: ignore[import-untyped]

    def embed(texts: list[str]) -> list[list[float]]:
        url = f"{base_url}/embeddings"
        response = requests.post(
            url,
            json={"model": model, "input": texts},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in data]

    return embed
```

Also add to the imports at top of file: `from typing import Any, Callable`

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_review.py::TestMakeEmbedFn -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/grippy/review.py tests/test_grippy_review.py
git commit -m "feat: add make_embed_fn for LM Studio /v1/embeddings"
```

---

## Task 3: Add new environment variables [Bravo]

**Files:**
- Modify: `src/grippy/review.py:240-260` (env var reading section)
- Modify: `.dev.vars.example` (document new vars)

**Step 1: Add env vars to main()**

Already covered in Task 1 step 3. Verify that `GRIPPY_DATA_DIR`, `GRIPPY_EMBEDDING_MODEL`, and `GRIPPY_TIMEOUT` are read in main() and used correctly.

**Step 2: Update .dev.vars.example**

Add:
```
GRIPPY_EMBEDDING_MODEL=text-embedding-qwen3-embedding-4b
GRIPPY_DATA_DIR=./grippy-data
GRIPPY_TIMEOUT=300
```

**Step 3: Update module docstring**

Add new env vars to the module-level docstring in review.py.

**Step 4: Commit**

```bash
git add src/grippy/review.py .dev.vars.example
git commit -m "docs: document new Grippy env vars (embedding, data dir, timeout)"
```

---

## Task 4: Update workflow + action.yml with new env vars [Alpha]

**Files:**
- Modify: `.github/workflows/grippy-review.yml:28-35`
- Modify: `grippy-action/action.yml:9-33` (inputs) and `grippy-action/action.yml:62-69` (env)

**Step 1: Update grippy-review.yml**

Add new env vars to the "Run Grippy review" step:

```yaml
      - name: Run Grippy review
        id: review
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_EVENT_PATH: ${{ github.event_path }}
          GRIPPY_BASE_URL: ${{ secrets.GRIPPY_BASE_URL }}
          GRIPPY_MODEL_ID: ${{ secrets.GRIPPY_MODEL_ID }}
          GRIPPY_EMBEDDING_MODEL: ${{ secrets.GRIPPY_EMBEDDING_MODEL }}
          GRIPPY_DATA_DIR: /opt/grippy-data
          GRIPPY_TIMEOUT: '300'
        run: python -m grippy.review
```

Also update the install step to include persistence extra:
```yaml
      - name: Install navi-bootstrap with grippy extras
        run: pip install ".[grippy,grippy-persistence]"
```

**Step 2: Update action.yml inputs**

Add new inputs:
```yaml
  embedding-model:
    description: 'Embedding model name at the same endpoint'
    required: false
    default: 'text-embedding-qwen3-embedding-4b'
  data-dir:
    description: 'Persistent directory for graph DB and LanceDB'
    required: false
    default: './grippy-data'
  timeout:
    description: 'Review timeout in seconds'
    required: false
    default: '300'
```

Update the run step env:
```yaml
      - name: Run Grippy review
        id: review
        shell: bash
        env:
          GITHUB_TOKEN: ${{ inputs.github-token }}
          GRIPPY_BASE_URL: ${{ inputs.base-url }}
          GRIPPY_MODEL_ID: ${{ inputs.model-id }}
          GRIPPY_MODE: ${{ inputs.mode }}
          GRIPPY_EMBEDDING_MODEL: ${{ inputs.embedding-model }}
          GRIPPY_DATA_DIR: ${{ inputs.data-dir }}
          GRIPPY_TIMEOUT: ${{ inputs.timeout }}
        run: python -m grippy.review
```

Update install to include persistence:
```yaml
      - name: Install navi-bootstrap with grippy extras
        shell: bash
        run: |
          pip install "navi-bootstrap[grippy,grippy-persistence] @ git+https://github.com/Project-Navi/repo.git@${{ inputs.navi-bootstrap-ref }}"
```

**Step 3: Commit**

```bash
git add .github/workflows/grippy-review.yml grippy-action/action.yml
git commit -m "ci: add embedding, data dir, timeout env vars to workflow + action"
```

---

## Task 5: M1 — Timeout wrapper for run_review() [Alpha]

**Files:**
- Modify: `src/grippy/review.py` (add timeout logic in main)
- Test: `tests/test_grippy_review.py`

**Context:** If LM Studio hangs, the CI job hangs forever. Add SIGALRM-based timeout on Linux.

**Step 1: Write failing test**

```python
class TestReviewTimeout:
    def test_timeout_raises_on_slow_review(self, monkeypatch):
        """Review that exceeds timeout raises TimeoutError."""
        import signal
        from grippy.review import _with_timeout

        def slow_fn():
            import time
            time.sleep(10)

        with pytest.raises(TimeoutError, match="timed out"):
            _with_timeout(slow_fn, timeout_seconds=1)

    def test_timeout_zero_disables(self, monkeypatch):
        """timeout_seconds=0 means no timeout."""
        from grippy.review import _with_timeout

        result = _with_timeout(lambda: 42, timeout_seconds=0)
        assert result == 42
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_review.py::TestReviewTimeout -v`
Expected: FAIL — _with_timeout doesn't exist

**Step 3: Implement _with_timeout**

Add to `src/grippy/review.py`:

```python
def _with_timeout(fn: Callable[[], Any], *, timeout_seconds: int) -> Any:
    """Run fn with a SIGALRM timeout (Linux only). 0 = no timeout."""
    if timeout_seconds <= 0:
        return fn()

    import signal

    def _handler(signum: int, frame: Any) -> None:
        msg = f"Review timed out after {timeout_seconds}s"
        raise TimeoutError(msg)

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(timeout_seconds)
    try:
        return fn()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
```

Then in `main()`, wrap the run_review call:
```python
timeout_seconds = int(os.environ.get("GRIPPY_TIMEOUT", "300"))
# ...
review = _with_timeout(
    lambda: run_review(agent, user_message),
    timeout_seconds=timeout_seconds,
)
```

Add `TimeoutError` to the except chain alongside `ReviewParseError`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_review.py::TestReviewTimeout -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/grippy/review.py tests/test_grippy_review.py
git commit -m "fix: M1 — add SIGALRM timeout for review to prevent hung CI jobs"
```

---

## Task 6: M2 — Fork diff fetch graceful 403 handling [Alpha]

**Files:**
- Modify: `src/grippy/review.py:200-215` (fetch_pr_diff)
- Test: `tests/test_grippy_review.py`

**Context:** The raw diff API (`application/vnd.github.v3.diff`) works for fork PRs, but the token might lack access (403). Handle this gracefully instead of a raw traceback.

**Step 1: Write failing test**

```python
class TestFetchPrDiffForkHandling:
    @patch("requests.get")
    def test_403_raises_descriptive_error(self, mock_get):
        """403 from diff endpoint gives a helpful error message."""
        from requests.exceptions import HTTPError

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.raise_for_status.side_effect = HTTPError(
            "403 Forbidden", response=mock_resp
        )
        mock_get.return_value = mock_resp

        with pytest.raises(HTTPError):
            fetch_pr_diff("token", "org/repo", 42)

    @patch("requests.get")
    def test_successful_fork_diff(self, mock_get):
        """Fork PRs return diff successfully when token has access."""
        mock_resp = MagicMock()
        mock_resp.text = "diff --git a/fork-file.py b/fork-file.py\n+new"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = fetch_pr_diff("token", "org/fork-repo", 99)
        assert "fork-file.py" in result
```

**Step 2: Run test to verify it fails/passes**

Run: `uv run pytest tests/test_grippy_review.py::TestFetchPrDiffForkHandling -v`
Expected: May already pass (existing code calls raise_for_status). If so, the test documents the behavior.

**Step 3: Update main() error handling for diff fetch**

In main(), wrap the fetch_pr_diff call:
```python
try:
    diff = fetch_pr_diff(token, pr_event["repo"], pr_event["pr_number"])
except Exception as exc:
    print(f"::error::Failed to fetch PR diff: {exc}")
    if "403" in str(exc):
        print("::error::Token may lack access to this PR (fork?). Check GITHUB_TOKEN permissions.")
    try:
        failure_body = (
            f"## ❌ Grippy Review — DIFF FETCH ERROR\n\n"
            f"Could not fetch PR diff: `{exc}`\n\n"
            f"{COMMENT_MARKER}"
        )
        post_comment(token, pr_event["repo"], pr_event["pr_number"], failure_body)
    except Exception:
        pass
    sys.exit(1)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_grippy_review.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/grippy/review.py tests/test_grippy_review.py
git commit -m "fix: M2 — graceful error handling for fork PR diff fetch (403)"
```

---

## Task 7: M3 — main() integration tests (mock-based) [Alpha]

**Files:**
- Test: `tests/test_grippy_review.py`

**Context:** Test the full main() orchestration with mocks. These verify the wiring, not the LLM. Depends on Task 1 being complete (new API wired in).

**Step 1: Write tests**

```python
class TestMainOrchestration:
    """Mock-based integration tests for main() — verifies the full flow."""

    def _setup_env(self, monkeypatch, tmp_path):
        """Helper to set up env vars and event file for main()."""
        event = {
            "pull_request": {
                "number": 42, "title": "feat: test PR",
                "user": {"login": "testdev"},
                "head": {"ref": "feature/test"}, "base": {"ref": "main"},
                "body": "Test PR description",
            },
            "repository": {"full_name": "org/repo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("GRIPPY_TIMEOUT", "0")  # no timeout in tests
        return event_path

    @patch("grippy.review.post_comment")
    @patch("grippy.review.fetch_pr_diff")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    def test_happy_path(
        self, mock_create, mock_run_review, mock_to_graph, mock_store_cls,
        mock_fetch, mock_post, tmp_path, monkeypatch,
    ):
        """Happy path: diff → review → graph → persist → comment."""
        self._setup_env(monkeypatch, tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.return_value = _make_review()
        mock_to_graph.return_value = MagicMock(nodes=[MagicMock()] * 5)

        from grippy.review import main
        main()

        mock_run_review.assert_called_once()
        mock_to_graph.assert_called_once()
        mock_store_cls.return_value.store_review.assert_called_once()
        mock_post.assert_called_once()

    @patch("grippy.review.post_comment")
    @patch("grippy.review.fetch_pr_diff")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    def test_agent_failure_posts_error_comment(
        self, mock_create, mock_run_review, mock_fetch, mock_post,
        tmp_path, monkeypatch,
    ):
        """Agent failure posts error comment and exits 1."""
        self._setup_env(monkeypatch, tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.side_effect = RuntimeError("LLM exploded")

        from grippy.review import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        mock_post.assert_called_once()
        assert "ERROR" in mock_post.call_args[0][3]

    @patch("grippy.review.post_comment")
    @patch("grippy.review.fetch_pr_diff")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    def test_parse_failure_posts_error_comment(
        self, mock_create, mock_run_review, mock_fetch, mock_post,
        tmp_path, monkeypatch,
    ):
        """ReviewParseError posts parse error comment and exits 1."""
        from grippy.retry import ReviewParseError

        self._setup_env(monkeypatch, tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.side_effect = ReviewParseError(
            attempts=3, last_raw="garbage", errors=["bad json"]
        )

        from grippy.review import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        mock_post.assert_called_once()
        assert "PARSE" in mock_post.call_args[0][3]

    @patch("grippy.review.post_comment")
    @patch("grippy.review.fetch_pr_diff")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    def test_merge_blocking_exits_nonzero(
        self, mock_create, mock_run_review, mock_to_graph, mock_store_cls,
        mock_fetch, mock_post, tmp_path, monkeypatch,
    ):
        """Merge-blocking verdict causes exit code 1."""
        self._setup_env(monkeypatch, tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.return_value = _make_review(
            verdict=Verdict(
                status=VerdictStatus.FAIL,
                threshold_applied=70,
                merge_blocking=True,
                summary="Critical issues.",
            ),
        )
        mock_to_graph.return_value = MagicMock(nodes=[])

        from grippy.review import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_grippy_review.py::TestMainOrchestration -v`
Expected: All 4 pass (once Task 1 is complete)

**Step 3: Commit**

```bash
git add tests/test_grippy_review.py
git commit -m "test: M3 — main() integration tests for all orchestration paths"
```

---

## Task 8: Code review Bravo's wiring [Alpha]

**No code to write.** This is a review task.

**Checklist:**
- [ ] `run_review()` called instead of `agent.run()` — no direct agent.run calls remain
- [ ] `ReviewParseError` caught (not `ValueError`) — matches retry.py's exception type
- [ ] `review_to_graph()` called on the validated GrippyReview
- [ ] `GrippyStore` created with correct paths (graph_db_path, lance_dir)
- [ ] `embed_fn` has correct signature: `Callable[[list[str]], list[list[float]]]` (batch, not single)
- [ ] Persistence failure is non-fatal (review still gets posted)
- [ ] New env vars have sensible defaults
- [ ] No unused imports after the refactor
- [ ] `parse_review_response()` is no longer called (run_review handles parsing)
- [ ] ruff + mypy clean

Run:
```bash
uv run ruff check src/grippy/review.py
uv run mypy src/grippy/review.py
uv run pytest tests/test_grippy_review.py -v
```

---

## Task 9: Configure runner secrets + data dir [Nelson]

**No code.** Infrastructure task.

**Steps:**
1. Add GitHub Actions secrets to the repo:
   - `GRIPPY_BASE_URL` — LM Studio endpoint URL
   - `GRIPPY_MODEL_ID` — Devstral model name
   - `GRIPPY_EMBEDDING_MODEL` — `text-embedding-qwen3-embedding-4b`

2. Create persistent data directory on GPU runner:
   ```bash
   sudo mkdir -p /opt/grippy-data
   sudo chown runner:runner /opt/grippy-data
   ```

3. Verify LM Studio serves both models:
   ```bash
   curl $GRIPPY_BASE_URL/models
   # Should list both devstral and qwen3 embedding model
   ```

---

## Task 10: Dogfood — end-to-end test on real PR [All]

**Steps:**

1. Create a test branch:
   ```bash
   git checkout -b test/grippy-dogfood
   echo "# TODO: remove after dogfood test" >> DEBT.md
   git add DEBT.md && git commit -m "test: trigger grippy review"
   git push -u origin test/grippy-dogfood
   ```

2. Open PR via `gh pr create --title "test: grippy dogfood" --body "Testing Grippy end-to-end"`

3. Watch the Actions run:
   ```bash
   gh run watch
   ```

4. Verify:
   - [ ] Review comment posted with score, findings, personality
   - [ ] No duplicate comments on re-push
   - [ ] Graph data persisted at `/opt/grippy-data/`
   - [ ] Timeout works (check logs for timeout env var)
   - [ ] Exit code matches merge-blocking status

5. Clean up:
   ```bash
   gh pr close --delete-branch
   ```

---

## Summary

| Task | Owner | New tests | Depends on |
|------|-------|-----------|------------|
| 1. Wire pipeline | Bravo | 1 | — |
| 2. embed_fn | Bravo | 3 | T1 |
| 3. Env vars | Bravo | 0 | T1 |
| 4. Workflow update | Alpha | 0 | T3 |
| 5. M1 timeout | Alpha | 2 | T1 |
| 6. M2 fork 403 | Alpha | 2 | — |
| 7. M3 integration | Alpha | 4 | T1 |
| 8. Code review | Alpha | 0 | T1 |
| 9. Runner config | Nelson | 0 | T4 |
| 10. Dogfood | All | 0 | T1-T9 |

**Total new tests:** ~12
**Expected suite total:** ~462 tests
