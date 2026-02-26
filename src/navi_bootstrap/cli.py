# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Project Navi

"""nboot CLI — render and apply template packs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from navi_bootstrap.diff import compute_diffs
from navi_bootstrap.engine import plan, render, render_to_files
from navi_bootstrap.hooks import run_hooks
from navi_bootstrap.init import inspect_project
from navi_bootstrap.manifest import ManifestError, load_manifest
from navi_bootstrap.resolve import ResolveError, resolve_action_shas
from navi_bootstrap.sanitize import sanitize_manifest, sanitize_spec
from navi_bootstrap.spec import SpecError, load_spec
from navi_bootstrap.validate import run_validations


@click.group()
@click.version_option()
def cli() -> None:
    """nboot — bootstrap projects to navi-os-grade posture."""


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", type=click.Path(exists=True, path_type=Path), default=None)
def validate(spec: Path, pack: Path | None) -> None:
    """Validate a spec (and optionally a pack manifest)."""
    try:
        load_spec(spec)
        click.echo(f"Spec valid: {spec}")
    except SpecError as e:
        raise click.ClickException(str(e)) from e

    if pack:
        try:
            load_manifest(pack / "manifest.yaml")
            click.echo(f"Manifest valid: {pack / 'manifest.yaml'}")
        except ManifestError as e:
            raise click.ClickException(str(e)) from e


@cli.command("render")
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--out", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-resolve", is_flag=True, default=False, help="Skip SHA resolution (offline)")
@click.option("--trust", is_flag=True, default=False, help="Execute hooks from manifest (unsafe)")
def render_cmd(
    spec: Path, pack: Path, out: Path | None, dry_run: bool, skip_resolve: bool, trust: bool
) -> None:
    """Render a template pack into a new project (greenfield)."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e)) from e
    spec_data = sanitize_spec(spec_data)

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e)) from e
    manifest = sanitize_manifest(manifest)

    output_dir = out or Path(spec_data["name"])

    # Stage 0: Resolve SHAs
    action_shas_config = manifest.get("action_shas", [])
    try:
        shas, versions = resolve_action_shas(action_shas_config, skip=skip_resolve or dry_run)
    except ResolveError as e:
        raise click.ClickException(str(e)) from e

    # Stage 2: Plan
    templates_dir = pack / "templates"
    render_plan = plan(manifest, spec_data, templates_dir)

    if dry_run:
        click.echo("Dry run — render plan:")
        for entry in render_plan.entries:
            mode_tag = f" [{entry.mode}]" if entry.mode != "create" else ""
            click.echo(f"  {entry.src} → {entry.dest}{mode_tag}")
        return

    # Stage 3: Render
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        written = render(
            render_plan,
            spec_data,
            templates_dir,
            output_dir,
            mode="greenfield",
            action_shas=shas,
            action_versions=versions,
        )
    except FileExistsError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Rendered {len(written)} files to {output_dir}")

    # Stage 5: Hooks
    hooks = manifest.get("hooks", [])
    if hooks:
        if trust:
            click.echo("Running hooks...")
            for r in run_hooks(hooks, output_dir):
                status = "OK" if r.success else "FAIL"
                click.echo(f"  [{status}] {r.command}")
        else:
            click.echo("Skipped hooks (manifest commands not trusted):")
            for h in hooks:
                click.echo(f"  {h}")
            click.echo("Pass --trust to execute.")


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--target", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-resolve", is_flag=True, default=False, help="Skip SHA resolution (offline)")
@click.option(
    "--trust", is_flag=True, default=False, help="Execute hooks/validations from manifest (unsafe)"
)
def apply(
    spec: Path, pack: Path, target: Path, dry_run: bool, skip_resolve: bool, trust: bool
) -> None:
    """Apply a template pack to an existing project."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e)) from e
    spec_data = sanitize_spec(spec_data)

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e)) from e
    manifest = sanitize_manifest(manifest)

    # Stage 0: Resolve SHAs
    action_shas_config = manifest.get("action_shas", [])
    try:
        shas, versions = resolve_action_shas(action_shas_config, skip=skip_resolve or dry_run)
    except ResolveError as e:
        raise click.ClickException(str(e)) from e

    # Stage 2: Plan
    templates_dir = pack / "templates"
    render_plan = plan(manifest, spec_data, templates_dir)

    if dry_run:
        click.echo("Dry run — render plan:")
        for entry in render_plan.entries:
            mode_tag = f" [{entry.mode}]" if entry.mode != "create" else ""
            click.echo(f"  {entry.src} → {entry.dest}{mode_tag}")
        return

    # Stage 3: Render
    written = render(
        render_plan,
        spec_data,
        templates_dir,
        target,
        mode="apply",
        action_shas=shas,
        action_versions=versions,
    )
    click.echo(f"Applied {len(written)} files to {target}")

    # Stage 4: Validate + Stage 5: Hooks
    validations = manifest.get("validation", [])
    hooks = manifest.get("hooks", [])

    if trust:
        if validations:
            click.echo("Running validations...")
            for r in run_validations(validations, target):
                if r.skipped:
                    status = "SKIP"
                elif r.passed:
                    status = "PASS"
                else:
                    status = "FAIL"
                click.echo(f"  [{status}] {r.description}")

        if hooks:
            click.echo("Running hooks...")
            for h in run_hooks(hooks, target):
                status = "OK" if h.success else "FAIL"
                click.echo(f"  [{status}] {h.command}")
    else:
        skipped: list[str] = []
        for v in validations:
            cmd = v.get("command")
            if cmd:
                skipped.append(cmd)
        skipped.extend(hooks)
        if skipped:
            click.echo("Skipped validations/hooks (manifest commands not trusted):")
            for s in skipped:
                click.echo(f"  {s}")
            click.echo("Pass --trust to execute.")


@cli.command("diff")
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--target", required=True, type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option("--skip-resolve", is_flag=True, default=False, help="Skip SHA resolution (offline)")
def diff_cmd(spec: Path, pack: Path, target: Path, skip_resolve: bool) -> None:
    """Preview what a pack would change without writing anything."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e)) from e
    spec_data = sanitize_spec(spec_data)

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e)) from e
    manifest = sanitize_manifest(manifest)

    # Stage 0: Resolve SHAs
    action_shas_config = manifest.get("action_shas", [])
    try:
        shas, versions = resolve_action_shas(action_shas_config, skip=skip_resolve)
    except ResolveError as e:
        raise click.ClickException(str(e)) from e

    # Stage 2: Plan
    templates_dir = pack / "templates"
    render_plan = plan(manifest, spec_data, templates_dir)

    # Stage 3: Render to memory (no filesystem writes)
    rendered_files = render_to_files(
        render_plan,
        spec_data,
        templates_dir,
        action_shas=shas,
        action_versions=versions,
    )

    # Compute diffs
    diffs = compute_diffs(rendered_files, target, pack_name=render_plan.pack_name)

    if not diffs:
        click.echo("No changes — target is up to date.")
        raise SystemExit(0)

    for d in diffs:
        label = "(new)" if d.is_new else "(changed)"
        click.echo(f"--- {d.dest} {label} ---")
        click.echo(d.diff_text)

    n = len(diffs)
    click.echo(f"\n{n} file{'s' if n != 1 else ''} would change.")
    raise SystemExit(1)


@cli.command()
@click.option(
    "--target",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=".",
    help="Project directory to inspect (default: current directory)",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for spec file (default: <target>/nboot-spec.json)",
)
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompts")
def init(target: Path, out: Path | None, yes: bool) -> None:
    """Generate a project spec by inspecting an existing project."""
    click.echo(f"Inspecting {target}...\n")

    spec = inspect_project(target)

    # Prompt for missing required fields
    if not spec.get("language"):
        if yes:
            raise click.ClickException(
                "Could not detect project language. Run without --yes to provide it interactively."
            )
        spec["language"] = click.prompt(
            "  Language", type=click.Choice(["python", "typescript", "go", "rust"])
        )

    if not spec.get("name"):
        if yes:
            raise click.ClickException(
                "Could not detect project name. Run without --yes to provide it interactively."
            )
        spec["name"] = click.prompt("  Project name")

    # Sanitize before display and write — spec values from pyproject.toml
    # may contain Jinja2 delimiters, homoglyphs, or zero-width chars.
    spec = sanitize_spec(spec)

    # Display detected spec
    _display_spec(spec)

    # Confirm
    if not yes:
        if not click.confirm("\nWrite spec?", default=True):
            click.echo("Aborted.")
            return

    # Write
    out_path = out or (target / "nboot-spec.json")
    out_path.write_text(json.dumps(spec, indent=2) + "\n")
    click.echo(f"\nWrote {out_path}")


def _display_spec(spec: dict[str, Any]) -> None:
    """Display a summary of the detected spec."""
    click.echo(f"  Name:        {spec.get('name', '(unknown)')}")
    click.echo(f"  Language:    {spec.get('language', '(unknown)')}")
    if v := spec.get("version"):
        click.echo(f"  Version:     {v}")
    if pv := spec.get("python_version"):
        click.echo(f"  Python:      {pv}")
    if s := spec.get("structure"):
        if src := s.get("src_dir"):
            click.echo(f"  Source:      {src}")
        if td := s.get("test_dir"):
            click.echo(f"  Tests:       {td}")
    if gh := spec.get("github"):
        click.echo(f"  GitHub:      {gh.get('org', '?')}/{gh.get('repo', '?')}")
    if f := spec.get("features"):
        active = [k for k, v in f.items() if v]
        if active:
            click.echo(f"  Features:    {', '.join(active)}")
    if r := spec.get("recon"):
        tools = r.get("existing_tools", {})
        found = [k for k, v in tools.items() if v]
        if found:
            click.echo(f"  Tools:       {', '.join(found)}")
        if tc := r.get("test_count"):
            click.echo(f"  Test count:  {tc}")
