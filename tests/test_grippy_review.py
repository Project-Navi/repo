"""Tests for Grippy CI review entry point — reads PR, runs agent, posts comment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from grippy.review import (
    COMMENT_MARKER_PREFIX,
    MAX_DIFF_CHARS,
    _with_timeout,
    fetch_pr_diff,
    format_review_comment,
    load_pr_event,
    parse_review_response,
    post_comment,
    truncate_diff,
)
from grippy.schema import (
    AsciiArtKey,
    ComplexityTier,
    Escalation,
    EscalationCategory,
    EscalationTarget,
    Finding,
    FindingCategory,
    GrippyReview,
    Personality,
    PRMetadata,
    ReviewMeta,
    ReviewScope,
    Score,
    ScoreBreakdown,
    ScoreDeductions,
    Severity,
    ToneRegister,
    Verdict,
    VerdictStatus,
)

# --- Fixtures ---


def _make_finding(**overrides: Any) -> Finding:
    defaults: dict[str, Any] = {
        "id": "F-001",
        "severity": Severity.HIGH,
        "confidence": 85,
        "category": FindingCategory.SECURITY,
        "file": "src/app.py",
        "line_start": 42,
        "line_end": 45,
        "title": "SQL injection in query builder",
        "description": "User input passed directly to SQL",
        "suggestion": "Use parameterized queries",
        "governance_rule_id": "SEC-001",
        "evidence": "f-string in execute()",
        "grippy_note": "This one hurt to read.",
    }
    defaults.update(overrides)
    return Finding(**defaults)


def _make_review(**overrides: Any) -> GrippyReview:
    defaults: dict[str, Any] = {
        "version": "1.0",
        "audit_type": "pr_review",
        "timestamp": "2026-02-26T12:00:00Z",
        "model": "devstral-small-2-24b-instruct-2512",
        "pr": PRMetadata(
            title="feat: add user auth",
            author="testdev",
            branch="feature/auth → main",
            complexity_tier=ComplexityTier.STANDARD,
        ),
        "scope": ReviewScope(
            files_in_diff=3,
            files_reviewed=3,
            coverage_percentage=100.0,
            governance_rules_applied=["SEC-001"],
            modes_active=["pr_review"],
        ),
        "findings": [_make_finding()],
        "escalations": [],
        "score": Score(
            overall=72,
            breakdown=ScoreBreakdown(
                security=60, logic=80, governance=75, reliability=70, observability=75
            ),
            deductions=ScoreDeductions(
                critical_count=0, high_count=1, medium_count=0, low_count=0, total_deduction=28
            ),
        ),
        "verdict": Verdict(
            status=VerdictStatus.PROVISIONAL,
            threshold_applied=70,
            merge_blocking=False,
            summary="Fix the SQL injection before merge.",
        ),
        "personality": Personality(
            tone_register=ToneRegister.GRUMPY,
            opening_catchphrase="*adjusts reading glasses*",
            closing_line="Fix it or I'm telling the security team.",
            ascii_art_key=AsciiArtKey.WARNING,
        ),
        "meta": ReviewMeta(
            review_duration_ms=45000,
            tokens_used=8200,
            context_files_loaded=3,
            confidence_filter_suppressed=1,
            duplicate_filter_suppressed=0,
        ),
    }
    defaults.update(overrides)
    return GrippyReview(**defaults)


# --- load_pr_event ---


class TestLoadPrEvent:
    def test_loads_pull_request_event(self, tmp_path: Path) -> None:
        """Parses PR number, repo, title, author, branch from event JSON."""
        event = {
            "pull_request": {
                "number": 42,
                "title": "feat: add auth",
                "user": {"login": "nelson"},
                "head": {"ref": "feature/auth"},
                "base": {"ref": "main"},
                "body": "Adds authentication system",
            },
            "repository": {"full_name": "Project-Navi/repo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        result = load_pr_event(event_path)
        assert result["pr_number"] == 42
        assert result["repo"] == "Project-Navi/repo"
        assert result["title"] == "feat: add auth"
        assert result["author"] == "nelson"
        assert result["head_ref"] == "feature/auth"
        assert result["base_ref"] == "main"
        assert result["description"] == "Adds authentication system"

    def test_missing_event_file_raises(self) -> None:
        """Raises FileNotFoundError for nonexistent event file."""
        with pytest.raises(FileNotFoundError):
            load_pr_event(Path("/nonexistent/event.json"))

    def test_missing_pull_request_key_raises(self, tmp_path: Path) -> None:
        """Raises KeyError when event has no pull_request key."""
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps({"action": "opened"}))

        with pytest.raises(KeyError, match="pull_request"):
            load_pr_event(event_path)

    def test_null_body_becomes_empty_string(self, tmp_path: Path) -> None:
        """PR body of null becomes empty string."""
        event = {
            "pull_request": {
                "number": 1,
                "title": "fix: typo",
                "user": {"login": "dev"},
                "head": {"ref": "fix"},
                "base": {"ref": "main"},
                "body": None,
            },
            "repository": {"full_name": "org/repo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        result = load_pr_event(event_path)
        assert result["description"] == ""


# --- format_review_comment ---


class TestFormatReviewComment:
    def test_contains_verdict_header(self) -> None:
        """Comment starts with verdict status as header."""
        review = _make_review()
        comment = format_review_comment(review)
        assert "Grippy Review" in comment
        assert "PROVISIONAL" in comment

    def test_contains_score(self) -> None:
        """Comment includes the overall score."""
        review = _make_review()
        comment = format_review_comment(review)
        assert "72" in comment
        assert "/100" in comment

    def test_contains_findings(self) -> None:
        """Comment lists each finding with severity and title."""
        review = _make_review()
        comment = format_review_comment(review)
        assert "HIGH" in comment
        assert "SQL injection in query builder" in comment
        assert "src/app.py" in comment

    def test_contains_personality(self) -> None:
        """Comment includes Grippy's personality elements."""
        review = _make_review()
        comment = format_review_comment(review)
        assert "*adjusts reading glasses*" in comment
        assert "Fix it or I'm telling the security team." in comment

    def test_empty_findings_shows_clean(self) -> None:
        """Review with no findings shows a clean message."""
        review = _make_review(
            findings=[],
            score=Score(
                overall=100,
                breakdown=ScoreBreakdown(
                    security=100, logic=100, governance=100, reliability=100, observability=100
                ),
                deductions=ScoreDeductions(
                    critical_count=0, high_count=0, medium_count=0, low_count=0, total_deduction=0
                ),
            ),
            verdict=Verdict(
                status=VerdictStatus.PASS,
                threshold_applied=70,
                merge_blocking=False,
                summary="Ship it.",
            ),
        )
        comment = format_review_comment(review)
        assert "No findings" in comment or "PASS" in comment

    def test_finding_links_to_file_line(self) -> None:
        """Each finding references file:line for easy navigation."""
        review = _make_review(findings=[_make_finding(file="src/auth.py", line_start=99)])
        comment = format_review_comment(review)
        assert "src/auth.py" in comment

    def test_escalations_included(self) -> None:
        """Escalations are shown in the comment."""
        escalation = Escalation(
            id="E-001",
            severity="CRITICAL",
            category=EscalationCategory.SECURITY,
            summary="Credentials in source code",
            details="API key hardcoded in config.py",
            recommended_target=EscalationTarget.SECURITY_TEAM,
            blocking=True,
        )
        review = _make_review(escalations=[escalation])
        comment = format_review_comment(review)
        assert "Escalation" in comment or "E-001" in comment
        assert "Credentials in source code" in comment

    def test_merge_blocking_flagged(self) -> None:
        """Merge-blocking verdict is clearly marked."""
        review = _make_review(
            verdict=Verdict(
                status=VerdictStatus.FAIL,
                threshold_applied=70,
                merge_blocking=True,
                summary="Critical security issues found.",
            ),
        )
        comment = format_review_comment(review)
        assert "FAIL" in comment
        # Should indicate merge is blocked
        assert "block" in comment.lower() or "FAIL" in comment


# --- parse_review_response ---


class TestParseReviewResponse:
    def test_parses_model_instance(self) -> None:
        """Direct GrippyReview instance passes through."""
        review = _make_review()
        result = parse_review_response(review)
        assert result.score.overall == 72

    def test_parses_dict(self) -> None:
        """Dict is validated as GrippyReview."""
        review = _make_review()
        result = parse_review_response(review.model_dump())
        assert result.score.overall == 72

    def test_parses_json_string(self) -> None:
        """JSON string is parsed and validated."""
        review = _make_review()
        result = parse_review_response(review.model_dump_json())
        assert result.score.overall == 72

    def test_invalid_json_raises(self) -> None:
        """Non-JSON string raises ValueError."""
        with pytest.raises(ValueError, match="parse"):
            parse_review_response("not json at all")

    def test_invalid_schema_raises(self) -> None:
        """JSON that doesn't match schema raises ValueError."""
        with pytest.raises(ValueError, match="validat"):
            parse_review_response(json.dumps({"version": "1.0"}))


# --- C1: fetch_pr_diff uses raw diff API, not paginated compare ---


class TestFetchPrDiff:
    @patch("requests.get")
    def test_fetches_raw_diff_via_api(self, mock_get: MagicMock) -> None:
        """Uses GitHub API with diff media type, not compare().files."""
        mock_response = MagicMock()
        mock_response.text = (
            "diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new"
        )
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_pr_diff("test-token", "org/repo", 42)

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "org/repo" in call_args[0][0]
        assert "42" in call_args[0][0]
        assert "application/vnd.github.v3.diff" in str(call_args[1].get("headers", {}))
        assert "diff --git" in result

    @patch("requests.get")
    def test_includes_auth_header(self, mock_get: MagicMock) -> None:
        """Request includes Authorization header with token."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetch_pr_diff("my-secret-token", "org/repo", 1)

        headers = mock_get.call_args[1]["headers"]
        assert "my-secret-token" in headers.get("Authorization", "")

    @patch("requests.get")
    def test_raises_on_http_error(self, mock_get: MagicMock) -> None:
        """HTTP errors propagate (e.g., 404 for missing PR)."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        with pytest.raises(Exception, match="404"):
            fetch_pr_diff("token", "org/repo", 999)


# --- M2: fetch_pr_diff fork handling ---


class TestFetchPrDiffForkHandling:
    """Fork-specific scenarios for the raw diff endpoint."""

    @patch("requests.get")
    def test_403_raises_descriptive_error(self, mock_get: MagicMock) -> None:
        """A 403 from the diff endpoint raises HTTPError (e.g., fork token lacks access)."""
        from requests.exceptions import HTTPError

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = HTTPError(
            "403 Forbidden", response=mock_response
        )
        mock_get.return_value = mock_response

        with pytest.raises(HTTPError, match="403"):
            fetch_pr_diff("fork-token", "upstream/repo", 99)

    @patch("requests.get")
    def test_successful_fork_diff(self, mock_get: MagicMock) -> None:
        """Fork PRs return diff successfully when the token has access."""
        mock_response = MagicMock()
        mock_response.text = (
            "diff --git a/lib.py b/lib.py\n--- a/lib.py\n+++ b/lib.py\n@@ -1 +1 @@\n-old\n+new"
        )
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_pr_diff("fork-token", "upstream/repo", 55)

        assert "diff --git" in result
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "upstream/repo" in call_url
        assert "55" in call_url


# --- post_comment: SHA-scoped upsert ---


class TestPostComment:
    @patch("github.Github")
    def test_creates_new_comment_for_new_sha(self, mock_gh_cls: MagicMock) -> None:
        """New SHA creates a new comment."""
        mock_pr = MagicMock()
        mock_pr.get_issue_comments.return_value = []
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_gh_cls.return_value.get_repo.return_value = mock_repo

        post_comment("token", "org/repo", 42, "Review body", head_sha="abc123")

        mock_pr.create_issue_comment.assert_called_once()

    @patch("github.Github")
    def test_edits_existing_comment_for_same_sha(self, mock_gh_cls: MagicMock) -> None:
        """Re-run on same SHA edits the existing comment."""
        existing_comment = MagicMock()
        existing_comment.body = f"Old review\n{COMMENT_MARKER_PREFIX}abc123 -->"
        mock_pr = MagicMock()
        mock_pr.get_issue_comments.return_value = [existing_comment]
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_gh_cls.return_value.get_repo.return_value = mock_repo

        post_comment("token", "org/repo", 42, "New review", head_sha="abc123")

        existing_comment.edit.assert_called_once_with("New review")
        mock_pr.create_issue_comment.assert_not_called()

    @patch("github.Github")
    def test_new_comment_for_different_sha(self, mock_gh_cls: MagicMock) -> None:
        """Different SHA creates new comment even if old review exists."""
        existing_comment = MagicMock()
        existing_comment.body = f"Old review\n{COMMENT_MARKER_PREFIX}abc123 -->"
        mock_pr = MagicMock()
        mock_pr.get_issue_comments.return_value = [existing_comment]
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_gh_cls.return_value.get_repo.return_value = mock_repo

        post_comment("token", "org/repo", 42, "New review", head_sha="def456")

        mock_pr.create_issue_comment.assert_called_once()
        existing_comment.edit.assert_not_called()

    @patch("github.Github")
    def test_no_sha_always_creates_new(self, mock_gh_cls: MagicMock) -> None:
        """Without head_sha, always creates a new comment (error comments)."""
        mock_pr = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_gh_cls.return_value.get_repo.return_value = mock_repo

        post_comment("token", "org/repo", 42, "Error comment")

        mock_pr.create_issue_comment.assert_called_once()


# --- T2: make_embed_fn ---


class TestMakeEmbedFn:
    """Tests for make_embed_fn — LM Studio /v1/embeddings wrapper."""

    @patch("requests.post")
    def test_calls_embeddings_endpoint(self, mock_post: MagicMock) -> None:
        """embed_fn hits /v1/embeddings with correct model and input."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
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
    def test_batch_embedding(self, mock_post: MagicMock) -> None:
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
        assert result[0] == [0.1, 0.2]
        assert result[1] == [0.3, 0.4]

    @patch("requests.post")
    def test_http_error_propagates(self, mock_post: MagicMock) -> None:
        """HTTP errors from embedding endpoint propagate."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        with pytest.raises(Exception, match="503"):
            fn(["hello"])

    @patch("requests.post")
    def test_openai_key_sent_to_openai_host(
        self, mock_post: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OPENAI_API_KEY is sent when endpoint is api.openai.com."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.delenv("GRIPPY_API_KEY", raising=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("https://api.openai.com/v1", "test-model")
        fn(["hello"])

        headers = mock_post.call_args[1].get("headers", {})
        assert headers.get("Authorization") == "Bearer sk-openai-test"

    @patch("requests.post")
    def test_openai_key_not_sent_to_non_openai_host(
        self, mock_post: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OPENAI_API_KEY is NOT sent to non-OpenAI endpoints."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.delenv("GRIPPY_API_KEY", raising=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        fn(["hello"])

        headers = mock_post.call_args[1].get("headers", {})
        assert "Authorization" not in headers

    @patch("requests.post")
    def test_grippy_api_key_sent_to_any_host(
        self, mock_post: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GRIPPY_API_KEY is used for any endpoint."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("GRIPPY_API_KEY", "grippy-secret")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.2]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        fn(["hello"])

        headers = mock_post.call_args[1].get("headers", {})
        assert headers.get("Authorization") == "Bearer grippy-secret"

    @patch("requests.post")
    def test_no_auth_when_no_keys(
        self, mock_post: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No Authorization header when neither key is set."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GRIPPY_API_KEY", raising=False)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.3]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        fn(["hello"])

        headers = mock_post.call_args[1].get("headers", {})
        assert "Authorization" not in headers

    @patch("requests.post")
    def test_openai_key_precedence_on_openai_host(
        self, mock_post: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OPENAI_API_KEY takes precedence over GRIPPY_API_KEY on OpenAI host."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("GRIPPY_API_KEY", "grippy-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.4]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("https://api.openai.com/v1", "test-model")
        fn(["hello"])

        headers = mock_post.call_args[1].get("headers", {})
        assert headers.get("Authorization") == "Bearer sk-openai"

    @patch("requests.post")
    def test_non_openai_host_with_both_keys_uses_grippy(
        self, mock_post: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-OpenAI host with both keys uses GRIPPY_API_KEY, not OPENAI_API_KEY."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("GRIPPY_API_KEY", "grippy-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.5]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from grippy.review import make_embed_fn

        fn = make_embed_fn("http://localhost:1234/v1", "test-model")
        fn(["hello"])

        headers = mock_post.call_args[1].get("headers", {})
        assert headers.get("Authorization") == "Bearer grippy-key"


# --- T1: main() uses run_review + review_to_graph + GrippyStore ---


class TestMainWiringNewAPI:
    """Verify main() calls run_review instead of agent.run, and pipes through graph + persistence."""

    def _make_event_file(self, tmp_path: Path) -> Path:
        event = {
            "pull_request": {
                "number": 1,
                "title": "test",
                "user": {"login": "dev"},
                "head": {"ref": "feat"},
                "base": {"ref": "main"},
                "body": "",
            },
            "repository": {"full_name": "org/repo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))
        return event_path

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_main_calls_run_review_not_agent_run(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() should call run_review(agent, message), not agent.run(message)."""
        event_path = self._make_event_file(tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        review = _make_review()
        mock_run_review.return_value = review
        mock_to_graph.return_value = MagicMock(nodes=[])

        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))

        from grippy.review import main

        main()

        mock_run_review.assert_called_once()
        mock_create.return_value.run.assert_not_called()

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_main_calls_review_to_graph(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() should transform review into a graph."""
        event_path = self._make_event_file(tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        review = _make_review()
        mock_run_review.return_value = review
        mock_to_graph.return_value = MagicMock(nodes=[])

        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))

        from grippy.review import main

        main()

        mock_to_graph.assert_called_once_with(review)

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_main_persists_graph(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """main() should persist the review graph via GrippyStore."""
        event_path = self._make_event_file(tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.return_value = _make_review()
        graph = MagicMock(nodes=[])
        mock_to_graph.return_value = graph

        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))

        from grippy.review import main

        main()

        mock_store_cls.assert_called_once()
        mock_store_cls.return_value.store_review.assert_called_once_with(graph)

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_persistence_failure_non_fatal(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Persistence failure should not prevent the review comment from posting."""
        event_path = self._make_event_file(tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.return_value = _make_review()
        mock_to_graph.return_value = MagicMock(nodes=[])
        mock_store_cls.return_value.store_review.side_effect = RuntimeError("LanceDB exploded")

        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))

        from grippy.review import main

        # Should NOT raise — persistence failure is non-fatal
        main()

        # Comment should still be posted
        mock_post.assert_called_once()

    @patch("grippy.review.post_comment")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_review_parse_error_posts_failure_comment(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ReviewParseError posts parse error comment and exits 1."""
        from grippy.retry import ReviewParseError

        event_path = self._make_event_file(tmp_path)
        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.side_effect = ReviewParseError(
            attempts=3, last_raw="garbage", errors=["bad json"]
        )

        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))

        from grippy.review import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        mock_post.assert_called_once()
        assert "PARSE" in mock_post.call_args[0][3]


# --- H2: diff size cap ---


class TestTruncateDiff:
    def test_small_diff_unchanged(self) -> None:
        """Diffs under the cap pass through unchanged."""
        diff = "diff --git a/foo.py b/foo.py\n-old\n+new"
        result = truncate_diff(diff)
        assert result == diff

    def test_large_diff_truncated(self) -> None:
        """Diffs over MAX_DIFF_CHARS are truncated with a warning."""
        # Build a diff with many file blocks that exceed the cap
        block = "diff --git a/f.py b/f.py\n" + ("+" * 5000) + "\n"
        diff = block * 100  # 100 files x ~5K each = ~500K chars
        assert len(diff) > MAX_DIFF_CHARS, "Test diff must exceed cap"
        result = truncate_diff(diff)
        assert len(result) < len(diff)
        assert "truncated" in result.lower()

    def test_truncated_diff_ends_at_file_boundary(self) -> None:
        """Truncation happens at a file boundary, not mid-hunk."""
        # Build a diff with multiple files, total > cap
        file_block = (
            "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n"
            + "@@ -1,10 +1,10 @@\n"
            + ("-old line\n+new line\n" * 100)
        )
        diff = file_block * 50  # Should exceed cap
        if len(diff) <= MAX_DIFF_CHARS:
            pytest.skip("Test diff not large enough to trigger truncation")
        result = truncate_diff(diff)
        # Should not cut in the middle of a hunk
        assert result.rstrip().endswith("(truncated)") or "truncated" in result

    def test_truncation_preserves_complete_files(self) -> None:
        """Truncated output contains only complete file diffs."""
        small_file = "diff --git a/small.py b/small.py\n--- a/small.py\n+++ b/small.py\n@@ -1 +1 @@\n-a\n+b\n"
        big_file = (
            "diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n" + "x" * MAX_DIFF_CHARS
        )
        diff = small_file + big_file
        result = truncate_diff(diff)
        # Should contain the small file completely
        assert "small.py" in result


# --- M1: _with_timeout ---


class TestReviewTimeout:
    """Tests for _with_timeout — SIGALRM-based review timeout."""

    def test_timeout_raises_on_slow_function(self) -> None:
        """Function exceeding timeout raises TimeoutError."""
        import time

        def slow() -> None:
            time.sleep(10)

        with pytest.raises(TimeoutError, match="timed out"):
            _with_timeout(slow, timeout_seconds=1)

    def test_timeout_zero_disables(self) -> None:
        """timeout_seconds=0 means no timeout — function runs normally."""
        result = _with_timeout(lambda: 42, timeout_seconds=0)
        assert result == 42

    def test_timeout_negative_disables(self) -> None:
        """Negative timeout_seconds also disables timeout."""
        result = _with_timeout(lambda: "ok", timeout_seconds=-1)
        assert result == "ok"

    def test_fast_function_returns_normally(self) -> None:
        """Function completing before timeout returns its value."""
        result = _with_timeout(lambda: 99, timeout_seconds=10)
        assert result == 99

    def test_alarm_restored_after_success(self) -> None:
        """SIGALRM handler is restored after successful execution."""
        import signal

        original = signal.getsignal(signal.SIGALRM)
        _with_timeout(lambda: 1, timeout_seconds=5)
        after = signal.getsignal(signal.SIGALRM)
        assert after is original

    def test_alarm_restored_after_timeout(self) -> None:
        """SIGALRM handler is restored even after a timeout."""
        import signal
        import time

        original = signal.getsignal(signal.SIGALRM)
        with pytest.raises(TimeoutError):
            _with_timeout(lambda: time.sleep(10), timeout_seconds=1)
        after = signal.getsignal(signal.SIGALRM)
        assert after is original


# --- M3: main() integration tests (mock-based) ---


class TestMainOrchestration:
    """End-to-end orchestration tests for main() — all external calls mocked."""

    def _make_event_file(self, tmp_path: Path) -> Path:
        """Write a minimal PR event JSON and return its path."""
        event = {
            "pull_request": {
                "number": 7,
                "title": "feat: add auth",
                "user": {"login": "testdev"},
                "head": {"ref": "feature/auth"},
                "base": {"ref": "main"},
                "body": "Adds authentication system",
            },
            "repository": {"full_name": "org/repo"},
        }
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))
        return event_path

    def _setup_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        event_path: Path,
        tmp_path: Path,
    ) -> None:
        """Set required env vars for main()."""
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
        monkeypatch.setenv("GRIPPY_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("GRIPPY_TIMEOUT", "0")

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_happy_path_posts_comment_and_persists(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Happy path: review succeeds, comment posted, graph persisted."""
        event_path = self._make_event_file(tmp_path)
        self._setup_env(monkeypatch, event_path, tmp_path)

        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        review = _make_review()
        mock_run_review.return_value = review
        graph = MagicMock(nodes=[])
        mock_to_graph.return_value = graph

        from grippy.review import main

        main()

        # Comment was posted with "Grippy Review" in the body
        mock_post.assert_called_once()
        posted_body = mock_post.call_args[0][3]
        assert "Grippy Review" in posted_body

        # Graph was persisted
        mock_store_cls.return_value.store_review.assert_called_once_with(graph)

    @patch("grippy.review.post_comment")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_agent_failure_posts_error_comment(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Agent RuntimeError posts ERROR comment and exits 1."""
        event_path = self._make_event_file(tmp_path)
        self._setup_env(monkeypatch, event_path, tmp_path)

        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.side_effect = RuntimeError("LLM crashed")

        from grippy.review import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

        # Error comment was posted
        mock_post.assert_called_once()
        posted_body = mock_post.call_args[0][3]
        assert "ERROR" in posted_body

    @patch("grippy.review.post_comment")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_parse_failure_posts_parse_error_comment(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ReviewParseError posts PARSE ERROR comment and exits 1."""
        from grippy.retry import ReviewParseError

        event_path = self._make_event_file(tmp_path)
        self._setup_env(monkeypatch, event_path, tmp_path)

        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.side_effect = ReviewParseError(
            attempts=3, last_raw="garbage", errors=["bad"]
        )

        from grippy.review import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

        # Parse error comment was posted
        mock_post.assert_called_once()
        posted_body = mock_post.call_args[0][3]
        assert "PARSE ERROR" in posted_body

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_merge_blocking_exits_nonzero(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Merge-blocking verdict posts review comment then exits 1."""
        event_path = self._make_event_file(tmp_path)
        self._setup_env(monkeypatch, event_path, tmp_path)

        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        review = _make_review(
            verdict=Verdict(
                status=VerdictStatus.FAIL,
                threshold_applied=70,
                merge_blocking=True,
                summary="Critical security issues found.",
            ),
        )
        mock_run_review.return_value = review
        mock_to_graph.return_value = MagicMock(nodes=[])

        from grippy.review import main

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

        # Review comment was still posted (not an error comment)
        mock_post.assert_called_once()
        posted_body = mock_post.call_args[0][3]
        assert "Grippy Review" in posted_body
        assert "FAIL" in posted_body

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_local_first_defaults_when_env_unset(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When GRIPPY_* env vars are unset, main() uses local-first defaults."""
        event_path = self._make_event_file(tmp_path)
        self._setup_env(monkeypatch, event_path, tmp_path)
        # Ensure GRIPPY_* are unset to test defaults
        monkeypatch.delenv("GRIPPY_BASE_URL", raising=False)
        monkeypatch.delenv("GRIPPY_MODEL_ID", raising=False)
        monkeypatch.delenv("GRIPPY_EMBEDDING_MODEL", raising=False)
        monkeypatch.delenv("GRIPPY_TRANSPORT", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.return_value = _make_review()
        mock_to_graph.return_value = MagicMock(nodes=[])

        import grippy.review as review_mod

        # Point __file__ at tmp_path so .dev.vars resolution finds nothing
        monkeypatch.setattr(review_mod, "__file__", str(tmp_path / "fake" / "grippy" / "review.py"))

        review_mod.main()

        # Verify local-first defaults were passed to create_reviewer
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["base_url"] == "http://localhost:1234/v1"
        assert call_kwargs["model_id"] == "devstral-small-2-24b-instruct-2512"
        assert call_kwargs["transport"] is None

    @patch("grippy.review.post_comment")
    @patch("grippy.review.GrippyStore")
    @patch("grippy.review.review_to_graph")
    @patch("grippy.review.run_review")
    @patch("grippy.review.create_reviewer")
    @patch("grippy.review.fetch_pr_diff")
    def test_transport_passed_to_create_reviewer(
        self,
        mock_fetch: MagicMock,
        mock_create: MagicMock,
        mock_run_review: MagicMock,
        mock_to_graph: MagicMock,
        mock_store_cls: MagicMock,
        mock_post: MagicMock,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """GRIPPY_TRANSPORT env var is passed through to create_reviewer()."""
        event_path = self._make_event_file(tmp_path)
        self._setup_env(monkeypatch, event_path, tmp_path)
        monkeypatch.setenv("GRIPPY_TRANSPORT", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        mock_fetch.return_value = "diff --git a/f.py b/f.py\n-old\n+new"
        mock_run_review.return_value = _make_review()
        mock_to_graph.return_value = MagicMock(nodes=[])

        from grippy.review import main

        main()

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["transport"] == "openai"
