"""nboot CLI — render and apply template packs."""

from __future__ import annotations

from pathlib import Path

import click

from navi_bootstrap.engine import plan, render
from navi_bootstrap.hooks import run_hooks
from navi_bootstrap.manifest import ManifestError, load_manifest
from navi_bootstrap.resolve import ResolveError, resolve_action_shas
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
def render_cmd(spec: Path, pack: Path, out: Path | None, dry_run: bool, skip_resolve: bool) -> None:
    """Render a template pack into a new project (greenfield)."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e)) from e

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e)) from e

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
        click.echo("Running hooks...")
        for r in run_hooks(hooks, output_dir):
            status = "OK" if r.success else "FAIL"
            click.echo(f"  [{status}] {r.command}")


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--pack", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--target", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--skip-resolve", is_flag=True, default=False, help="Skip SHA resolution (offline)")
def apply(spec: Path, pack: Path, target: Path, dry_run: bool, skip_resolve: bool) -> None:
    """Apply a template pack to an existing project."""
    try:
        spec_data = load_spec(spec)
    except SpecError as e:
        raise click.ClickException(str(e)) from e

    try:
        manifest = load_manifest(pack / "manifest.yaml")
    except ManifestError as e:
        raise click.ClickException(str(e)) from e

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

    # Stage 4: Validate
    validations = manifest.get("validation", [])
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

    # Stage 5: Hooks
    hooks = manifest.get("hooks", [])
    if hooks:
        click.echo("Running hooks...")
        for h in run_hooks(hooks, target):
            status = "OK" if h.success else "FAIL"
            click.echo(f"  [{status}] {h.command}")
