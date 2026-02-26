"""Stages 2 (Plan) and 3 (Render) of the nboot engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jinja2


@dataclass
class RenderEntry:
    """A single file to render."""

    src: str  # template filename (relative to templates dir)
    dest: str  # output path (relative to output dir)
    mode: str = "create"  # "create" or "append"
    extra_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RenderPlan:
    """The full list of files to render."""

    entries: list[RenderEntry] = field(default_factory=list)
    pack_name: str = ""


@dataclass
class RenderedFile:
    """A rendered file — content in memory, not yet written to disk.

    This dataclass is the boundary between the pure render stage (stateless,
    side-effect-free) and the write stage (filesystem). Designed so that
    stages 0-3 can run in a Cloudflare Worker or similar edge runtime that
    returns rendered content without touching a filesystem.
    """

    dest: str  # relative output path
    content: str  # rendered template content
    mode: str = "create"  # "create" or "append"


def _resolve_dotpath(obj: Any, path: str) -> Any:
    """Resolve a dotpath like 'spec.features.ci' against a nested dict."""
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _eval_condition(condition_expr: str, spec: dict[str, Any]) -> bool:
    """Evaluate a dotpath condition expression against spec context.

    Supports negation with '!' prefix: "!spec.recon.existing_tools.ruff"
    evaluates to True when the dotpath is falsy.
    """
    negate = condition_expr.startswith("!")
    path = condition_expr.lstrip("!")
    context = {"spec": spec}
    value = _resolve_dotpath(context, path)
    result = bool(value)
    return not result if negate else result


def _render_dest_path(dest_template: str, context: dict[str, Any]) -> str:
    """Render Jinja2 expressions in destination paths."""
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    tmpl = env.from_string(dest_template)
    return tmpl.render(**context)


def plan(
    manifest: dict[str, Any],
    spec: dict[str, Any],
    templates_dir: Path,
) -> RenderPlan:
    """Stage 2: Build a render plan from manifest + spec."""
    render_plan = RenderPlan(pack_name=manifest.get("name", "unknown"))
    conditions = manifest.get("conditions", {})
    loops = manifest.get("loops", {})

    for template_entry in manifest.get("templates", []):
        src = template_entry["src"]
        dest = template_entry["dest"]
        mode = template_entry.get("mode", "create")

        # Check conditions
        if src in conditions:
            if not _eval_condition(conditions[src], spec):
                continue

        # Check if this is a looped template
        if src in loops:
            loop_config = loops[src]
            over_path = loop_config["over"]
            as_name = loop_config["as"]
            items = _resolve_dotpath({"spec": spec}, over_path)
            if items is None:
                items = []
            for item in items:
                context = {"spec": spec, as_name: item}
                resolved_dest = _render_dest_path(dest, context)
                render_plan.entries.append(
                    RenderEntry(
                        src=src,
                        dest=resolved_dest,
                        mode=mode,
                        extra_context={as_name: item},
                    )
                )
        else:
            render_plan.entries.append(RenderEntry(src=src, dest=dest, mode=mode))

    return render_plan


def render_to_files(
    render_plan: RenderPlan,
    spec: dict[str, Any],
    templates_dir: Path,
    *,
    action_shas: dict[str, str] | None = None,
    action_versions: dict[str, str] | None = None,
) -> list[RenderedFile]:
    """Stage 3 (pure): Render templates to memory. No filesystem side effects.

    Returns a list of RenderedFile with (dest, content, mode). The caller
    decides what to do with them — write to disk, return via HTTP, etc.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )

    context: dict[str, Any] = {
        "spec": spec,
        "action_shas": action_shas or {},
        "action_versions": action_versions or {},
    }

    results: list[RenderedFile] = []

    for entry in render_plan.entries:
        template = env.get_template(entry.src)
        render_context = {**context, **entry.extra_context}
        rendered = template.render(**render_context)
        results.append(RenderedFile(dest=entry.dest, content=rendered, mode=entry.mode))

    return results


# --- Filesystem write layer (Stage 3b) ---

# Marker block pattern
_MARKER_START = "# --- nboot: {pack_name} ---"
_MARKER_END = "# --- end nboot: {pack_name} ---"
_MARKER_RE = re.compile(
    r"# --- nboot: (?P<pack>\S+) ---\n.*?# --- end nboot: (?P=pack) ---\n?",
    re.DOTALL,
)


def _write_append(output_path: Path, rendered: str, pack_name: str) -> None:
    """Append rendered content with marker blocks, replacing existing markers."""
    marker_start = _MARKER_START.format(pack_name=pack_name)
    marker_end = _MARKER_END.format(pack_name=pack_name)
    block = f"{marker_start}\n{rendered}{marker_end}\n"

    if output_path.exists():
        existing = output_path.read_text()
        # Replace existing marker block if present
        if marker_start in existing:
            new_content = _MARKER_RE.sub("", existing, count=1)
            if new_content and not new_content.endswith("\n"):
                new_content += "\n"
            output_path.write_text(new_content + block)
        else:
            if existing and not existing.endswith("\n"):
                existing += "\n"
            output_path.write_text(existing + block)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(block)


def write_rendered(
    rendered_files: list[RenderedFile],
    output_dir: Path,
    pack_name: str,
    *,
    mode: str = "apply",
) -> list[Path]:
    """Write rendered files to disk. Handles append markers and greenfield checks.

    mode: "greenfield" (fail if non-append files exist) or "apply" (create/append).
    Returns list of written file paths.
    """
    written: list[Path] = []

    for rf in rendered_files:
        output_path = output_dir / rf.dest

        if rf.mode == "append":
            _write_append(output_path, rf.content, pack_name)
        else:
            if mode == "greenfield" and output_path.exists():
                raise FileExistsError(f"File already exists (greenfield mode): {output_path}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rf.content)

        written.append(output_path)

    return written


def render(
    render_plan: RenderPlan,
    spec: dict[str, Any],
    templates_dir: Path,
    output_dir: Path,
    *,
    mode: str = "apply",
    action_shas: dict[str, str] | None = None,
    action_versions: dict[str, str] | None = None,
) -> list[Path]:
    """Stage 3 (convenience): Render templates and write to disk.

    Combines render_to_files() + write_rendered() for the common case.
    For edge/stateless usage, call render_to_files() directly.
    """
    rendered_files = render_to_files(
        render_plan,
        spec,
        templates_dir,
        action_shas=action_shas,
        action_versions=action_versions,
    )
    return write_rendered(rendered_files, output_dir, render_plan.pack_name, mode=mode)
