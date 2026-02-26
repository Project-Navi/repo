# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""Stage 0: Resolve action SHAs via gh api."""

from __future__ import annotations

import json
import subprocess
from typing import Any


class ResolveError(Exception):
    """Raised when SHA resolution fails."""


def _gh_api(endpoint: str) -> dict[str, Any]:
    """Call gh api and return parsed JSON."""
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ResolveError(f"gh api failed for {endpoint}: {result.stderr}")
    return json.loads(result.stdout)


def _resolve_one(repo: str, tag: str) -> str:
    """Resolve a single action tag to its commit SHA, handling annotated tags."""
    endpoint = f"repos/{repo}/git/refs/tags/{tag}"
    data = _gh_api(endpoint)
    obj = data["object"]

    # Annotated tag — dereference to get the commit
    if obj["type"] == "tag":
        deref_endpoint = f"repos/{repo}/git/tags/{obj['sha']}"
        tag_data = _gh_api(deref_endpoint)
        return tag_data["object"]["sha"]

    return obj["sha"]


def resolve_action_shas(
    action_shas: list[dict[str, str]], *, skip: bool = False
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve all action SHAs from manifest config.

    Returns (shas, versions) dicts keyed by action name.
    If skip=True, fills SHAs with placeholder strings (for dry-run/offline).
    """
    shas: dict[str, str] = {}
    versions: dict[str, str] = {}

    for entry in action_shas:
        name = entry["name"]
        versions[name] = entry["tag"]

        if skip:
            shas[name] = "SKIP_SHA_RESOLUTION"
        else:
            try:
                shas[name] = _resolve_one(entry["repo"], entry["tag"])
            except (ResolveError, KeyError, json.JSONDecodeError, FileNotFoundError) as e:
                raise ResolveError(
                    f"Failed to resolve SHA for {entry['repo']}@{entry['tag']}: {e}"
                ) from e

    return shas, versions
