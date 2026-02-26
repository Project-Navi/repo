"""Grippy agent factory — builds Agno agents for each review mode."""

from __future__ import annotations

from pathlib import Path

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from grippy.prompts import load_identity, load_instructions
from grippy.schema import GrippyReview

DEFAULT_PROMPTS_DIR = Path(__file__).parent / "prompts_data"


def create_reviewer(
    *,
    model_id: str = "devstral-small-2-24b-instruct-2512",
    base_url: str = "http://localhost:1234/v1",
    api_key: str = "lm-studio",
    prompts_dir: Path | str = DEFAULT_PROMPTS_DIR,
    mode: str = "pr_review",
) -> Agent:
    """Create a Grippy review agent.

    Args:
        model_id: Model identifier at the inference endpoint.
        base_url: OpenAI-compatible API base URL.
        api_key: API key (LM Studio accepts any non-empty string).
        prompts_dir: Directory containing Grippy's 21 markdown prompt files.
        mode: Review mode — pr_review, security_audit, governance_check, surprise_audit.

    Returns:
        Configured Agno Agent with Grippy's prompt chain and structured output schema.
    """
    prompts_dir = Path(prompts_dir)

    return Agent(
        name="grippy",
        model=OpenAILike(
            id=model_id,
            api_key=api_key,
            base_url=base_url,
        ),
        description=load_identity(prompts_dir),
        instructions=load_instructions(prompts_dir, mode=mode),
        output_schema=GrippyReview,
        markdown=False,
    )


def format_pr_context(
    *,
    title: str,
    author: str,
    branch: str,
    description: str = "",
    diff: str,
    labels: str = "",
    file_context: str = "",
    governance_rules: str = "",
    learnings: str = "",
) -> str:
    """Format PR context as the user message, matching pr-review.md input format."""
    sections = []

    if governance_rules:
        sections.append(f"<governance_rules>\n{governance_rules}\n</governance_rules>")

    # Count diff stats
    additions = diff.count("\n+") - diff.count("\n+++")
    deletions = diff.count("\n-") - diff.count("\n---")
    changed_files = diff.count("diff --git")

    sections.append(
        f"<pr_metadata>\n"
        f"Title: {title}\n"
        f"Author: {author}\n"
        f"Branch: {branch}\n"
        f"Description: {description}\n"
        f"Labels: {labels}\n"
        f"Changed Files: {changed_files}\n"
        f"Additions: {additions}\n"
        f"Deletions: {deletions}\n"
        f"</pr_metadata>"
    )

    sections.append(f"<diff>\n{diff}\n</diff>")

    if file_context:
        sections.append(f"<file_context>\n{file_context}\n</file_context>")

    if learnings:
        sections.append(f"<learnings>\n{learnings}\n</learnings>")

    return "\n\n".join(sections)
