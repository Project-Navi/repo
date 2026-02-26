"""Grippy CI review entry point — reads PR event, runs agent, posts comment.

Usage (GitHub Actions):
    python -m grippy.review

Environment variables:
    GITHUB_TOKEN        — GitHub API token for fetching diff and posting comments
    GITHUB_EVENT_PATH   — path to PR event JSON (set by GitHub Actions)
    GRIPPY_BASE_URL     — LM Studio / OpenAI-compatible endpoint
    GRIPPY_MODEL_ID     — model identifier at the endpoint
    GITHUB_REPOSITORY   — owner/repo (set by GitHub Actions, fallback)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from grippy.schema import GrippyReview


def load_pr_event(event_path: Path) -> dict[str, Any]:
    """Parse GitHub Actions pull_request event payload.

    Returns:
        Dict with keys: pr_number, repo, title, author, head_ref, base_ref, description.

    Raises:
        FileNotFoundError: If event_path doesn't exist.
        KeyError: If event JSON lacks pull_request key.
    """
    data = json.loads(event_path.read_text(encoding="utf-8"))
    pr = data["pull_request"]
    return {
        "pr_number": pr["number"],
        "repo": data["repository"]["full_name"],
        "title": pr["title"],
        "author": pr["user"]["login"],
        "head_ref": pr["head"]["ref"],
        "base_ref": pr["base"]["ref"],
        "description": pr.get("body") or "",
    }


def parse_review_response(content: Any) -> GrippyReview:
    """Parse agent response content into GrippyReview.

    Handles three response shapes from Agno:
    - GrippyReview instance (structured output worked)
    - dict (parsed JSON object)
    - str (raw JSON string)

    Raises:
        ValueError: If content can't be parsed or validated.
    """
    if isinstance(content, GrippyReview):
        return content
    if isinstance(content, dict):
        try:
            return GrippyReview.model_validate(content)
        except Exception as exc:
            msg = f"Failed to validate review dict: {exc}"
            raise ValueError(msg) from exc
    if isinstance(content, str):
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            msg = f"Failed to parse review response as JSON: {exc}"
            raise ValueError(msg) from exc
        try:
            return GrippyReview.model_validate(data)
        except Exception as exc:
            msg = f"Failed to validate review JSON: {exc}"
            raise ValueError(msg) from exc
    msg = f"Unexpected response type: {type(content).__name__}"
    raise ValueError(msg)


def format_review_comment(review: GrippyReview) -> str:
    """Format GrippyReview as a markdown PR comment."""
    lines: list[str] = []

    # Header with verdict
    status = review.verdict.status.value
    emoji = {"PASS": "✅", "FAIL": "❌", "PROVISIONAL": "⚠️"}.get(status, "🔍")
    lines.append(f"## {emoji} Grippy Review — {status}")
    lines.append("")

    # Personality opener
    lines.append(f"> {review.personality.opening_catchphrase}")
    lines.append("")

    # Score
    lines.append(f"**Score: {review.score.overall}/100**")
    bd = review.score.breakdown
    lines.append(
        f"Security {bd.security} · Logic {bd.logic} · Governance {bd.governance}"
        f" · Reliability {bd.reliability} · Observability {bd.observability}"
    )
    lines.append("")

    # Verdict summary
    lines.append(f"**Verdict:** {review.verdict.summary}")
    if review.verdict.merge_blocking:
        lines.append("**⛔ This review blocks merge.**")
    lines.append("")

    # Findings
    if review.findings:
        lines.append(f"### Findings ({len(review.findings)})")
        lines.append("")
        for finding in review.findings:
            sev = finding.severity.value
            sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵"}.get(sev, "⚪")
            lines.append(f"#### {sev_emoji} {sev}: {finding.title}")
            lines.append(f"📁 `{finding.file}:{finding.line_start}`")
            lines.append(f"Confidence: {finding.confidence}%")
            lines.append("")
            lines.append(finding.description)
            lines.append("")
            lines.append(f"**Suggestion:** {finding.suggestion}")
            if finding.governance_rule_id:
                lines.append(f"**Rule:** {finding.governance_rule_id}")
            lines.append("")
            lines.append(f"*— {finding.grippy_note}*")
            lines.append("")
    else:
        lines.append("### No findings")
        lines.append("")

    # Escalations
    if review.escalations:
        lines.append(f"### Escalations ({len(review.escalations)})")
        lines.append("")
        for esc in review.escalations:
            blocking_tag = " **[BLOCKING]**" if esc.blocking else ""
            lines.append(f"- **{esc.id}** ({esc.severity}){blocking_tag}: {esc.summary}")
            lines.append(f"  Target: {esc.recommended_target.value}")
        lines.append("")

    # Personality closer
    lines.append("---")
    lines.append(f"*{review.personality.closing_line}*")
    lines.append("")

    # Meta footer
    lines.append(
        f"<sub>Model: {review.model} · "
        f"Duration: {review.meta.review_duration_ms}ms · "
        f"Files: {review.scope.files_reviewed}/{review.scope.files_in_diff} · "
        f"Complexity: {review.pr.complexity_tier.value}</sub>"
    )

    return "\n".join(lines)


def fetch_pr_diff(token: str, repo: str, pr_number: int) -> str:
    """Fetch PR diff via PyGithub.

    Returns:
        The unified diff as a string.
    """
    from github import Github  # type: ignore[import-not-found]

    gh = Github(token)
    repository = gh.get_repo(repo)
    pr = repository.get_pull(pr_number)

    # Get diff by fetching the compare URL
    comparison = repository.compare(pr.base.sha, pr.head.sha)
    # Build diff from file patches
    parts: list[str] = []
    for f in comparison.files:
        if f.patch:
            parts.append(f"diff --git a/{f.filename} b/{f.filename}")
            parts.append(f"--- a/{f.filename}")
            parts.append(f"+++ b/{f.filename}")
            parts.append(f.patch)
    return "\n".join(parts)


def post_comment(token: str, repo: str, pr_number: int, body: str) -> None:
    """Post a comment on a PR via PyGithub."""
    from github import Github

    gh = Github(token)
    repository = gh.get_repo(repo)
    pr = repository.get_pull(pr_number)
    pr.create_issue_comment(body)


def main() -> None:
    """CI entry point — reads env, runs review, posts comment."""
    # Load .dev.vars if present (local dev)
    dev_vars_path = Path(__file__).resolve().parent.parent.parent / ".dev.vars"
    if dev_vars_path.is_file():
        for line in dev_vars_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    # Required env
    token = os.environ.get("GITHUB_TOKEN", "")
    event_path_str = os.environ.get("GITHUB_EVENT_PATH", "")
    base_url = os.environ.get("GRIPPY_BASE_URL", "http://localhost:1234/v1")
    model_id = os.environ.get("GRIPPY_MODEL_ID", "devstral-small-2-24b-instruct-2512")

    if not token:
        print("::error::GITHUB_TOKEN not set")
        sys.exit(1)
    if not event_path_str:
        print("::error::GITHUB_EVENT_PATH not set")
        sys.exit(1)

    event_path = Path(event_path_str)
    if not event_path.is_file():
        print(f"::error::Event file not found: {event_path}")
        sys.exit(1)

    # 1. Parse event
    print("=== Grippy Review ===")
    pr_event = load_pr_event(event_path)
    print(
        f"PR #{pr_event['pr_number']}: {pr_event['title']} "
        f"({pr_event['head_ref']} → {pr_event['base_ref']})"
    )

    # 2. Fetch diff
    print("Fetching PR diff...")
    diff = fetch_pr_diff(token, pr_event["repo"], pr_event["pr_number"])
    print(f"  {diff.count('diff --git')} files, {len(diff)} chars")

    # 3. Create agent and format context
    from grippy.agent import create_reviewer, format_pr_context

    agent = create_reviewer(
        model_id=model_id,
        base_url=base_url,
        mode="pr_review",
    )

    user_message = format_pr_context(
        title=pr_event["title"],
        author=pr_event["author"],
        branch=f"{pr_event['head_ref']} → {pr_event['base_ref']}",
        description=pr_event["description"],
        diff=diff,
    )

    # 4. Run review
    print(f"Running review (model={model_id}, endpoint={base_url})...")
    run_output = agent.run(user_message)

    # 5. Parse response
    review = parse_review_response(run_output.content)
    print(f"  Score: {review.score.overall}/100 — {review.verdict.status.value}")
    print(f"  Findings: {len(review.findings)}")

    # 6. Format and post comment
    comment = format_review_comment(review)
    print("Posting review comment...")
    post_comment(token, pr_event["repo"], pr_event["pr_number"], comment)
    print("  Done.")

    # 7. Set outputs for GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"score={review.score.overall}\n")
            f.write(f"verdict={review.verdict.status.value}\n")
            f.write(f"findings-count={len(review.findings)}\n")
            f.write(f"merge-blocking={str(review.verdict.merge_blocking).lower()}\n")

    # Exit non-zero if merge-blocking
    if review.verdict.merge_blocking:
        print(f"::warning::Review verdict: {review.verdict.status.value} (merge-blocking)")
        sys.exit(1)


if __name__ == "__main__":
    main()
