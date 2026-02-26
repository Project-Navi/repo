"""Grippy CI review entry point — reads PR event, runs agent, posts comment.

Usage (GitHub Actions):
    python -m grippy.review

Environment variables:
    GITHUB_TOKEN            — GitHub API token for fetching diff and posting comments
    GITHUB_EVENT_PATH       — path to PR event JSON (set by GitHub Actions)
    OPENAI_API_KEY          — OpenAI API key (or unset for local endpoints)
    GRIPPY_BASE_URL         — API endpoint (default: http://localhost:1234/v1)
    GRIPPY_MODEL_ID         — model identifier (default: devstral-small-2-24b-instruct-2512)
    GRIPPY_EMBEDDING_MODEL  — embedding model (default: text-embedding-qwen3-embedding-4b)
    GRIPPY_TRANSPORT        — "openai" or "local" (default: infer from OPENAI_API_KEY)
    GRIPPY_API_KEY          — API key for non-OpenAI endpoints (embedding auth fallback)
    GRIPPY_DATA_DIR         — persistent directory for graph DB + LanceDB
    GRIPPY_TIMEOUT          — seconds before review is killed (0 = no timeout)
    GITHUB_REPOSITORY       — owner/repo (set by GitHub Actions, fallback)
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from grippy.agent import create_reviewer, format_pr_context
from grippy.graph import review_to_graph
from grippy.persistence import GrippyStore
from grippy.retry import ReviewParseError, run_review
from grippy.schema import GrippyReview

# Marker embedded in every Grippy comment — used for upsert (C2 fix)
COMMENT_MARKER = "<!-- grippy-review -->"

# Max diff size sent to the LLM — ~200K chars ≈ 50K tokens (H2 fix)
MAX_DIFF_CHARS = 200_000


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


def truncate_diff(diff: str, max_chars: int = MAX_DIFF_CHARS) -> str:
    """Truncate diff at file boundaries if it exceeds max_chars.

    Splits on 'diff --git' markers and includes complete files until the
    budget is exhausted. Appends a truncation warning.
    """
    if len(diff) <= max_chars:
        return diff

    # Split into per-file blocks
    parts = diff.split("diff --git ")
    # First element is empty or preamble
    preamble = parts[0]
    file_blocks = [f"diff --git {p}" for p in parts[1:]]

    kept: list[str] = []
    total = len(preamble)
    for block in file_blocks:
        if total + len(block) > max_chars and kept:
            break
        kept.append(block)
        total += len(block)

    truncated_count = len(file_blocks) - len(kept)
    result = preamble + "".join(kept)
    if truncated_count > 0:
        result += f"\n\n... {truncated_count} file(s) truncated (diff exceeded {max_chars} chars) (truncated)"
    return result


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
        from urllib.parse import urlparse

        url = f"{base_url}/embeddings"
        headers: dict[str, str] = {}
        # Only send OPENAI_API_KEY to OpenAI hosts; use GRIPPY_API_KEY for others
        parsed = urlparse(base_url)
        is_openai_host = parsed.hostname == "api.openai.com"
        openai_key = os.environ.get("OPENAI_API_KEY") or ""
        grippy_key = os.environ.get("GRIPPY_API_KEY") or ""
        if is_openai_host and openai_key:
            api_key = openai_key
        elif grippy_key:
            api_key = grippy_key
        elif not is_openai_host and openai_key:
            # Don't leak OPENAI_API_KEY to non-OpenAI endpoints
            print(
                f"::warning::OPENAI_API_KEY present but embedding endpoint is {base_url}. "
                f"Set GRIPPY_API_KEY for non-OpenAI endpoints. Sending unauthenticated."
            )
            api_key = ""
        else:
            api_key = ""
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        response = requests.post(
            url,
            json={"model": model, "input": texts},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in data]

    return embed


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

    # Hidden marker for upsert detection
    lines.append("")
    lines.append(COMMENT_MARKER)

    return "\n".join(lines)


def fetch_pr_diff(token: str, repo: str, pr_number: int) -> str:
    """Fetch complete PR diff via GitHub API raw diff endpoint.

    Uses Accept: application/vnd.github.v3.diff to get the full unified
    diff in a single request — no pagination issues (C1 fix).
    """
    import requests

    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.diff",
    }
    response = requests.get(url, headers=headers, timeout=60)
    response.raise_for_status()
    return response.text


def post_comment(token: str, repo: str, pr_number: int, body: str) -> None:
    """Post or update a Grippy review comment on a PR.

    Searches for an existing comment containing COMMENT_MARKER and edits
    it instead of creating a duplicate (C2 fix).
    """
    from github import Github

    gh = Github(token)
    repository = gh.get_repo(repo)
    pr = repository.get_pull(pr_number)

    # Look for existing Grippy comment to edit
    for comment in pr.get_issue_comments():
        if COMMENT_MARKER in comment.body:
            comment.edit(body)
            return

    # No existing comment — create new
    pr.create_issue_comment(body)


def _with_timeout(fn: Callable[[], Any], *, timeout_seconds: int) -> Any:
    """Run *fn* with a SIGALRM timeout (Linux only).  0 = no timeout."""
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
    transport = os.environ.get("GRIPPY_TRANSPORT") or None
    mode = os.environ.get("GRIPPY_MODE", "pr_review")
    timeout_seconds = int(os.environ.get("GRIPPY_TIMEOUT", "300"))

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

    # 2. Fetch diff (M2: graceful 403 handling for fork PRs)
    print("Fetching PR diff...")
    try:
        diff = fetch_pr_diff(token, pr_event["repo"], pr_event["pr_number"])
    except Exception as exc:
        print(f"::error::Failed to fetch PR diff: {exc}")
        if "403" in str(exc):
            print(
                "::error::The token may lack access to this fork's diff. "
                "Ensure the workflow has `pull_request_target` trigger or "
                "the token has read access to the fork."
            )
        try:
            failure_body = (
                f"## \u274c Grippy Review \u2014 DIFF FETCH ERROR\n\n"
                f"Could not fetch PR diff: `{exc}`\n\n"
                f"{COMMENT_MARKER}"
            )
            post_comment(token, pr_event["repo"], pr_event["pr_number"], failure_body)
        except Exception:
            pass  # Don't mask the original error
        sys.exit(1)
    file_count = diff.count("diff --git")
    print(f"  {file_count} files, {len(diff)} chars")

    # H2: cap diff size to avoid overflowing LLM context
    diff = truncate_diff(diff)
    if len(diff) < file_count:
        print(f"  Diff truncated to {MAX_DIFF_CHARS} chars")

    # 3. Create agent and format context
    data_dir_str = os.environ.get("GRIPPY_DATA_DIR", "./grippy-data")
    embedding_model = os.environ.get("GRIPPY_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-4b")
    data_dir = Path(data_dir_str)
    data_dir.mkdir(parents=True, exist_ok=True)

    agent = create_reviewer(
        model_id=model_id,
        base_url=base_url,
        transport=transport,
        mode=mode,
        db_path=data_dir / "grippy-session.db",
        session_id=f"pr-{pr_event['pr_number']}",
    )

    user_message = format_pr_context(
        title=pr_event["title"],
        author=pr_event["author"],
        branch=f"{pr_event['head_ref']} → {pr_event['base_ref']}",
        description=pr_event["description"],
        diff=diff,
    )

    # 4. Run review with retry + validation (replaces agent.run + parse_review_response)
    print(f"Running review (model={model_id}, endpoint={base_url})...")
    try:
        review = _with_timeout(
            lambda: run_review(agent, user_message),
            timeout_seconds=timeout_seconds,
        )
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
    except TimeoutError as exc:
        print(f"::error::Grippy review timed out: {exc}")
        try:
            failure_body = (
                f"## \u274c Grippy Review \u2014 TIMEOUT\n\n"
                f"Review timed out after {timeout_seconds}s.\n\n"
                f"Model: {model_id} at {base_url}\n\n"
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

    print(f"  Score: {review.score.overall}/100 — {review.verdict.status.value}")
    print(f"  Findings: {len(review.findings)}")

    # 5. Build graph and persist (non-fatal — review still gets posted on failure)
    print("Persisting review graph...")
    try:
        embed_fn = make_embed_fn(base_url, embedding_model)
        graph = review_to_graph(review)
        store = GrippyStore(
            graph_db_path=data_dir / "grippy-graph.db",
            lance_dir=data_dir / "lance",
            embed_fn=embed_fn,
        )
        store.store_review(graph)
        print(f"  Graph: {len(graph.nodes)} nodes persisted")
    except Exception as exc:
        print(f"::warning::Graph persistence failed: {exc}")

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
