# Grippy PR UX Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Grippy's noisy issue comments with inline PR review comments, graph-powered finding resolution, and Agno Knowledge-backed persistence.

**Architecture:** Two-layer comment system (summary dashboard + inline review comments via GitHub PR Review API). Finding lifecycle tracked across rounds using deterministic fingerprints + vector similarity via Agno Knowledge/LanceDb. GrippyStore migrated from raw LanceDB to Agno's Knowledge class.

**Tech Stack:** Agno (Knowledge, LanceDb, OpenAIEmbedder, SqliteDb), PyGithub (create_review, get_reviews), GitHub GraphQL (resolveReviewThread via `gh api graphql`), Pydantic, pytest

**Design Doc:** `docs/plans/2026-02-26-grippy-pr-ux-design.md`

---

### Task 1: Finding Fingerprint

Add a deterministic fingerprint to Finding for cross-round matching.

**Files:**
- Modify: `src/grippy/schema.py`
- Test: `tests/test_grippy_schema.py`

**Step 1: Write the failing test**

Add to `tests/test_grippy_schema.py`:

```python
class TestFindingFingerprint:
    """Finding.fingerprint is a deterministic hash for cross-round matching."""

    def test_fingerprint_is_deterministic(self) -> None:
        """Same file + category + title → same fingerprint."""
        f1 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="security",
            file="src/auth.py", line_start=10, line_end=20,
            title="SQL injection risk", description="desc", suggestion="fix",
            evidence="ev", grippy_note="note",
        )
        f2 = Finding(
            id="F-002", severity="MEDIUM", confidence=70, category="security",
            file="src/auth.py", line_start=50, line_end=60,
            title="SQL injection risk", description="different desc", suggestion="other",
            evidence="other ev", grippy_note="other note",
        )
        assert f1.fingerprint == f2.fingerprint

    def test_fingerprint_stable_across_line_changes(self) -> None:
        """Line numbers don't affect fingerprint."""
        f1 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="logic",
            file="app.py", line_start=10, line_end=20,
            title="Off by one", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        f2 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="logic",
            file="app.py", line_start=100, line_end=110,
            title="Off by one", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        assert f1.fingerprint == f2.fingerprint

    def test_fingerprint_differs_for_different_files(self) -> None:
        """Different file → different fingerprint."""
        f1 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="security",
            file="a.py", line_start=1, line_end=2,
            title="Same title", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        f2 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="security",
            file="b.py", line_start=1, line_end=2,
            title="Same title", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        assert f1.fingerprint != f2.fingerprint

    def test_fingerprint_differs_for_different_categories(self) -> None:
        """Different category → different fingerprint."""
        f1 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="security",
            file="a.py", line_start=1, line_end=2,
            title="Same title", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        f2 = Finding(
            id="F-001", severity="HIGH", confidence=90, category="logic",
            file="a.py", line_start=1, line_end=2,
            title="Same title", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        assert f1.fingerprint != f2.fingerprint

    def test_fingerprint_is_12_char_hex(self) -> None:
        """Fingerprint is a 12-character hex string."""
        f = Finding(
            id="F-001", severity="HIGH", confidence=90, category="security",
            file="a.py", line_start=1, line_end=2,
            title="Title", description="d", suggestion="s",
            evidence="e", grippy_note="n",
        )
        assert len(f.fingerprint) == 12
        assert all(c in "0123456789abcdef" for c in f.fingerprint)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_schema.py::TestFindingFingerprint -v`
Expected: FAIL — `AttributeError: 'Finding' object has no attribute 'fingerprint'`

**Step 3: Write minimal implementation**

In `src/grippy/schema.py`, add to `Finding`:

```python
import hashlib

class Finding(BaseModel):
    # ... existing fields ...

    @property
    def fingerprint(self) -> str:
        """Deterministic 12-char hex hash for cross-round matching.

        Based on file + category + normalized title. Stable across line
        number shifts, severity changes, and description edits.
        """
        raw = f"{self.file}:{self.category.value}:{self.title.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_schema.py::TestFindingFingerprint -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/grippy/schema.py tests/test_grippy_schema.py
git commit -m "feat: add Finding.fingerprint for cross-round matching"
```

---

### Task 2: Graph Extensions — New Edge Types + Finding Properties

Add `RESOLVES`, `PERSISTS_AS` edge types and `fingerprint`/`status`/`thread_id` to FINDING nodes.

**Files:**
- Modify: `src/grippy/graph.py`
- Test: `tests/test_grippy_graph.py`

**Step 1: Write the failing test**

Add to `tests/test_grippy_graph.py`:

```python
class TestGraphExtensions:
    """New edge types and finding properties for resolution tracking."""

    def test_resolves_edge_type_exists(self) -> None:
        assert EdgeType.RESOLVES == "RESOLVES"

    def test_persists_as_edge_type_exists(self) -> None:
        assert EdgeType.PERSISTS_AS == "PERSISTS_AS"

    def test_finding_nodes_have_fingerprint(self, sample_review: GrippyReview) -> None:
        """review_to_graph includes fingerprint in FINDING node properties."""
        graph = review_to_graph(sample_review)
        finding_nodes = [n for n in graph.nodes if n.type == NodeType.FINDING]
        assert len(finding_nodes) > 0
        for node in finding_nodes:
            assert "fingerprint" in node.properties
            assert len(node.properties["fingerprint"]) == 12

    def test_finding_nodes_have_status(self, sample_review: GrippyReview) -> None:
        """review_to_graph sets status='open' on new FINDING nodes."""
        graph = review_to_graph(sample_review)
        finding_nodes = [n for n in graph.nodes if n.type == NodeType.FINDING]
        for node in finding_nodes:
            assert node.properties.get("status") == "open"
```

Note: The `sample_review` fixture should already exist in the test file (or conftest). If not, create a fixture that builds a minimal `GrippyReview` with at least one `Finding`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_graph.py::TestGraphExtensions -v`
Expected: FAIL — `AttributeError: type object 'EdgeType' has no attribute 'RESOLVES'`

**Step 3: Write minimal implementation**

In `src/grippy/graph.py`:

Add to `EdgeType` enum:
```python
class EdgeType(StrEnum):
    # ... existing ...
    RESOLVES = "RESOLVES"
    PERSISTS_AS = "PERSISTS_AS"
```

In `review_to_graph()`, modify the FINDING node creation to include fingerprint and status:
```python
        # FINDING node
        finding_nid = node_id(NodeType.FINDING, finding.file, finding.line_start, finding.title)
        _add(
            Node(
                id=finding_nid,
                type=NodeType.FINDING,
                label=finding.title,
                properties={
                    "severity": finding.severity.value,
                    "confidence": finding.confidence,
                    "category": finding.category.value,
                    "file": finding.file,
                    "line_start": finding.line_start,
                    "line_end": finding.line_end,
                    "evidence": finding.evidence,
                    "fingerprint": finding.fingerprint,
                    "status": "open",
                },
                edges=finding_edges,
                created_at=review.timestamp,
                source_review_id=review_nid,
            )
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_graph.py::TestGraphExtensions -v`
Expected: PASS (4 tests)

**Step 5: Run full graph test suite**

Run: `uv run pytest tests/test_grippy_graph.py -v`
Expected: All existing tests still pass

**Step 6: Commit**

```bash
git add src/grippy/graph.py tests/test_grippy_graph.py
git commit -m "feat: add RESOLVES/PERSISTS_AS edges, fingerprint+status on findings"
```

---

### Task 3: Embedder Factory

Replace `make_embed_fn()` with Agno `OpenAIEmbedder`-based factory.

**Files:**
- Create: `src/grippy/embedder.py`
- Create: `tests/test_grippy_embedder.py`

**Step 1: Write the failing test**

Create `tests/test_grippy_embedder.py`:

```python
"""Tests for Grippy embedder factory."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestCreateEmbedder:
    """create_embedder() returns the right Agno embedder for each transport."""

    def test_openai_transport_returns_openai_embedder(self) -> None:
        from grippy.embedder import create_embedder

        embedder = create_embedder(
            transport="openai",
            model="text-embedding-3-large",
            base_url="http://ignored",
        )
        from agno.knowledge.embedder.openai import OpenAIEmbedder

        assert isinstance(embedder, OpenAIEmbedder)
        assert embedder.id == "text-embedding-3-large"

    def test_local_transport_returns_embedder_with_base_url(self) -> None:
        from grippy.embedder import create_embedder

        embedder = create_embedder(
            transport="local",
            model="text-embedding-qwen3-embedding-4b",
            base_url="http://localhost:1234/v1",
        )
        from agno.knowledge.embedder.openai import OpenAIEmbedder

        assert isinstance(embedder, OpenAIEmbedder)
        assert embedder.id == "text-embedding-qwen3-embedding-4b"

    def test_local_transport_uses_lm_studio_api_key(self) -> None:
        from grippy.embedder import create_embedder

        embedder = create_embedder(
            transport="local",
            model="test-model",
            base_url="http://localhost:1234/v1",
        )
        assert embedder.api_key == "lm-studio"

    def test_openai_transport_does_not_set_base_url(self) -> None:
        """OpenAI transport uses default OpenAI base URL (not overridden)."""
        from grippy.embedder import create_embedder

        embedder = create_embedder(
            transport="openai",
            model="text-embedding-3-large",
            base_url="http://should-be-ignored",
        )
        # OpenAIEmbedder default base_url is None or the OpenAI default
        # The key assertion: we did NOT pass our custom base_url
        assert embedder.base_url is None or "openai.com" in str(embedder.base_url)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grippy.embedder'`

**Step 3: Write minimal implementation**

Create `src/grippy/embedder.py`:

```python
"""Embedder factory — selects Agno embedder based on transport mode."""

from __future__ import annotations

from agno.knowledge.embedder.openai import OpenAIEmbedder


def create_embedder(
    transport: str,
    model: str,
    base_url: str,
) -> OpenAIEmbedder:
    """Create an Agno embedder based on the resolved transport.

    Args:
        transport: "openai" or "local".
        model: Embedding model ID (e.g. "text-embedding-3-large").
        base_url: API base URL (used only for local transport).

    Returns:
        Configured OpenAIEmbedder instance.
    """
    if transport == "openai":
        return OpenAIEmbedder(id=model)
    return OpenAIEmbedder(id=model, base_url=base_url, api_key="lm-studio")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_embedder.py -v`
Expected: PASS (4 tests)

Note: If `OpenAIEmbedder` doesn't have a `base_url` param, check the Agno docs and adjust. The import path may also need verification — it could be `agno.embedder.openai` instead of `agno.knowledge.embedder.openai`.

**Step 5: Commit**

```bash
git add src/grippy/embedder.py tests/test_grippy_embedder.py
git commit -m "feat: add embedder factory — Agno OpenAIEmbedder per transport"
```

---

### Task 4: Diff Parser

Parse unified diff to determine which lines are addressable for inline review comments.

**Files:**
- Create: `src/grippy/github_review.py` (start with just the parser)
- Create: `tests/test_grippy_github_review.py`

**Step 1: Write the failing test**

Create `tests/test_grippy_github_review.py`:

```python
"""Tests for Grippy GitHub Review API integration."""

from __future__ import annotations

import pytest


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
        # Lines 10 (context), 11 (added), 12 (context), 13 (added) are addressable
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
        # Context lines (1, 2) are addressable, but deleted line is not
        assert "x.py" in result
        lines = result["x.py"]
        # Right-side lines 1 and 2 are in the hunk
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
        # All right-side lines in the hunk: 10, 11, 12 (new), 13, 14
        assert 10 in result["f.py"]
        assert 12 in result["f.py"]  # the added line
        assert 14 in result["f.py"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_grippy_github_review.py::TestParseDiffLines -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'grippy.github_review'`

**Step 3: Write minimal implementation**

Create `src/grippy/github_review.py`:

```python
"""GitHub PR Review API integration — inline comments, resolution, summaries."""

from __future__ import annotations

import re


def parse_diff_lines(diff_text: str) -> dict[str, set[int]]:
    """Parse unified diff to extract addressable RIGHT-side line numbers.

    GitHub's PR Review API only allows comments on lines that appear in
    the diff hunk. This function returns a mapping of file paths to the
    set of right-side (new file) line numbers that are addressable.

    Args:
        diff_text: Complete unified diff text from GitHub API.

    Returns:
        Dict mapping file paths to sets of addressable line numbers.
    """
    if not diff_text.strip():
        return {}

    result: dict[str, set[int]] = {}
    current_file: str | None = None
    right_line = 0

    for line in diff_text.splitlines():
        # Track current file from diff headers
        file_match = re.match(r"^diff --git a/.+ b/(.+)$", line)
        if file_match:
            current_file = file_match.group(1)
            if current_file not in result:
                result[current_file] = set()
            continue

        # Parse hunk header for right-side starting line
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk_match:
            right_line = int(hunk_match.group(1))
            continue

        if current_file is None:
            continue

        # Skip diff metadata lines
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("diff --git"):
            continue

        # Deleted lines: only advance left-side counter (not tracked)
        if line.startswith("-"):
            continue

        # Added lines: addressable on the right side
        if line.startswith("+"):
            result[current_file].add(right_line)
            right_line += 1
            continue

        # Context lines (space prefix or empty): addressable on right side
        if line.startswith(" ") or (not line.startswith("\\") and right_line > 0):
            result[current_file].add(right_line)
            right_line += 1

    return result
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_grippy_github_review.py::TestParseDiffLines -v`
Expected: PASS (7 tests)

**Step 5: Commit**

```bash
git add src/grippy/github_review.py tests/test_grippy_github_review.py
git commit -m "feat: add diff parser for addressable review comment lines"
```

---

### Task 5: Finding Classification + Inline Comment Builder

Classify findings as inline-eligible or off-diff, build PyGithub review comment dicts.

**Files:**
- Modify: `src/grippy/github_review.py`
- Modify: `tests/test_grippy_github_review.py`

**Step 1: Write the failing tests**

Add to `tests/test_grippy_github_review.py`:

```python
from grippy.schema import Finding, Severity, FindingCategory


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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_github_review.py::TestClassifyFindings tests/test_grippy_github_review.py::TestBuildReviewComment -v`
Expected: FAIL — `ImportError: cannot import name 'classify_findings' from 'grippy.github_review'`

**Step 3: Write minimal implementation**

Add to `src/grippy/github_review.py`:

```python
from grippy.schema import Finding


def classify_findings(
    findings: list[Finding],
    diff_lines: dict[str, set[int]],
) -> tuple[list[Finding], list[Finding]]:
    """Split findings into inline-eligible and off-diff.

    A finding is inline-eligible if its file appears in the diff and its
    line_start is within an addressable hunk line.

    Args:
        findings: List of findings from the review.
        diff_lines: Output of parse_diff_lines().

    Returns:
        (inline_findings, off_diff_findings)
    """
    inline: list[Finding] = []
    off_diff: list[Finding] = []
    for finding in findings:
        file_lines = diff_lines.get(finding.file)
        if file_lines and finding.line_start in file_lines:
            inline.append(finding)
        else:
            off_diff.append(finding)
    return inline, off_diff


_SEVERITY_EMOJI = {
    "CRITICAL": "\U0001f534",
    "HIGH": "\U0001f7e0",
    "MEDIUM": "\U0001f7e1",
    "LOW": "\U0001f535",
}


def build_review_comment(finding: Finding) -> dict[str, str | int]:
    """Build a PyGithub-compatible review comment dict for a finding.

    Args:
        finding: The finding to create a comment for.

    Returns:
        Dict with keys: path, body, line, side.
    """
    emoji = _SEVERITY_EMOJI.get(finding.severity.value, "\u26aa")
    body_lines = [
        f"#### {emoji} {finding.severity.value}: {finding.title}",
        f"Confidence: {finding.confidence}%",
        "",
        finding.description,
        "",
        f"**Suggestion:** {finding.suggestion}",
        "",
        f"*\u2014 {finding.grippy_note}*",
        "",
        f"<!-- grippy-finding-{finding.fingerprint} -->",
    ]
    return {
        "path": finding.file,
        "body": "\n".join(body_lines),
        "line": finding.line_start,
        "side": "RIGHT",
    }
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_github_review.py -v`
Expected: All tests PASS (7 diff parser + 6 classify + 6 build = 19 tests)

**Step 5: Commit**

```bash
git add src/grippy/github_review.py tests/test_grippy_github_review.py
git commit -m "feat: finding classification + inline comment builder"
```

---

### Task 6: Summary Dashboard Formatter

Format the compact summary issue comment with score, delta, and off-diff findings.

**Files:**
- Modify: `src/grippy/github_review.py`
- Modify: `tests/test_grippy_github_review.py`

**Step 1: Write the failing tests**

Add to `tests/test_grippy_github_review.py`:

```python
class TestFormatSummary:
    """format_summary_comment builds the compact PR dashboard."""

    def test_contains_score_and_verdict(self) -> None:
        from grippy.github_review import format_summary_comment

        result = format_summary_comment(
            score=85, verdict="PASS", finding_count=3,
            new_count=2, persists_count=1, resolved_count=0,
            off_diff_findings=[], head_sha="abc123", pr_number=6,
        )
        assert "85/100" in result
        assert "PASS" in result

    def test_contains_delta_section(self) -> None:
        from grippy.github_review import format_summary_comment

        result = format_summary_comment(
            score=75, verdict="PASS", finding_count=4,
            new_count=2, persists_count=1, resolved_count=3,
            off_diff_findings=[], head_sha="abc123", pr_number=6,
        )
        assert "2 new" in result
        assert "1 persists" in result
        assert "3 resolved" in result

    def test_contains_summary_marker(self) -> None:
        from grippy.github_review import format_summary_comment

        result = format_summary_comment(
            score=80, verdict="PASS", finding_count=0,
            new_count=0, persists_count=0, resolved_count=0,
            off_diff_findings=[], head_sha="abc", pr_number=6,
        )
        assert "<!-- grippy-summary-6 -->" in result

    def test_off_diff_findings_in_collapsible(self) -> None:
        from grippy.github_review import format_summary_comment

        off_diff = [_make_finding(file="config.yaml", line_start=99)]
        result = format_summary_comment(
            score=70, verdict="PASS", finding_count=1,
            new_count=1, persists_count=0, resolved_count=0,
            off_diff_findings=off_diff, head_sha="abc", pr_number=6,
        )
        assert "<details>" in result
        assert "config.yaml" in result
        assert "Test finding" in result
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_github_review.py::TestFormatSummary -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/grippy/github_review.py`:

```python
def format_summary_comment(
    *,
    score: int,
    verdict: str,
    finding_count: int,
    new_count: int,
    persists_count: int,
    resolved_count: int,
    off_diff_findings: list[Finding],
    head_sha: str,
    pr_number: int,
) -> str:
    """Format the compact summary dashboard as an issue comment.

    Args:
        score: Overall review score (0-100).
        verdict: PASS, FAIL, or PROVISIONAL.
        finding_count: Total findings this round.
        new_count: Findings not seen in prior round.
        persists_count: Findings that persist from prior round.
        resolved_count: Prior findings resolved this round.
        off_diff_findings: Findings outside diff hunks (shown inline here).
        head_sha: Commit SHA for this review.
        pr_number: PR number for marker scoping.

    Returns:
        Formatted markdown comment body.
    """
    emoji = {"\u2705": "PASS", "\u274c": "FAIL", "\u26a0\ufe0f": "PROVISIONAL"}
    status_emoji = next((k for k, v in emoji.items() if v == verdict), "\U0001f50d")

    lines: list[str] = []
    lines.append(f"## {status_emoji} Grippy Review \u2014 {verdict}")
    lines.append("")
    lines.append(f"**Score: {score}/100** | **Findings: {finding_count}**")
    lines.append("")

    # Delta section
    if new_count or persists_count or resolved_count:
        parts = []
        if new_count:
            parts.append(f"{new_count} new")
        if persists_count:
            parts.append(f"{persists_count} persists")
        if resolved_count:
            parts.append(f"\u2705 {resolved_count} resolved")
        lines.append(f"**Delta:** {' \u00b7 '.join(parts)}")
        lines.append("")

    # Off-diff findings
    if off_diff_findings:
        lines.append("<details>")
        lines.append(f"<summary>Off-diff findings ({len(off_diff_findings)})</summary>")
        lines.append("")
        for f in off_diff_findings:
            sev_emoji = _SEVERITY_EMOJI.get(f.severity.value, "\u26aa")
            lines.append(f"#### {sev_emoji} {f.severity.value}: {f.title}")
            lines.append(f"\U0001f4c1 `{f.file}:{f.line_start}`")
            lines.append("")
            lines.append(f.description)
            lines.append("")
            lines.append(f"**Suggestion:** {f.suggestion}")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append(f"<sub>Commit: {head_sha[:7]}</sub>")
    lines.append("")
    lines.append(f"<!-- grippy-summary-{pr_number} -->")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_github_review.py::TestFormatSummary -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/grippy/github_review.py tests/test_grippy_github_review.py
git commit -m "feat: summary dashboard formatter for PR comments"
```

---

### Task 7: GrippyStore — Agno Knowledge Migration

Migrate vector storage from raw LanceDB to Agno's Knowledge + LanceDb. Keep SQLite edges.

**Files:**
- Modify: `src/grippy/persistence.py`
- Modify: `tests/test_grippy_persistence.py`

**Step 1: Read current persistence tests**

Read `tests/test_grippy_persistence.py` to understand what the current tests expect, then adapt.

**Step 2: Write the failing tests for new resolution methods**

Add to `tests/test_grippy_persistence.py`:

```python
class TestResolutionQueries:
    """GrippyStore resolution matching for finding lifecycle."""

    def test_get_prior_findings_returns_open_findings(
        self, store: GrippyStore, sample_graph: ReviewGraph
    ) -> None:
        """get_prior_findings returns findings with status='open'."""
        store.store_review(sample_graph)
        findings = store.get_prior_findings(review_id=sample_graph.review_id)
        assert len(findings) > 0
        for f in findings:
            assert f["status"] == "open"

    def test_get_prior_findings_empty_when_no_reviews(self, store: GrippyStore) -> None:
        """No stored reviews → empty list."""
        findings = store.get_prior_findings(review_id="nonexistent")
        assert findings == []

    def test_update_finding_status(
        self, store: GrippyStore, sample_graph: ReviewGraph
    ) -> None:
        """update_finding_status changes a finding's status in node_meta."""
        store.store_review(sample_graph)
        finding_nodes = [n for n in sample_graph.nodes if n.type.value == "FINDING"]
        assert len(finding_nodes) > 0
        node_id = finding_nodes[0].id
        store.update_finding_status(node_id, "resolved")
        findings = store.get_prior_findings(review_id=sample_graph.review_id)
        statuses = {f["node_id"]: f["status"] for f in findings}
        # If there was only one finding, list might be empty (resolved ones excluded)
        # OR we need to query all findings regardless of status
        # Let's check the node directly
        cur = store._conn.cursor()
        cur.execute("SELECT properties FROM node_meta WHERE node_id = ?", (node_id,))
        import json
        props = json.loads(cur.fetchone()["properties"])
        assert props["status"] == "resolved"
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_persistence.py::TestResolutionQueries -v`
Expected: FAIL — methods don't exist

**Step 4: Modify GrippyStore implementation**

Modify `src/grippy/persistence.py`:

Key changes:
1. Replace `embed_fn: EmbedFn` param with `embedder` (Agno Embedder instance)
2. Replace raw `lancedb.connect()` with Agno `Knowledge(vector_db=LanceDb(...))`
3. Add `get_prior_findings()` and `update_finding_status()` methods
4. Keep all SQLite edge logic unchanged

The exact implementation depends on verifying the Agno `Knowledge` API during implementation. The core pattern:

```python
from agno.knowledge.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb, SearchType

class GrippyStore:
    def __init__(self, *, graph_db_path, lance_dir, embedder):
        self._knowledge = Knowledge(
            vector_db=LanceDb(
                uri=str(lance_dir),
                table_name="findings",
                search_type=SearchType.hybrid,
                embedder=embedder,
            ),
        )
        # SQLite init unchanged
        ...

    def get_prior_findings(self, review_id: str) -> list[dict[str, Any]]:
        """Get open findings from a specific review."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT node_id, label, properties FROM node_meta "
            "WHERE node_type = ? AND review_id = ?",
            ("FINDING", review_id),
        )
        results = []
        for row in cur.fetchall():
            props = json.loads(row["properties"])
            if props.get("status") == "open":
                props["node_id"] = row["node_id"]
                props["title"] = row["label"]
                results.append(props)
        return results

    def update_finding_status(self, node_id: str, status: str) -> None:
        """Update a finding's status in node_meta properties."""
        cur = self._conn.cursor()
        cur.execute("SELECT properties FROM node_meta WHERE node_id = ?", (node_id,))
        row = cur.fetchone()
        if row:
            props = json.loads(row["properties"])
            props["status"] = status
            cur.execute(
                "UPDATE node_meta SET properties = ? WHERE node_id = ?",
                (json.dumps(props), node_id),
            )
            self._conn.commit()
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_persistence.py -v`
Expected: All tests PASS (existing + 3 new)

**Step 6: Run full test suite**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: All tests pass, no regressions

**Step 7: Commit**

```bash
git add src/grippy/persistence.py tests/test_grippy_persistence.py
git commit -m "feat: migrate GrippyStore to Agno Knowledge + resolution queries"
```

---

### Task 8: Finding Resolution Engine

Core resolution logic — match current findings against prior round using fingerprints + vector similarity.

**Files:**
- Modify: `src/grippy/github_review.py`
- Modify: `tests/test_grippy_github_review.py`

**Step 1: Write the failing tests**

Add to `tests/test_grippy_github_review.py`:

```python
class TestResolveFindingsLogic:
    """resolve_findings_against_prior matches findings across rounds."""

    def test_exact_fingerprint_match_is_persists(self) -> None:
        from grippy.github_review import resolve_findings_against_prior

        prior = [{"fingerprint": "aaa111bbb222", "title": "SQL injection", "node_id": "F:abc"}]
        current = [_make_finding(file="src/auth.py", title="SQL injection", category="security")]
        result = resolve_findings_against_prior(current, prior)
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_github_review.py::TestResolveFindingsLogic -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/grippy/github_review.py`:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersistingFinding:
    """A finding that persists from a prior round."""
    finding: Finding
    prior_node_id: str


@dataclass
class ResolutionResult:
    """Result of resolving current findings against prior round."""
    new: list[Finding] = field(default_factory=list)
    persisting: list[PersistingFinding] = field(default_factory=list)
    resolved: list[dict[str, Any]] = field(default_factory=list)


def resolve_findings_against_prior(
    current: list[Finding],
    prior: list[dict[str, Any]],
) -> ResolutionResult:
    """Match current findings against prior round using fingerprints.

    Resolution rules:
    - Exact fingerprint match → PERSISTS
    - No match in current for a prior finding → RESOLVED
    - No match in prior for a current finding → NEW

    Args:
        current: Findings from the current review round.
        prior: Prior findings as dicts with 'fingerprint', 'title', 'node_id'.

    Returns:
        ResolutionResult with new, persisting, and resolved findings.
    """
    result = ResolutionResult()
    prior_by_fp = {p["fingerprint"]: p for p in prior}
    matched_prior_fps: set[str] = set()

    for finding in current:
        fp = finding.fingerprint
        if fp in prior_by_fp:
            result.persisting.append(
                PersistingFinding(finding=finding, prior_node_id=prior_by_fp[fp]["node_id"])
            )
            matched_prior_fps.add(fp)
        else:
            result.new.append(finding)

    # Prior findings not matched by any current finding → RESOLVED
    for prior_finding in prior:
        if prior_finding["fingerprint"] not in matched_prior_fps:
            result.resolved.append(prior_finding)

    return result
```

Note: Vector similarity fallback is a v1.1 enhancement. For v1, fingerprint matching is sufficient and deterministic. The vector search path can be added later using `GrippyStore.search_nodes()`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_github_review.py::TestResolveFindingsLogic -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add src/grippy/github_review.py tests/test_grippy_github_review.py
git commit -m "feat: finding resolution engine — fingerprint matching across rounds"
```

---

### Task 9: post_review() — Main Review Posting Function

Wire everything together: classify findings, post inline review + summary, store thread IDs.

**Files:**
- Modify: `src/grippy/github_review.py`
- Modify: `tests/test_grippy_github_review.py`

**Step 1: Write the failing tests**

Add to `tests/test_grippy_github_review.py`:

```python
from unittest.mock import MagicMock, patch


class TestPostReview:
    """post_review creates PR review with inline comments + summary."""

    @patch("grippy.github_review.Github")
    def test_creates_review_with_inline_comments(self, mock_github_cls: MagicMock) -> None:
        from grippy.github_review import post_review

        mock_pr = MagicMock()
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = mock_pr
        mock_pr.get_issue_comments.return_value = []

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
            token="test-token", repo="org/repo", pr_number=1,
            findings=findings, prior_findings=[], head_sha="abc123",
            diff=diff, score=80, verdict="PASS",
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

        diff = "diff --git a/other.py b/other.py\n--- a/other.py\n+++ b/other.py\n@@ -1,2 +1,3 @@\n line\n+new\n line\n"
        findings = [_make_finding(file="src/app.py", line_start=99)]  # not in diff

        post_review(
            token="test-token", repo="org/repo", pr_number=1,
            findings=findings, prior_findings=[], head_sha="abc123",
            diff=diff, score=70, verdict="PASS",
        )

        # No inline review created when all findings are off-diff
        mock_pr.create_review.assert_not_called()
        # But summary comment IS posted
        mock_pr.create_issue_comment.assert_called_once()
        body = mock_pr.create_issue_comment.call_args[0][0]
        assert "Off-diff findings" in body

    @patch("grippy.github_review.Github")
    def test_summary_comment_upserted(self, mock_github_cls: MagicMock) -> None:
        from grippy.github_review import post_review

        mock_pr = MagicMock()
        mock_github_cls.return_value.get_repo.return_value.get_pull.return_value = mock_pr

        # Existing summary comment
        existing_comment = MagicMock()
        existing_comment.body = "old stuff\n<!-- grippy-summary-1 -->"
        mock_pr.get_issue_comments.return_value = [existing_comment]

        post_review(
            token="test-token", repo="org/repo", pr_number=1,
            findings=[], prior_findings=[], head_sha="abc",
            diff="", score=90, verdict="PASS",
        )

        existing_comment.edit.assert_called_once()
        mock_pr.create_issue_comment.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_github_review.py::TestPostReview -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/grippy/github_review.py`:

```python
from github import Github


def post_review(
    *,
    token: str,
    repo: str,
    pr_number: int,
    findings: list[Finding],
    prior_findings: list[dict[str, Any]],
    head_sha: str,
    diff: str,
    score: int,
    verdict: str,
) -> None:
    """Post Grippy review as inline comments + summary dashboard.

    Args:
        token: GitHub API token.
        repo: Repository full name (owner/repo).
        pr_number: Pull request number.
        findings: Current round's findings.
        prior_findings: Prior round's findings (from GrippyStore).
        head_sha: Current commit SHA.
        diff: Full PR diff text.
        score: Overall review score.
        verdict: PASS, FAIL, or PROVISIONAL.
    """
    gh = Github(token)
    repository = gh.get_repo(repo)
    pr = repository.get_pull(pr_number)

    # Resolve findings against prior round
    resolution = resolve_findings_against_prior(findings, prior_findings)

    # Parse diff and classify
    diff_lines = parse_diff_lines(diff)
    inline, off_diff = classify_findings(findings, diff_lines)

    # Post inline review comments (batched at 25)
    if inline:
        comments = [build_review_comment(f) for f in inline]
        for i in range(0, len(comments), 25):
            batch = comments[i : i + 25]
            pr.create_review(
                body="" if i > 0 else None,
                event="COMMENT",
                comments=batch,
            )

    # Build and post/upsert summary comment
    summary = format_summary_comment(
        score=score,
        verdict=verdict,
        finding_count=len(findings),
        new_count=len(resolution.new),
        persists_count=len(resolution.persisting),
        resolved_count=len(resolution.resolved),
        off_diff_findings=off_diff,
        head_sha=head_sha,
        pr_number=pr_number,
    )

    # Upsert: edit existing summary or create new
    marker = f"<!-- grippy-summary-{pr_number} -->"
    for comment in pr.get_issue_comments():
        if marker in comment.body:
            comment.edit(summary)
            return

    pr.create_issue_comment(summary)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_github_review.py::TestPostReview -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add src/grippy/github_review.py tests/test_grippy_github_review.py
git commit -m "feat: post_review — inline comments + summary dashboard upsert"
```

---

### Task 10: GraphQL Thread Resolution

Auto-resolve inline threads for fixed findings via `gh api graphql`.

**Files:**
- Modify: `src/grippy/github_review.py`
- Modify: `tests/test_grippy_github_review.py`

**Step 1: Write the failing tests**

```python
import subprocess


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
        # Should not raise — resolution failure is non-fatal
        count = resolve_threads(
            repo="org/repo",
            pr_number=1,
            thread_ids=["PRRT_bad"],
        )
        assert count == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_github_review.py::TestResolveThreads -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Add to `src/grippy/github_review.py`:

```python
import subprocess


def resolve_threads(
    *,
    repo: str,
    pr_number: int,
    thread_ids: list[str],
) -> int:
    """Auto-resolve GitHub review threads via GraphQL.

    Uses ``gh api graphql`` subprocess for authentication simplicity.

    Args:
        repo: Repository full name (owner/repo).
        pr_number: Pull request number (for logging).
        thread_ids: List of GitHub review thread node IDs (PRRT_...).

    Returns:
        Number of threads successfully resolved.
    """
    resolved = 0
    for thread_id in thread_ids:
        mutation = (
            "mutation { resolveReviewThread(input: "
            f'{{threadId: "{thread_id}"}}'
            ") { thread { id isResolved } } }"
        )
        try:
            result = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={mutation}"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if result.returncode == 0:
                resolved += 1
            else:
                print(f"::warning::Failed to resolve thread {thread_id}: {result.stderr}")
        except Exception as exc:
            print(f"::warning::Exception resolving thread {thread_id}: {exc}")
    return resolved
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_github_review.py::TestResolveThreads -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add src/grippy/github_review.py tests/test_grippy_github_review.py
git commit -m "feat: GraphQL thread resolution via gh api graphql"
```

---

### Task 11: Wire Into main() + Transport Error UX

Rewire `review.py:main()` to use new review system and handle transport errors.

**Files:**
- Modify: `src/grippy/review.py`
- Modify: `tests/test_grippy_review.py`

**Step 1: Write the failing tests**

Add to `tests/test_grippy_review.py`:

```python
class TestMainReviewIntegration:
    """main() uses new post_review and create_embedder."""

    @patch("grippy.review.post_review")
    @patch("grippy.review.run_review")
    @patch("grippy.review.fetch_pr_diff")
    @patch("grippy.review.load_pr_event")
    def test_main_calls_post_review(
        self, mock_load, mock_diff, mock_run, mock_post,
        tmp_path, monkeypatch,
    ) -> None:
        """main() should call post_review instead of post_comment."""
        # Setup env
        event_file = tmp_path / "event.json"
        event_file.write_text('{"pull_request": {"number": 1, "title": "test", "user": {"login": "dev"}, "head": {"ref": "feat", "sha": "abc123"}, "base": {"ref": "main"}}, "repository": {"full_name": "org/repo"}}')
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GRIPPY_TRANSPORT", "local")
        monkeypatch.setattr("grippy.review.__file__", str(tmp_path / "fake" / "grippy" / "review.py"))

        mock_load.return_value = {
            "pr_number": 1, "repo": "org/repo", "title": "test",
            "author": "dev", "head_ref": "feat", "head_sha": "abc123",
            "base_ref": "main", "description": "",
        }
        mock_diff.return_value = "diff --git a/x.py b/x.py\n"

        from grippy.schema import GrippyReview
        mock_review = MagicMock(spec=GrippyReview)
        mock_review.score.overall = 80
        mock_review.verdict.status.value = "PASS"
        mock_review.verdict.merge_blocking = False
        mock_review.findings = []
        mock_review.model = "test"
        mock_review.meta.review_duration_ms = 100
        mock_review.scope.files_reviewed = 1
        mock_review.scope.files_in_diff = 1
        mock_review.pr.complexity_tier.value = "STANDARD"
        mock_review.personality.opening_catchphrase = "Hi"
        mock_review.personality.closing_line = "Bye"
        mock_run.return_value = mock_review

        from grippy.review import main
        main()

        mock_post.assert_called_once()


class TestTransportErrorUX:
    """Invalid GRIPPY_TRANSPORT posts error comment and exits."""

    @patch("grippy.review.post_comment")
    @patch("grippy.review.load_pr_event")
    def test_invalid_transport_posts_error_comment(
        self, mock_load, mock_post_comment, tmp_path, monkeypatch,
    ) -> None:
        event_file = tmp_path / "event.json"
        event_file.write_text('{"pull_request": {"number": 1, "title": "t", "user": {"login": "d"}, "head": {"ref": "f", "sha": "a"}, "base": {"ref": "m"}}, "repository": {"full_name": "o/r"}}')
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GRIPPY_TRANSPORT", "invalid-transport")
        monkeypatch.setattr("grippy.review.__file__", str(tmp_path / "fake" / "grippy" / "review.py"))

        mock_load.return_value = {
            "pr_number": 1, "repo": "o/r", "title": "t",
            "author": "d", "head_ref": "f", "head_sha": "a",
            "base_ref": "m", "description": "",
        }

        from grippy.review import main
        with pytest.raises(SystemExit):
            main()

        # Should have posted an error comment
        mock_post_comment.assert_called_once()
        body = mock_post_comment.call_args[0][3]  # 4th positional arg is body
        assert "CONFIG ERROR" in body
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_grippy_review.py::TestMainReviewIntegration tests/test_grippy_review.py::TestTransportErrorUX -v`
Expected: FAIL

**Step 3: Modify main() in review.py**

Key changes to `src/grippy/review.py:main()`:

1. Import `post_review` from `github_review` and `create_embedder` from `embedder`
2. Wrap `create_reviewer()` in `try/except ValueError` for transport errors
3. After successful review, call `post_review()` instead of `post_comment()`
4. Pass `diff` and `prior_findings` to `post_review()`

The exact implementation depends on the Task 7 `GrippyStore` API. The general flow:

```python
# In main(), after review succeeds:

# Get prior findings for resolution
try:
    prior_findings = store.get_prior_findings(review_id=prior_review_id)
except Exception:
    prior_findings = []

# Post review with new system
from grippy.github_review import post_review
post_review(
    token=token, repo=pr_event["repo"], pr_number=pr_event["pr_number"],
    findings=review.findings, prior_findings=prior_findings,
    head_sha=pr_event["head_sha"], diff=diff,
    score=review.score.overall, verdict=review.verdict.status.value,
)
```

For transport error handling:
```python
try:
    agent = create_reviewer(...)
except ValueError as exc:
    error_body = (
        f"## \u274c Grippy Review \u2014 CONFIG ERROR\n\n"
        f"Invalid configuration: `{exc}`\n\n"
        f"Valid GRIPPY_TRANSPORT values: `openai`, `local`\n\n"
        f"<!-- grippy-error -->"
    )
    post_comment(token, pr_event["repo"], pr_event["pr_number"], error_body)
    sys.exit(1)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_grippy_review.py -v`
Expected: All tests PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 6: Lint + type check**

Run: `uv run ruff check src/grippy/ tests/ && uv run mypy src/grippy/`
Expected: Clean

**Step 7: Commit**

```bash
git add src/grippy/review.py tests/test_grippy_review.py
git commit -m "feat: wire post_review into main() + transport error UX"
```

---

### Task 12: Update Exports + Cleanup

Update `__init__.py`, remove dead code, final quality checks.

**Files:**
- Modify: `src/grippy/__init__.py`
- Modify: `src/grippy/review.py` (remove `make_embed_fn`, old `post_comment`, `format_review_comment`)
- Modify: `pyproject.toml` (verify extras)

**Step 1: Update __init__.py exports**

Add new public symbols:
```python
from grippy.embedder import create_embedder
from grippy.github_review import (
    build_review_comment,
    classify_findings,
    format_summary_comment,
    parse_diff_lines,
    post_review,
    resolve_findings_against_prior,
    resolve_threads,
)
```

Update `__all__` accordingly.

**Step 2: Remove dead code from review.py**

Remove:
- `make_embed_fn()` — replaced by `create_embedder()`
- `COMMENT_MARKER_PREFIX`, `COMMENT_MARKER_SUFFIX`, `_make_comment_marker()` — replaced by summary marker
- `format_review_comment()` — replaced by `build_review_comment()` + `format_summary_comment()`
- Old `post_comment()` — replaced by `post_review()` (keep a simplified version for error comments only)

**Step 3: Verify pyproject.toml extras**

Check that `agno[openai]` is in `grippy` extras and `lancedb` is in `grippy-persistence`. The Agno Knowledge class may need additional deps — verify during implementation.

**Step 4: Run full quality checks**

```bash
uv run ruff format src/grippy/ tests/
uv run ruff check src/grippy/ tests/
uv run mypy src/grippy/
uv run pytest tests/ -v
```

Expected: All green

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: update exports, remove dead code, verify extras"
```

---

### Task 13: Integration Smoke Test

Verify everything works end-to-end on the actual PR.

**Step 1: Push to trigger Grippy**

```bash
git push origin dogfood/fix-spec-drift
```

**Step 2: Monitor CI**

```bash
gh pr checks 6 --watch
```

**Step 3: Verify comment behavior**

Check PR #6:
- Summary dashboard comment exists (with marker)
- Inline review comments on diff lines (if findings)
- No duplicate summary comments
- Off-diff findings in collapsible section

```bash
gh pr view 6 --comments
```

**Step 4: If issues, fix and re-push**

Follow the same pattern from prior rounds: fix, test, commit, push.

---

## Verification Checklist

```bash
# Tests
uv run pytest tests/ -v

# Lint
uv run ruff check src/grippy/ tests/

# Format
uv run ruff format --check src/grippy/ tests/

# Type check
uv run mypy src/grippy/

# Security
uv run bandit -r src/grippy/ -ll
```
