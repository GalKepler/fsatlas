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

# Supported atlas format IDs
_FORMAT_CHOICES = ["annot", "nifti", "dlabel_gii", "gca", "auto"]


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
    help="Atlas name from catalog (e.g. schaefer100-7) or path to atlas file.",
)
@click.option(
    "--format", "-F", "atlas_format",
    type=click.Choice(_FORMAT_CHOICES),
    default="auto",
    help="Atlas file format. Auto-detected for catalog atlases and by extension for custom.",
)
@click.option(
    "--atlas-type", "-t",
    type=click.Choice(["surface", "volumetric", "auto"]),
    default=None,
    hidden=True,      # deprecated — kept for backward compatibility
    help="[Deprecated] Use --format instead.",
)
@click.option(
    "--lut", "-l",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a custom LUT TSV (index, label, hemisphere). "
         "Required for custom atlases that lack embedded labels.",
)
@click.option(
    "--subjects", "-s",
    multiple=True,
    help="Subject IDs to process. If omitted, all subjects in SUBJECTS_DIR are processed.",
)
@click.option(
    "--subjects-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Text file with one subject ID per line.",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("fsatlas_output"),
    help="Output directory for TSV files.",
)
@click.option("--force", "-f", is_flag=True, help="Recompute even if outputs already exist.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def extract(
    subjects_dir: Path | None,
    atlas: str,
    atlas_format: str,
    atlas_type: str | None,
    lut: Path | None,
    subjects: tuple[str, ...],
    subjects_file: Path | None,
    output_dir: Path,
    force: bool,
    verbose: bool,
) -> None:
    """Extract morphometric measures for one atlas across subjects."""
    _setup_logging(verbose)

    if atlas_type is not None and atlas_format == "auto":
        console.print(
            "[yellow]--atlas-type is deprecated; use --format instead.[/yellow]"
        )
        atlas_format = {"surface": "annot", "volumetric": "nifti"}.get(atlas_type, "auto")

    try:
        env = FreeSurferEnv.detect(subjects_dir)
    except OSError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(f"FreeSurfer {env.version} | SUBJECTS_DIR: {env.subjects_dir}")

    registry = AtlasRegistry()
    atlas_spec = _resolve_atlas(registry, atlas, atlas_format, lut)

    # Download catalog atlas if needed
    if hasattr(atlas_spec, "is_downloaded") and not atlas_spec.builtin:
        if not atlas_spec.is_downloaded():
            console.print(f"Downloading atlas [bold]{atlas_spec.name}[/bold]...")
            registry.download(atlas_spec.name, env=env)
    elif getattr(atlas_spec, "builtin", False):
        # Ensure builtin LUT is cached
        if not atlas_spec.is_downloaded():
            registry.download(atlas_spec.name, env=env)

    subject_list = _resolve_subjects(env, subjects, subjects_file)
    if not subject_list:
        console.print("[red]No subjects found.[/red]")
        sys.exit(1)

    console.print(
        f"Atlas: [bold]{atlas_spec.name}[/bold] (format={atlas_spec.format}) | "
        f"Subjects: {len(subject_list)}"
    )

    output_paths = run_extraction(
        atlas=atlas_spec,
        subjects=subject_list,
        env=env,
        output_dir=output_dir,
        force=force,
    )

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
    table.add_column("Format")
    table.add_column("Family")
    table.add_column("Description")
    table.add_column("Cached", justify="center")

    for a in atlases:
        cached = "✓" if a.is_downloaded() else "—"
        table.add_row(a.name, a.format, a.family, a.description, cached)

    console.print(table)


@cli.command()
@click.argument("atlas_name")
@click.option("--force", is_flag=True, help="Re-download even if cached.")
@click.option(
    "--subjects-dir", "-d",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="FreeSurfer SUBJECTS_DIR (needed to generate LUT for built-in atlases).",
)
def download(atlas_name: str, force: bool, subjects_dir: Path | None) -> None:
    """Download an atlas from the catalog to local cache."""
    registry = AtlasRegistry()
    try:
        env: FreeSurferEnv | None = None
        try:
            env = FreeSurferEnv.detect(subjects_dir)
        except OSError:
            pass  # env not required for non-builtin, non-annot atlases
        atlas = registry.download(atlas_name, force=force, env=env)
        console.print(f"[green]Atlas '{atlas.name}' ready at {atlas.cache_dir}[/green]")
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Download failed: {e}[/red]")
        sys.exit(1)


@cli.command("generate-lut")
@click.option(
    "--atlas", "-a",
    default=None,
    help="Catalog atlas name to generate a LUT for (e.g. desikan).",
)
@click.option(
    "--lh-annot",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Left-hemisphere .annot file (for custom atlas LUT generation).",
)
@click.option(
    "--rh-annot",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Right-hemisphere .annot file (for custom atlas LUT generation).",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Output TSV path.",
)
@click.option(
    "--subjects-dir", "-d",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="FreeSurfer SUBJECTS_DIR (needed for built-in atlases).",
)
def generate_lut(
    atlas: str | None,
    lh_annot: Path | None,
    rh_annot: Path | None,
    output: Path,
    subjects_dir: Path | None,
) -> None:
    """Generate a LUT TSV from a .annot file pair or a catalog atlas.

    Examples:

    \b
      fsatlas generate-lut --atlas desikan -o desikan_labels.tsv
      fsatlas generate-lut --lh-annot lh.myatlas.annot --rh-annot rh.myatlas.annot -o lut.tsv
    """
    from ..core.lut import LookupTable

    if atlas is not None:
        registry = AtlasRegistry()
        spec = registry.get(atlas)
        if spec.format != "annot":
            console.print(
                f"[red]Atlas '{atlas}' is not an annot atlas (format={spec.format}).[/red]"
            )
            sys.exit(1)

        if spec.builtin:
            try:
                env = FreeSurferEnv.detect(subjects_dir)
            except OSError as e:
                console.print(f"[red]{e}[/red]")
                sys.exit(1)
            fsavg = env.freesurfer_home / "subjects" / "fsaverage" / "label"
            lh_annot = fsavg / f"lh.{spec.annot_name}.annot"
            rh_annot = fsavg / f"rh.{spec.annot_name}.annot"
        else:
            if not spec.is_downloaded():
                console.print(
                    f"[yellow]Atlas '{atlas}' not cached. "
                    f"Run 'fsatlas download {atlas}' first.[/yellow]"
                )
                sys.exit(1)
            lh_annot = spec.get_file("lh.annot")
            rh_annot = spec.get_file("rh.annot")

    if lh_annot is None or rh_annot is None:
        console.print("[red]Provide either --atlas or both --lh-annot and --rh-annot.[/red]")
        sys.exit(1)

    lut = LookupTable.from_annot(lh_annot, rh_annot)
    lut.to_tsv(output)
    console.print(f"[green]LUT written to {output} ({len(lut.df)} regions)[/green]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_atlas(registry: AtlasRegistry, atlas_arg: str, atlas_format: str, lut: Path | None):
    """Resolve an atlas argument to an AtlasSpec or CustomAtlasSpec."""
    # Try catalog lookup first
    try:
        spec = registry.get(atlas_arg)
        if lut is not None:
            spec.labels_tsv = str(lut)  # override LUT path if explicitly provided
        return spec
    except KeyError:
        pass

    path = Path(atlas_arg)
    if not path.exists():
        console.print(
            f"[red]'{atlas_arg}' is not a catalog atlas name nor an existing file.[/red]"
        )
        console.print("Use [bold]fsatlas list-atlases[/bold] to see available catalog atlases.")
        sys.exit(1)

    # Auto-detect format from extension
    if atlas_format == "auto":
        name_lower = path.name.lower()
        if path.suffix == ".annot":
            atlas_format = "annot"
        elif name_lower.endswith(".nii.gz") or path.suffix == ".nii":
            atlas_format = "nifti"
        elif name_lower.endswith(".dlabel.gii") or name_lower.endswith(".label.gii"):
            atlas_format = "dlabel_gii"
        elif path.suffix == ".gca":
            atlas_format = "gca"
        else:
            console.print(
                f"[red]Cannot infer format from extension '{path.suffix}'. "
                f"Use --format to specify.[/red]"
            )
            sys.exit(1)

    if atlas_format == "annot":
        stem = path.stem
        parent = path.parent
        if stem.startswith("lh."):
            lh, rh = path, parent / f"rh.{stem[3:]}.annot"
        elif stem.startswith("rh."):
            rh, lh = path, parent / f"lh.{stem[3:]}.annot"
        else:
            console.print(
                "[red]Surface annot file must start with 'lh.' or 'rh.' "
                "so the other hemisphere can be found.[/red]"
            )
            sys.exit(1)
        return AtlasRegistry.from_custom_surface(lh, rh, labels_tsv=lut)

    elif atlas_format == "nifti":
        return AtlasRegistry.from_custom_volumetric(path, labels_tsv=lut)

    elif atlas_format == "dlabel_gii":
        name_lower = path.name.lower()
        parent = path.parent
        if name_lower.startswith("lh."):
            stem = path.name[3:]
            lh, rh = path, parent / f"rh.{stem}"
        elif name_lower.startswith("rh."):
            stem = path.name[3:]
            rh, lh = path, parent / f"lh.{stem}"
        else:
            console.print("[red]dlabel.gii file must start with 'lh.' or 'rh.'.[/red]")
            sys.exit(1)
        return AtlasRegistry.from_custom_dlabel_gii(lh, rh, labels_tsv=lut)

    elif atlas_format == "gca":
        return AtlasRegistry.from_custom_gca(path, labels_tsv=lut)

    else:
        console.print(f"[red]Unknown format: {atlas_format}[/red]")
        sys.exit(1)


def _resolve_subjects(
    env: FreeSurferEnv,
    subjects_args: tuple[str, ...],
    subjects_file: Path | None,
) -> list[str]:
    """Build subject list from CLI args, file, or auto-discovery."""
    subject_list = list(subjects_args)
    if subjects_file:
        lines = subjects_file.read_text().splitlines()
        subject_list.extend(
            line.strip() for line in lines if line.strip() and not line.startswith("#")
        )
    if not subject_list:
        subject_list = env.list_subjects()
        console.print(f"Auto-discovered {len(subject_list)} subjects in {env.subjects_dir}")
    return subject_list
