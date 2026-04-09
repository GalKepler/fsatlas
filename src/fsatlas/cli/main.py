"""fsatlas CLI — extract morphometric measures using arbitrary atlases."""

from __future__ import annotations

import logging
import os
import shutil
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
@click.option(
    "--freesurfer-license-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    envvar="FS_LICENSE",
    help="Path to a FreeSurfer license.txt file. Required when running inside a container.",
)
def cli(freesurfer_license_file: Path | None) -> None:
    """fsatlas — Extract morphometric measures from FreeSurfer subjects using arbitrary atlases."""
    if freesurfer_license_file is not None:
        os.environ["FS_LICENSE"] = str(freesurfer_license_file)


@cli.command()
@click.option(
    "--subjects-dir", "-d",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="FreeSurfer SUBJECTS_DIR. Defaults to $SUBJECTS_DIR.",
)
@click.option(
    "--atlas", "-a",
    multiple=True,
    help="Atlas name from catalog (e.g. schaefer100-7) or path to atlas file. Repeat to process multiple atlases.",
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
@click.option(
    "--output-layout",
    type=click.Choice(["flat", "bids"]),
    default="flat",
    show_default=True,
    help=(
        "Output layout: 'flat' writes one TSV per atlas with all subjects concatenated; "
        "'bids' writes per-subject CSVs in a sub-/ses-/anat/ directory tree."
    ),
)
@click.option(
    "--jobs", "-j",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Number of parallel worker threads for subject processing.",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def extract(
    subjects_dir: Path | None,
    atlas: tuple[str, ...],
    atlas_format: str,
    atlas_type: str | None,
    lut: Path | None,
    subjects: tuple[str, ...],
    subjects_file: Path | None,
    output_dir: Path,
    force: bool,
    output_layout: str,
    jobs: int,
    verbose: bool,
) -> None:
    """Extract morphometric measures for one or more atlases across subjects."""
    _setup_logging(verbose)

    if not atlas:
        console.print("[red]At least one --atlas / -a argument is required.[/red]")
        sys.exit(1)

    if atlas_type is not None and atlas_format == "auto":
        console.print(
            "[yellow]--atlas-type is deprecated; use --format instead.[/yellow]"
        )
        atlas_format = {"surface": "annot", "volumetric": "nifti"}.get(atlas_type, "auto")

    if lut is not None and len(atlas) > 1:
        console.print(
            "[yellow]Warning: --lut will be applied to all specified atlases.[/yellow]"
        )

    try:
        env = FreeSurferEnv.detect(subjects_dir)
    except OSError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(f"FreeSurfer {env.version} | SUBJECTS_DIR: {env.subjects_dir}")

    subject_list = _resolve_subjects(env, subjects, subjects_file)
    if not subject_list:
        console.print("[red]No subjects found.[/red]")
        sys.exit(1)

    registry = AtlasRegistry()
    all_output_paths: dict[str, Path] = {}

    for atlas_arg in atlas:
        atlas_spec = _resolve_atlas(registry, atlas_arg, atlas_format, lut)

        # Download catalog atlas if needed
        if hasattr(atlas_spec, "is_downloaded") and not atlas_spec.builtin:
            if not atlas_spec.is_downloaded():
                console.print(f"Downloading atlas [bold]{atlas_spec.name}[/bold]...")
                registry.download(atlas_spec.name, env=env)
        elif getattr(atlas_spec, "builtin", False):
            # Ensure builtin LUT is cached
            if not atlas_spec.is_downloaded():
                registry.download(atlas_spec.name, env=env)

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
            output_layout=output_layout,
            jobs=jobs,
        )
        for kind, path in output_paths.items():
            all_output_paths[f"{atlas_spec.name}:{kind}"] = path

    console.print("\n[green]Done![/green]")
    if output_layout == "bids":
        console.print(f"  BIDS output written to: {output_dir}")
    else:
        console.print("  Output files:")
        for kind, path in all_output_paths.items():
            console.print(f"    {kind}: {path}")


@cli.command()
@click.option(
    "--bids-dir", "-d",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="BIDS output directory from 'fsatlas extract --output-layout bids'.",
)
@click.option(
    "--atlas", "-a",
    default=None,
    help="Atlas name to aggregate (e.g. Brainnetome246Ext). "
         "If omitted, lists available atlases and exits.",
)
@click.option(
    "--structure",
    type=click.Choice(["cortex", "subcortex", "both"]),
    default="both",
    show_default=True,
    help="Which structures to include.",
)
@click.option(
    "--subjects", "-s",
    multiple=True,
    help="Subject labels to include (without sub- prefix). Default: all.",
)
@click.option(
    "--subjects-file",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Text file with one subject label per line.",
)
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output file path. Default: {bids_dir}/atlas-{name}_aggregated.csv",
)
@click.option(
    "--format", "-F", "output_format",
    type=click.Choice(["csv", "tsv"]),
    default="csv",
    show_default=True,
    help="Output file format.",
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def aggregate(
    bids_dir: Path,
    atlas: str | None,
    structure: str,
    subjects: tuple[str, ...],
    subjects_file: Path | None,
    output: Path | None,
    output_format: str,
    verbose: bool,
) -> None:
    """Aggregate BIDS-layout per-subject CSVs into a single wide-format table."""
    _setup_logging(verbose)

    from ..core.aggregate import aggregate as run_aggregate, discover_atlases

    if atlas is None:
        available = discover_atlases(bids_dir)
        if not available:
            console.print(f"[yellow]No atlases found in {bids_dir}[/yellow]")
            sys.exit(1)
        console.print("Available atlases:")
        for name in available:
            console.print(f"  {name}")
        return

    # Build subject filter
    subject_list = list(subjects)
    if subjects_file:
        lines = subjects_file.read_text().splitlines()
        subject_list.extend(
            line.strip() for line in lines if line.strip() and not line.startswith("#")
        )
    subject_filter = subject_list or None

    structures = ["cortex", "subcortex"] if structure == "both" else [structure]
    result = run_aggregate(bids_dir, atlas, structures=structures, subjects=subject_filter)

    if result.empty:
        console.print("[yellow]No data found for the specified atlas/subjects.[/yellow]")
        sys.exit(1)

    if output is None:
        ext = ".tsv" if output_format == "tsv" else ".csv"
        output = bids_dir / f"atlas-{atlas}_aggregated{ext}"

    sep = "\t" if output_format == "tsv" else ","
    result.to_csv(output, sep=sep, index=False)

    n_subjects = result["subject_id"].nunique()
    n_rows = len(result)
    console.print(
        f"[green]Aggregated {n_subjects} subject(s), {n_rows} rows → {output}[/green]"
    )


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


@cli.command("build-atlas-dir")
@click.option(
    "--output", "-o",
    type=click.Path(path_type=Path),
    required=True,
    help="Destination directory for the BIDS-structured atlas files.",
)
@click.option("--force", "-f", is_flag=True, help="Re-download and overwrite existing files.")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging.")
def build_atlas_dir(output: Path, force: bool, verbose: bool) -> None:
    """Populate a BIDS-structured atlas directory with all non-builtin catalog atlases.

    Downloads (or copies from local source) every non-FreeSurfer-builtin atlas and
    organises the files under OUTPUT using BIDS-style naming:

    \b
      OUTPUT/
        dataset_description.json
        <atlas-name>/
          atlas-<BidsName>_hemi-L_space-<space>_dseg.annot   (surface)
          atlas-<BidsName>_hemi-R_space-<space>_dseg.annot
          atlas-<BidsName>_dseg.tsv
          atlas-<BidsName>_space-<space>_res-01_dseg.nii[.gz] (volumetric)
          atlas-<BidsName>_dseg.tsv

    This directory can be committed to the repository and COPYed into the Docker
    image so that containers work without any runtime downloads.
    """
    import json

    _setup_logging(verbose)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    registry = AtlasRegistry()

    # Write dataset_description.json
    desc_path = output / "dataset_description.json"
    if not desc_path.exists() or force:
        desc = {
            "Name": "fsatlas built-in atlas collection",
            "BIDSVersion": "1.9.0",
            "DatasetType": "atlas",
            "GeneratedBy": [
                {"Name": "fsatlas", "CodeURL": "https://github.com/GalKepler/fsatlas"}
            ],
        }
        desc_path.write_text(json.dumps(desc, indent=2) + "\n")
        console.print(f"Wrote {desc_path}")

    atlases = [a for a in registry.list_atlases() if not a.builtin]
    console.print(f"Building BIDS atlas directory for {len(atlases)} atlases → {output}")

    ok = failed = 0
    for spec in atlases:
        atlas_dir = output / spec.name
        atlas_dir.mkdir(parents=True, exist_ok=True)

        # Check whether all BIDS files already exist
        bids_files = {k: spec._bids_filename_for_key(k) for k in spec.files}
        bids_lut = spec._bids_labels_filename
        all_present = all((atlas_dir / fn).exists() for fn in bids_files.values()) and (
            atlas_dir / bids_lut
        ).exists()
        if all_present and not force:
            console.print(f"  [dim]{spec.name}[/dim] already present, skipping")
            ok += 1
            continue

        try:
            # Populate the local cache via the existing download mechanism, then BIDS-rename
            downloaded = registry.download(spec.name, force=force)

            for key, bids_filename in bids_files.items():
                src = downloaded.cache_dir / key
                dst = atlas_dir / bids_filename
                if src.exists():
                    if not dst.exists() or force:
                        shutil.copy2(src, dst)
                else:
                    console.print(
                        f"  [yellow]Warning:[/yellow] {spec.name}: {key} missing in cache"
                    )

            lut_src = downloaded.cache_dir / "labels.tsv"
            lut_dst = atlas_dir / bids_lut
            if lut_src.exists():
                if not lut_dst.exists() or force:
                    shutil.copy2(lut_src, lut_dst)
            else:
                console.print(
                    f"  [yellow]Warning:[/yellow] {spec.name}: labels.tsv missing in cache"
                )

            console.print(f"  [green]✓[/green] {spec.name}")
            ok += 1
        except Exception as exc:
            console.print(f"  [red]✗[/red] {spec.name}: {exc}")
            failed += 1

    console.print(
        f"\n[green]{ok} atlas(es) written[/green]"
        + (f", [red]{failed} failed[/red]" if failed else "")
        + f" → {output}"
    )
    if failed:
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
    else:
        subject_list = _expand_sessions(env, subject_list)
    return subject_list


def _expand_sessions(env: FreeSurferEnv, subjects: list[str]) -> list[str]:
    """Expand each subject code to include all matching sessions (<subject>_*).

    If a directory named exactly ``subject_id`` exists it is kept.
    Any directories matching ``<subject_id>_*`` are also included.
    When no sessions are found the original ID is kept so the pipeline
    can emit a clear error later.
    """
    expanded: list[str] = []
    seen: set[str] = set()

    for subject_id in subjects:
        # Exact match
        if (env.subjects_dir / subject_id).is_dir():
            if subject_id not in seen:
                expanded.append(subject_id)
                seen.add(subject_id)

        # Session matches: <subject_id>_*
        sessions = sorted(
            d.name
            for d in env.subjects_dir.iterdir()
            if d.is_dir() and d.name.startswith(f"{subject_id}_")
        )
        for session in sessions:
            if session not in seen:
                expanded.append(session)
                seen.add(session)

        if subject_id not in seen:
            # Neither exact dir nor sessions found — keep original so the
            # pipeline produces a clear "subject not found" error.
            expanded.append(subject_id)
            seen.add(subject_id)

    return expanded
