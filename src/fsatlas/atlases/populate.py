"""Build / populate the BIDS-atlas directory.

This module contains the logic for downloading and organising atlas files into
the canonical BIDS-atlas directory layout.  It is called by:

- ``scripts/build_bids_atlases.py`` — during Docker / Apptainer image builds.
- ``fsatlas populate`` — for users running fsatlas outside a container.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

import yaml

from .registry import (
    CATALOG_PATH,
    AtlasSpec,
    _add_annot_labels_to_lut,
    _copy_file_from_source,
)

try:
    from .. import __version__
except Exception:
    __version__ = "unknown"

logger = logging.getLogger(__name__)


def _bids_filename(atlas: AtlasSpec, key: str) -> str:
    """Map an internal file key to its BIDS filename (without directory)."""
    base = f"atlas-{atlas.bids_atlas_name}_space-{atlas.space}"
    if key == "lh.annot":
        return f"{base}_hemi-L_dseg.annot"
    if key == "rh.annot":
        return f"{base}_hemi-R_dseg.annot"
    if key in ("atlas.nii.gz", "atlas.nii") or key.endswith(".nii.gz") or (
        key.endswith(".nii") and not key.endswith(".annot")
    ):
        return f"{base}_dseg.nii.gz"
    if key.endswith(".gca"):
        return f"atlas-{atlas.bids_atlas_name}_dseg.gca"
    if key.endswith(".dlabel.gii"):
        hemi = "L" if key.startswith("lh.") else "R"
        return f"{base}_hemi-{hemi}_dseg.dlabel.gii"
    raise KeyError(f"No BIDS filename mapping for key '{key}'")


def _lut_filename(atlas: AtlasSpec) -> str:
    """Return the BIDS filename for *atlas*'s LUT (uses unique name to avoid collisions)."""
    return f"atlas-{atlas._safe_name}_dseg.tsv"


def populate_atlas(
    atlas: AtlasSpec,
    output_dir: Path,
    force: bool = False,
    freesurfer_home: Path | None = None,
) -> Path:
    """Populate one atlas into *output_dir* following the BIDS-atlas layout.

    Returns the atlas sub-directory.
    """
    atlas_dir = output_dir / f"atlas-{atlas.bids_atlas_name}"
    atlas_dir.mkdir(parents=True, exist_ok=True)
    lut_dest = atlas_dir / _lut_filename(atlas)

    if atlas.builtin:
        _populate_builtin(atlas, atlas_dir, lut_dest, freesurfer_home, force)
        return atlas_dir

    # ------------------------------------------------------------------
    # Non-builtin: download / copy atlas files
    # ------------------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="fsatlas_populate_") as tmp:
        tmp_dir = Path(tmp)

        # Download / copy each file to a temp location first
        tmp_files: dict[str, Path] = {}
        for local_key, remote_filename in atlas.files.items():
            bids_fname = _bids_filename(atlas, local_key)
            dest = atlas_dir / bids_fname
            if dest.exists() and not force:
                logger.info(f"  {bids_fname} already present, skipping")
                tmp_files[local_key] = dest
                continue
            tmp_dest = tmp_dir / local_key
            _copy_file_from_source(
                local_key,
                remote_filename,
                tmp_dest,
                atlas.local_source_dir,
                atlas.source_url,
            )
            # Compress .nii → .nii.gz on the fly
            if local_key.endswith(".nii") and not local_key.endswith(".nii.gz"):
                import gzip
                gz_dest = tmp_dir / (local_key + ".gz")
                with open(tmp_dest, "rb") as f_in, gzip.open(gz_dest, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                tmp_dest = gz_dest
            tmp_files[local_key] = tmp_dest

        # Move temp files to final BIDS paths
        for local_key, src_path in tmp_files.items():
            bids_fname = _bids_filename(atlas, local_key)
            final_dest = atlas_dir / bids_fname
            if final_dest != src_path:
                shutil.copy2(src_path, final_dest)
                logger.info(f"  Wrote {final_dest}")

        # ------------------------------------------------------------------
        # Generate / copy the LUT
        # ------------------------------------------------------------------
        if lut_dest.exists() and not force:
            logger.info(f"  LUT already present: {lut_dest}")
            return atlas_dir

        # Prefer a rich dseg.tsv from the catalog package
        dseg_src = _find_dseg_tsv(atlas)
        if dseg_src is not None:
            logger.info(f"  Copying dseg.tsv for '{atlas.name}': {dseg_src} -> {lut_dest}")
            shutil.copy2(dseg_src, lut_dest)
            if atlas.format in ("annot", "dlabel_gii"):
                lh = atlas_dir / _bids_filename(atlas, "lh.annot")
                rh = atlas_dir / _bids_filename(atlas, "rh.annot")
                if lh.exists() and rh.exists():
                    _add_annot_labels_to_lut(lut_dest, lh, rh)

        elif atlas.format == "annot":
            from ..core.lut import LookupTable
            lh = atlas_dir / _bids_filename(atlas, "lh.annot")
            rh = atlas_dir / _bids_filename(atlas, "rh.annot")
            if lh.exists() and rh.exists():
                logger.info(f"  Generating LUT from .annot colour table for '{atlas.name}'")
                lut = LookupTable.from_annot(lh, rh)
                lut.to_tsv(lut_dest)
            else:
                logger.warning(f"  Cannot generate LUT for '{atlas.name}': annot files missing")

        else:
            # Volumetric: copy the labels TSV from catalog package dir or download it
            _fetch_labels_tsv(atlas, lut_dest)

    logger.info(f"Atlas '{atlas.name}' ready at {atlas_dir}")
    return atlas_dir


def _populate_builtin(
    atlas: AtlasSpec,
    atlas_dir: Path,
    lut_dest: Path,
    freesurfer_home: Path | None,
    force: bool,
) -> None:
    """Generate / copy the LUT for a FreeSurfer built-in atlas."""
    from ..core.lut import LookupTable

    if lut_dest.exists() and not force:
        logger.info(f"  Builtin LUT already present: {lut_dest}")
        return

    if atlas.format == "annot":
        # Try bundled package TSV first (e.g. pre-computed for common builtins)
        if atlas.labels_tsv:
            bundled = CATALOG_PATH.parent / atlas.labels_tsv
            if bundled.exists() and bundled != lut_dest:
                shutil.copy2(bundled, lut_dest)
                logger.info(f"  Copied bundled LUT for builtin '{atlas.name}'")
                return

        # Generate from fsaverage annot files (requires FreeSurfer)
        if freesurfer_home is None:
            logger.warning(
                f"Cannot generate LUT for built-in '{atlas.name}': "
                "FREESURFER_HOME not set / FreeSurfer not found. "
                "Pass --freesurfer-home or run inside a container."
            )
            return
        fsavg_label = freesurfer_home / "subjects" / "fsaverage" / "label"
        lh = fsavg_label / f"lh.{atlas.annot_name}.annot"
        rh = fsavg_label / f"rh.{atlas.annot_name}.annot"
        if lh.exists() and rh.exists():
            logger.info(f"  Generating LUT for builtin '{atlas.name}' from fsaverage")
            lut = LookupTable.from_annot(lh, rh)
            lut.to_tsv(lut_dest)
        else:
            logger.warning(
                f"  fsaverage annot not found for '{atlas.name}' at {fsavg_label}"
            )

    elif atlas.format == "nifti":
        # Copy the bundled labels TSV (e.g. aseg_labels.tsv)
        if atlas.labels_tsv:
            bundled = CATALOG_PATH.parent / atlas.labels_tsv
            if bundled.exists():
                shutil.copy2(bundled, lut_dest)
                logger.info(f"  Copied bundled NIfTI LUT for builtin '{atlas.name}'")
            else:
                logger.warning(
                    f"  Bundled labels not found for '{atlas.name}': {bundled}"
                )


def _find_dseg_tsv(atlas: AtlasSpec) -> Path | None:
    """Return the source path of a bundled dseg.tsv for *atlas*, or None."""
    if not atlas.dseg_tsv:
        return None

    if atlas.local_source_dir:
        local_dir = Path(atlas.local_source_dir)
        if not local_dir.is_absolute():
            local_dir = CATALOG_PATH.parent / local_dir
        candidate = local_dir / atlas.dseg_tsv
        if candidate.exists():
            return candidate

    candidate = CATALOG_PATH.parent / atlas.dseg_tsv
    if candidate.exists():
        return candidate

    logger.warning(
        f"dseg_tsv '{atlas.dseg_tsv}' specified for '{atlas.name}' but not found."
    )
    return None


def _fetch_labels_tsv(atlas: AtlasSpec, dest: Path) -> None:
    """Copy or download the raw labels file for a volumetric atlas."""
    if not atlas.labels_tsv:
        logger.warning(f"No labels_tsv defined for '{atlas.name}' — LUT will be missing.")
        return

    catalog_labels = CATALOG_PATH.parent / atlas.labels_tsv
    if catalog_labels.exists():
        logger.info(f"  Copying catalog labels {catalog_labels} -> {dest}")
        shutil.copy2(catalog_labels, dest)
        return

    if atlas.source_url:
        import requests
        url = f"{atlas.source_url}/{atlas.labels_tsv}"
        logger.info(f"  Downloading labels {url} -> {dest}")
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return

    logger.warning(f"  No labels_tsv source found for '{atlas.name}'.")


def write_dataset_description(output_dir: Path) -> None:
    """Write a BIDS dataset_description.json to *output_dir*."""
    desc = {
        "Name": "fsatlas BIDS Atlas Directory",
        "BIDSVersion": "1.9.0",
        "GeneratedBy": [{"Name": "fsatlas", "Version": __version__}],
        "HowToAcknowledge": (
            "Please cite the individual atlases used. "
            "See each atlas directory for citation information."
        ),
    }
    out = output_dir / "dataset_description.json"
    with open(out, "w") as f:
        json.dump(desc, f, indent=2)
    logger.info(f"Wrote {out}")


def populate_all(
    output_dir: Path,
    atlas_names: list[str] | None = None,
    force: bool = False,
    freesurfer_home: Path | None = None,
    catalog_path: Path | None = None,
) -> None:
    """Populate *output_dir* with all (or selected) atlases from the catalog.

    Parameters
    ----------
    output_dir:
        Destination BIDS-atlas directory.
    atlas_names:
        If given, only populate these specific atlas names.
    force:
        Re-download / re-generate even if files already exist.
    freesurfer_home:
        Path to ``$FREESURFER_HOME`` — required for built-in atlases.
    catalog_path:
        Override the default catalog.yaml location.
    """
    cp = catalog_path or CATALOG_PATH
    with open(cp) as f:
        raw = yaml.safe_load(f)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_dataset_description(output_dir)

    # Build AtlasSpec objects on the fly to avoid importing AtlasRegistry
    from .registry import AtlasRegistry
    registry = AtlasRegistry(catalog_path=cp)

    to_process = atlas_names or list(raw.keys())
    failed: list[tuple[str, str]] = []

    for name in to_process:
        try:
            atlas = registry.get(name)
            logger.info(f"Processing atlas '{name}'...")
            populate_atlas(atlas, output_dir, force=force, freesurfer_home=freesurfer_home)
        except KeyError as e:
            logger.error(f"Unknown atlas '{name}': {e}")
            failed.append((name, str(e)))
        except Exception as e:
            logger.error(f"Failed to populate '{name}': {e}")
            failed.append((name, str(e)))

    if failed:
        logger.warning(f"{len(failed)} atlas(es) failed:")
        for name, reason in failed:
            logger.warning(f"  {name}: {reason}")
    else:
        logger.info(f"All atlases populated in {output_dir}")
