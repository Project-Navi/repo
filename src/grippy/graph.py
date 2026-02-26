"""Graph data model — typed nodes and directed edges for Grippy reviews.

Transforms flat GrippyReview output into a graph structure suitable for
persistence in SQLite (edges) and LanceDB (vectors). Designed to migrate
cleanly to SurrealDB: nodes become records, edges become graph relations.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from grippy.schema import GrippyReview


class EdgeType(StrEnum):
    VIOLATES = "VIOLATES"
    FOUND_IN = "FOUND_IN"
    FIXED_BY = "FIXED_BY"
    IS_A = "IS_A"
    PREREQUISITE_FOR = "PREREQUISITE_FOR"
    EXTRACTED_FROM = "EXTRACTED_FROM"
    TENDENCY = "TENDENCY"
    REVIEWED_BY = "REVIEWED_BY"


class NodeType(StrEnum):
    REVIEW = "REVIEW"
    FINDING = "FINDING"
    RULE = "RULE"
    PATTERN = "PATTERN"
    AUTHOR = "AUTHOR"
    FILE = "FILE"
    SUGGESTION = "SUGGESTION"


class Edge(BaseModel):
    type: EdgeType
    target_id: str
    target_type: NodeType
    metadata: dict[str, str | int | float | bool] = {}


class Node(BaseModel):
    id: str
    type: NodeType
    label: str
    properties: dict[str, Any] = {}
    edges: list[Edge] = []
    created_at: str
    source_review_id: str | None = None


class ReviewGraph(BaseModel):
    """Graph representation of a single review — nodes + edges."""

    review_id: str
    nodes: list[Node]
    timestamp: str


def node_id(node_type: NodeType, *parts: Any) -> str:
    """Deterministic node ID from type + content parts.

    Format: ``{TYPE}:{sha256_hex[:12]}``
    """
    raw = ":".join([node_type.value, *(str(p) for p in parts)])
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"{node_type.value}:{digest}"


def review_to_graph(review: GrippyReview) -> ReviewGraph:
    """Transform a flat GrippyReview into a graph of typed nodes and directed edges."""
    nodes: list[Node] = []
    seen_ids: set[str] = set()

    def _add(node: Node) -> None:
        if node.id not in seen_ids:
            nodes.append(node)
            seen_ids.add(node.id)

    # Review node
    review_nid = node_id(NodeType.REVIEW, review.timestamp, review.pr.title)
    review_node = Node(
        id=review_nid,
        type=NodeType.REVIEW,
        label=f"Review: {review.pr.title}",
        properties={
            "audit_type": review.audit_type,
            "overall_score": review.score.overall,
            "verdict": review.verdict.status.value,
            "model": review.model,
        },
        edges=[
            Edge(
                type=EdgeType.REVIEWED_BY,
                target_id=node_id(NodeType.AUTHOR, "agent", review.model),
                target_type=NodeType.AUTHOR,
            ),
        ],
        created_at=review.timestamp,
        source_review_id=None,
    )
    _add(review_node)

    # Author node (PR author)
    author_nid = node_id(NodeType.AUTHOR, review.pr.author)
    _add(
        Node(
            id=author_nid,
            type=NodeType.AUTHOR,
            label=review.pr.author,
            properties={"branch": review.pr.branch},
            created_at=review.timestamp,
            source_review_id=review_nid,
        )
    )

    # Process each finding
    for finding in review.findings:
        # FILE node (deduplicated by path)
        file_nid = node_id(NodeType.FILE, finding.file)
        _add(
            Node(
                id=file_nid,
                type=NodeType.FILE,
                label=finding.file,
                properties={},
                created_at=review.timestamp,
                source_review_id=review_nid,
            )
        )

        # SUGGESTION node
        suggestion_nid = node_id(
            NodeType.SUGGESTION, finding.file, finding.line_start, finding.suggestion
        )
        _add(
            Node(
                id=suggestion_nid,
                type=NodeType.SUGGESTION,
                label=finding.suggestion,
                properties={},
                created_at=review.timestamp,
                source_review_id=review_nid,
            )
        )

        # RULE node (if governance_rule_id present, deduplicated)
        finding_edges: list[Edge] = [
            Edge(type=EdgeType.FOUND_IN, target_id=file_nid, target_type=NodeType.FILE),
            Edge(type=EdgeType.FIXED_BY, target_id=suggestion_nid, target_type=NodeType.SUGGESTION),
        ]

        if finding.governance_rule_id:
            rule_nid = node_id(NodeType.RULE, finding.governance_rule_id)
            _add(
                Node(
                    id=rule_nid,
                    type=NodeType.RULE,
                    label=finding.governance_rule_id,
                    properties={},
                    created_at=review.timestamp,
                    source_review_id=review_nid,
                )
            )
            finding_edges.append(
                Edge(type=EdgeType.VIOLATES, target_id=rule_nid, target_type=NodeType.RULE)
            )

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
                },
                edges=finding_edges,
                created_at=review.timestamp,
                source_review_id=review_nid,
            )
        )

    return ReviewGraph(
        review_id=review_nid,
        nodes=nodes,
        timestamp=review.timestamp,
    )
