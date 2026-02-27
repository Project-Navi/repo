"""Tests for Grippy GitHub Review API integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from grippy.schema import Finding

# --- Helpers ---


def _make_finding(
    *,
    file: str = "src/app.py",
    line_start: int = 10,
    title: str = "Test finding",
    severity: str = "HIGH",
    category: str = "security",
) -> Finding:
    return Finding(
        id="F-001",
        severity=severity,
        confidence=90,
        category=category,
        file=file,
        line_start=line_start,
        line_end=line_start + 5,
        title=title,
        description="A test finding description.",
        suggestion="Fix this issue.",
        evidence="evidence here",
        grippy_note="Grippy says fix it.",
    )


# --- parse_diff_lines ---


class TestParseDiffLines:
    """parse_diff_lines extracts addressable RIGHT-side lines from unified diff."""

    def test_simple_addition(self) -> None:
        from grippy.github_review import parse_diff_lines

        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -10,3 +10,4 @@ def main():\n"
            "     existing_line\n"
            "+    new_line\n"
            "     another_existing\n"
            "+    another_new\n"
        )
        result = parse_diff_lines(diff)
        assert "src/app.py" in result
        assert 11 in result["src/app.py"]
        assert 13 in result["src/app.py"]

    def test_multiple_files(self) -> None:
        from grippy.github_review import parse_diff_lines

        diff = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1,2 +1,3 @@\n"
            " line1\n"
            "+added\n"
            " line2\n"
            "diff --git a/b.py b/b.py\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -5,2 +5,3 @@\n"
            " old\n"
            "+new\n"
            " old2\n"
        )
        result = parse_diff_lines(diff)
        assert "a.py" in result
        assert "b.py" in result
        assert 2 in result["a.py"]
        assert 6 in result["b.py"]

    def test_empty_diff(self) -> None:
        from grippy.github_review import parse_diff_lines

        result = parse_diff_lines("")
        assert result == {}

    def test_deletion_only_not_addressable(self) -> None:
        from grippy.github_review import parse_diff_lines

        diff = (
            "diff --git a/x.py b/x.py\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -1,3 +1,2 @@\n"
            " keep\n"
            "-removed\n"
            " keep2\n"
        )
        result = parse_diff_lines(diff)
        assert "x.py" in result
        lines = result["x.py"]
        assert 1 in lines
        assert 2 in lines

    def test_new_file(self) -> None:
        from grippy.github_review import parse_diff_lines

        diff = (
            "diff --git a/new.py b/new.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+line1\n"
            "+line2\n"
            "+line3\n"
        )
        result = parse_diff_lines(diff)
        assert "new.py" in result
        assert result["new.py"] == {1, 2, 3}

    def test_hunk_context_lines_addressable(self) -> None:
        """Context lines (unchanged) within a hunk are also addressable."""
        from grippy.github_review import parse_diff_lines

        diff = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -10,5 +10,6 @@ class Foo:\n"
            "     def bar(self):\n"
            "         pass\n"
            "+        new_code()\n"
            "     def baz(self):\n"
            "         pass\n"
        )
        result = parse_diff_lines(diff)
        assert 10 in result["f.py"]
        assert 12 in result["f.py"]  # the added line
        assert 14 in result["f.py"]


# --- classify_findings ---


class TestClassifyFindings:
    """classify_findings splits findings into inline-eligible and off-diff."""

    def test_finding_on_diff_line_is_inline(self) -> None:
        from grippy.github_review import classify_findings

        diff_lines = {"src/app.py": {10, 11, 12}}
        findings = [_make_finding(file="src/app.py", line_start=10)]
        inline, off_diff = classify_findings(findings, diff_lines)
        assert len(inline) == 1
        assert len(off_diff) == 0

    def test_finding_off_diff_goes_to_off_diff(self) -> None:
        from grippy.github_review import classify_findings

        diff_lines = {"src/app.py": {10, 11, 12}}
        findings = [_make_finding(file="src/app.py", line_start=99)]
        inline, off_diff = classify_findings(findings, diff_lines)
        assert len(inline) == 0
        assert len(off_diff) == 1

    def test_finding_in_unmodified_file_is_off_diff(self) -> None:
        from grippy.github_review import classify_findings

        diff_lines = {"src/other.py": {1, 2}}
        findings = [_make_finding(file="src/app.py", line_start=10)]
        inline, off_diff = classify_findings(findings, diff_lines)
        assert len(inline) == 0
        assert len(off_diff) == 1


# --- build_review_comment ---


class TestBuildReviewComment:
    """build_review_comment creates PyGithub-compatible comment dicts."""

    def test_comment_has_required_fields(self) -> None:
        from grippy.github_review import build_review_comment

        finding = _make_finding()
        comment = build_review_comment(finding)
        assert "path" in comment
        assert "body" in comment
        assert "line" in comment
        assert "side" in comment

    def test_comment_path_matches_finding_file(self) -> None:
        from grippy.github_review import build_review_comment

        finding = _make_finding(file="src/auth.py")
        comment = build_review_comment(finding)
        assert comment["path"] == "src/auth.py"

    def test_comment_line_matches_finding_line_start(self) -> None:
        from grippy.github_review import build_review_comment

        finding = _make_finding(line_start=42)
        comment = build_review_comment(finding)
        assert comment["line"] == 42

    def test_comment_body_contains_severity_and_title(self) -> None:
        from grippy.github_review import build_review_comment

        finding = _make_finding(severity="CRITICAL", title="Buffer overflow")
        comment = build_review_comment(finding)
        assert "CRITICAL" in comment["body"]
        assert "Buffer overflow" in comment["body"]

    def test_comment_body_contains_fingerprint_marker(self) -> None:
        from grippy.github_review import build_review_comment

        finding = _make_finding()
        comment = build_review_comment(finding)
        assert f"<!-- grippy-finding-{finding.fingerprint} -->" in comment["body"]

    def test_comment_side_is_right(self) -> None:
        from grippy.github_review import build_review_comment

        finding = _make_finding()
        comment = build_review_comment(finding)
        assert comment["side"] == "RIGHT"


# --- format_summary_comment ---


class TestFormatSummary:
    """format_summary_comment builds the compact PR dashboard."""

    def test_contains_score_and_verdict(self) -> None:
        from grippy.github_review import format_summary_comment

        result = format_summary_comment(
            score=85,
            verdict="PASS",
            finding_count=3,
            new_count=2,
            persists_count=1,
            resolved_count=0,
            off_diff_findings=[],
            head_sha="abc123",
            pr_number=6,
        )
        assert "85/100" in result
        assert "PASS" in result

    def test_contains_delta_section(self) -> None:
        from grippy.github_review import format_summary_comment

        result = format_summary_comment(
            score=75,
            verdict="PASS",
            finding_count=4,
            new_count=2,
            persists_count=1,
            resolved_count=3,
            off_diff_findings=[],
            head_sha="abc123",
            pr_number=6,
        )
        assert "2 new" in result
        assert "1 persists" in result
        assert "3 resolved" in result

    def test_contains_summary_marker(self) -> None:
        from grippy.github_review import format_summary_comment

        result = format_summary_comment(
            score=80,
            verdict="PASS",
            finding_count=0,
            new_count=0,
            persists_count=0,
            resolved_count=0,
            off_diff_findings=[],
            head_sha="abc",
            pr_number=6,
        )
        assert "<!-- grippy-summary-6 -->" in result

    def test_off_diff_findings_in_collapsible(self) -> None:
        from grippy.github_review import format_summary_comment

        off_diff = [_make_finding(file="config.yaml", line_start=99)]
        result = format_summary_comment(
            score=70,
            verdict="PASS",
            finding_count=1,
            new_count=1,
            persists_count=0,
            resolved_count=0,
            off_diff_findings=off_diff,
            head_sha="abc",
            pr_number=6,
        )
        assert "<details>" in result
        assert "config.yaml" in result
        assert "Test finding" in result


# --- resolve_findings_against_prior ---


class TestResolveFindingsLogic:
    """resolve_findings_against_prior matches findings across rounds."""

    def test_exact_fingerprint_match_is_persists(self) -> None:
        from grippy.github_review import resolve_findings_against_prior

        f = _make_finding(file="src/auth.py", title="SQL injection", category="security")
        prior = [{"fingerprint": f.fingerprint, "title": "SQL injection", "node_id": "F:abc"}]
        result = resolve_findings_against_prior([f], prior)
        assert len(result.persisting) == 1
        assert result.persisting[0].finding.title == "SQL injection"
        assert result.persisting[0].prior_node_id == "F:abc"

    def test_no_match_is_new(self) -> None:
        from grippy.github_review import resolve_findings_against_prior

        prior = [{"fingerprint": "xxx999yyy888", "title": "Old issue", "node_id": "F:old"}]
        current = [_make_finding(title="Brand new issue")]
        result = resolve_findings_against_prior(current, prior)
        assert len(result.new) == 1
        assert result.new[0].title == "Brand new issue"

    def test_unmatched_prior_is_resolved(self) -> None:
        from grippy.github_review import resolve_findings_against_prior

        prior = [{"fingerprint": "xxx999yyy888", "title": "Fixed issue", "node_id": "F:fixed"}]
        current = [_make_finding(title="Different issue")]
        result = resolve_findings_against_prior(current, prior)
        assert len(result.resolved) == 1
        assert result.resolved[0]["node_id"] == "F:fixed"

    def test_empty_prior_all_new(self) -> None:
        from grippy.github_review import resolve_findings_against_prior

        current = [_make_finding(), _make_finding(title="Second")]
        result = resolve_findings_against_prior(current, [])
        assert len(result.new) == 2
        assert len(result.persisting) == 0
        assert len(result.resolved) == 0

    def test_empty_current_all_resolved(self) -> None:
        from grippy.github_review import resolve_findings_against_prior

        prior = [
            {"fingerprint": "aaa", "title": "Issue 1", "node_id": "F:1"},
            {"fingerprint": "bbb", "title": "Issue 2", "node_id": "F:2"},
        ]
        result = resolve_findings_against_prior([], prior)
        assert len(result.new) == 0
        assert len(result.resolved) == 2


# --- post_review ---


class TestPostReview:
    """post_review creates PR review with inline comments + summary."""

    @patch("grippy.github_review.Github")
    def test_creates_review_with_inline_comments(self, mock_github_cls: MagicMock) -> None:
        from grippy.github_review import post_review

        mock_pr = MagicMock()
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = mock_pr
        mock_pr.get_issue_comments.return_value = []
        # Same repo — not a fork
        mock_pr.head.repo.full_name = "org/repo"
        mock_pr.base.repo.full_name = "org/repo"

        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -8,3 +8,4 @@\n"
            " line\n"
            "+new_line\n"
            " line2\n"
        )
        findings = [_make_finding(file="src/app.py", line_start=9)]

        post_review(
            token="test-token",
            repo="org/repo",
            pr_number=1,
            findings=findings,
            prior_findings=[],
            head_sha="abc123",
            diff=diff,
            score=80,
            verdict="PASS",
        )

        mock_pr.create_review.assert_called_once()
        call_kwargs = mock_pr.create_review.call_args
        assert call_kwargs.kwargs["event"] == "COMMENT"
        assert len(call_kwargs.kwargs["comments"]) == 1

    @patch("grippy.github_review.Github")
    def test_off_diff_findings_in_summary_only(self, mock_github_cls: MagicMock) -> None:
        from grippy.github_review import post_review

        mock_pr = MagicMock()
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = mock_pr
        mock_pr.get_issue_comments.return_value = []
        mock_pr.head.repo.full_name = "org/repo"
        mock_pr.base.repo.full_name = "org/repo"

        diff = (
            "diff --git a/other.py b/other.py\n"
            "--- a/other.py\n+++ b/other.py\n"
            "@@ -1,2 +1,3 @@\n line\n+new\n line\n"
        )
        findings = [_make_finding(file="src/app.py", line_start=99)]  # not in diff

        post_review(
            token="test-token",
            repo="org/repo",
            pr_number=1,
            findings=findings,
            prior_findings=[],
            head_sha="abc123",
            diff=diff,
            score=70,
            verdict="PASS",
        )

        mock_pr.create_review.assert_not_called()
        mock_pr.create_issue_comment.assert_called_once()
        body = mock_pr.create_issue_comment.call_args[0][0]
        assert "Off-diff findings" in body

    @patch("grippy.github_review.Github")
    def test_summary_comment_upserted(self, mock_github_cls: MagicMock) -> None:
        from grippy.github_review import post_review

        mock_pr = MagicMock()
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = mock_pr

        existing_comment = MagicMock()
        existing_comment.body = "old stuff\n<!-- grippy-summary-1 -->"
        mock_pr.get_issue_comments.return_value = [existing_comment]

        post_review(
            token="test-token",
            repo="org/repo",
            pr_number=1,
            findings=[],
            prior_findings=[],
            head_sha="abc",
            diff="",
            score=90,
            verdict="PASS",
        )

        existing_comment.edit.assert_called_once()
        mock_pr.create_issue_comment.assert_not_called()

    @patch("grippy.github_review.Github")
    def test_fork_pr_skips_inline_comments(self, mock_github_cls: MagicMock) -> None:
        """Fork PRs put all findings in summary, no inline review."""
        from grippy.github_review import post_review

        mock_pr = MagicMock()
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = mock_pr
        mock_pr.get_issue_comments.return_value = []
        mock_pr.head.repo.full_name = "forker/repo"
        mock_pr.base.repo.full_name = "org/repo"

        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n+++ b/src/app.py\n"
            "@@ -8,3 +8,4 @@\n line\n+new\n line2\n"
        )
        findings = [_make_finding(file="src/app.py", line_start=9)]

        post_review(
            token="test-token",
            repo="org/repo",
            pr_number=1,
            findings=findings,
            prior_findings=[],
            head_sha="abc",
            diff=diff,
            score=75,
            verdict="PASS",
        )

        mock_pr.create_review.assert_not_called()
        mock_pr.create_issue_comment.assert_called_once()


# --- resolve_threads ---


class TestResolveThreads:
    """resolve_threads auto-resolves GitHub review threads for fixed findings."""

    @patch("grippy.github_review.subprocess.run")
    def test_calls_gh_api_graphql(self, mock_run: MagicMock) -> None:
        from grippy.github_review import resolve_threads

        mock_run.return_value = MagicMock(returncode=0, stdout="{}")
        resolve_threads(
            repo="org/repo",
            pr_number=1,
            thread_ids=["PRRT_abc123"],
        )
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "gh" in call_args.args[0] or "gh" in str(call_args)

    @patch("grippy.github_review.subprocess.run")
    def test_resolves_multiple_threads(self, mock_run: MagicMock) -> None:
        from grippy.github_review import resolve_threads

        mock_run.return_value = MagicMock(returncode=0, stdout="{}")
        resolve_threads(
            repo="org/repo",
            pr_number=1,
            thread_ids=["PRRT_1", "PRRT_2", "PRRT_3"],
        )
        assert mock_run.call_count == 3

    @patch("grippy.github_review.subprocess.run")
    def test_empty_thread_ids_no_calls(self, mock_run: MagicMock) -> None:
        from grippy.github_review import resolve_threads

        resolve_threads(repo="org/repo", pr_number=1, thread_ids=[])
        mock_run.assert_not_called()

    @patch("grippy.github_review.subprocess.run")
    def test_failed_resolution_logged_not_raised(self, mock_run: MagicMock) -> None:
        from grippy.github_review import resolve_threads

        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        count = resolve_threads(
            repo="org/repo",
            pr_number=1,
            thread_ids=["PRRT_bad"],
        )
        assert count == 0
