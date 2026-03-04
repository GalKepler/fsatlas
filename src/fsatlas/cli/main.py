"""fsatlas CLI — extract morphometric measures using arbitrary atlases."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from ..atlases.registry import AtlasRegistry
from ..core.environment import FreeSurferEnv
from ..core.pipeline import run_extraction

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.version_option()
def cli() -> None:
    """fsatlas — Extract morphometric measures from FreeSurfer subjects using arbitrary atlases."""
    pass


@cli.command()
@click.option(
    "--subjects-dir", "-d",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="FreeSurfer SUBJECTS_DIR. Defaults to $SUBJECTS_DIR.",
)
@click.option(
    "--atlas", "-a",
    required=True,
    help="Atlas name from catalog (e.g. schaefer100-7, tian-s2) or path to .annot/.nii.gz",
)
@click.option(
    "--atlas-type", "-t",
    type=click.Choice(["surface", "volumetric", "auto"]),
    default="auto",
    help="Atlas type. Auto-detected for catalog atlases and by file extension for custom.",
)
@click.option(
    "--subjects", "-s",
    multiple=True,
    help="Subject IDs to process. If not provided, processes all subjects in SUBJECTS_DIR.",
)
@click.option(
    "--subjects-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a text file with one subject ID per line.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("fsatlas_output"),
    help="Output directory for TSV files.",
)
@click.option("--overwrite", is_flag=True, help="Overwrite existing transferred atlases and stats.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def extract(
    subjects_dir: Path | None,
    atlas: str,
    atlas_type: str,
    subjects: tuple[str, ...],
    subjects_file: Path | None,
    output_dir: Path,
    overwrite: bool,
    verbose: bool,
) -> None:
    """Extract morphometric measures for one atlas across subjects."""
    _setup_logging(verbose)

    # Detect FreeSurfer
    try:
        env = FreeSurferEnv.detect(subjects_dir)
    except EnvironmentError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(f"FreeSurfer {env.version} | SUBJECTS_DIR: {env.subjects_dir}")

    # Resolve atlas
    registry = AtlasRegistry()
    atlas_spec = _resolve_atlas(registry, atlas, atlas_type)

    # Download if needed (catalog atlas)
    if isinstance(atlas_spec, type(registry.get("desikan").__class__)):
        pass  # typing workaround
    if hasattr(atlas_spec, "is_downloaded") and not atlas_spec.builtin:
        if not atlas_spec.is_downloaded():
            console.print(f"Downloading atlas [bold]{atlas_spec.name}[/bold]...")
            registry.download(atlas_spec.name)

    # Resolve subjects
    subject_list = _resolve_subjects(env, subjects, subjects_file)
    if not subject_list:
        console.print("[red]No subjects found.[/red]")
        sys.exit(1)

    console.print(
        f"Atlas: [bold]{atlas_spec.name}[/bold] ({atlas_spec.type}) | "
        f"Subjects: {len(subject_list)}"
    )

    # Run pipeline
    output_paths = run_extraction(
        atlas=atlas_spec,
        subjects=subject_list,
        env=env,
        output_dir=output_dir,
        overwrite=overwrite,
    )

    # Report
    console.print("\n[green]Done![/green] Output files:")
    for kind, path in output_paths.items():
        console.print(f"  {kind}: {path}")


@cli.command("list-atlases")
def list_atlases() -> None:
    """List all available atlases in the catalog."""
    registry = AtlasRegistry()
    atlases = registry.list_atlases()

    table = Table(title="Available Atlases")
    table.add_column("Name", style="bold cyan")
    table.add_column("Type")
    table.add_column("Family")
    table.add_column("Description")
    table.add_column("Cached", justify="center")

    for a in atlases:
        cached = "✓" if a.is_downloaded() else "—"
        table.add_row(a.name, a.type, a.family, a.description, cached)

    console.print(table)


@cli.command()
@click.argument("atlas_name")
@click.option("--force", is_flag=True, help="Re-download even if cached.")
def download(atlas_name: str, force: bool) -> None:
    """Download an atlas from the catalog to local cache."""
    registry = AtlasRegistry()
    try:
        atlas = registry.download(atlas_name, force=force)
        console.print(f"[green]Atlas '{atlas.name}' ready at {atlas.cache_dir}[/green]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_atlas(registry: AtlasRegistry, atlas_arg: str, atlas_type: str):
    """Resolve an atlas argument to an AtlasSpec or CustomAtlasSpec."""
    # First try catalog lookup
    try:
        return registry.get(atlas_arg)
    except KeyError:
        pass

    # Treat as a file path
    path = Path(atlas_arg)
    if not path.exists():
        console.print(
            f"[red]'{atlas_arg}' is not a catalog atlas name nor an existing file.[/red]"
        )
        console.print("Use [bold]fsatlas list-atlases[/bold] to see available catalog atlases.")
        sys.exit(1)

    # Infer type
    if atlas_type == "auto":
        if path.suffix == ".annot":
            atlas_type = "surface"
        elif path.suffix in (".nii", ".gz"):
            atlas_type = "volumetric"
        else:
            console.print(
                f"[red]Cannot infer atlas type from extension '{path.suffix}'. "
                f"Use --atlas-type to specify.[/red]"
            )
            sys.exit(1)

    if atlas_type == "surface":
        # Expect user passed one annot; try to find the other hemisphere
        stem = path.stem
        parent = path.parent
        if stem.startswith("lh."):
            lh = path
            rh = parent / f"rh.{stem[3:]}.annot"
        elif stem.startswith("rh."):
            rh = path
            lh = parent / f"lh.{stem[3:]}.annot"
        else:
            console.print(
                "[red]Surface annot file must start with 'lh.' or 'rh.' "
                "so the other hemisphere can be found.[/red]"
            )
            sys.exit(1)

        return AtlasRegistry.from_custom_surface(lh, rh)
    else:
        return AtlasRegistry.from_custom_volumetric(path)


def _resolve_subjects(
    env: FreeSurferEnv,
    subjects_args: tuple[str, ...],
    subjects_file: Path | None,
) -> list[str]:
    """Build subject list from CLI args, file, or auto-discovery."""
    subject_list = list(subjects_args)

    if subjects_file:
        lines = subjects_file.read_text().splitlines()
        subject_list.extend(l.strip() for l in lines if l.strip() and not l.startswith("#"))

    if not subject_list:
        # Auto-discover
        subject_list = env.list_subjects()
        console.print(f"Auto-discovered {len(subject_list)} subjects in {env.subjects_dir}")

    return subject_list
