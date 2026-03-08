"""Atlas transfer: project atlases from template/MNI space to subject native space.

Surface atlases: uses nibabel to read fsaverage .annot, then FreeSurfer's
mri_surf2surf to resample to subject space (Python-native reading is not
sufficient here since the resampling requires the spherical registration).

Volumetric atlases: uses FreeSurfer's mri_vol2vol with talairach.xfm to
transform MNI-space NIfTI to subject native space.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import nibabel as nib

from ..atlases.registry import AtlasSpec, CustomAtlasSpec
from .environment import FreeSurferEnv, SubjectPaths

logger = logging.getLogger(__name__)

# Type alias for atlas specs
AnyAtlasSpec = AtlasSpec | CustomAtlasSpec


def transfer_surface_atlas(
    atlas: AnyAtlasSpec,
    subject: SubjectPaths,
    env: FreeSurferEnv,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Transfer a surface .annot atlas from fsaverage to subject space.

    For built-in atlases (DKT, Desikan, Destrieux), the annot files
    already exist in the subject's label/ directory — no transfer needed.

    Returns:
        Dict mapping hemisphere ("lh", "rh") to the subject-space .annot path.
    """
    if atlas.builtin:
        # Built-in atlas: annot files already created by recon-all
        annot_name = atlas.annot_name
        result = {}
        for hemi in ("lh", "rh"):
            annot_path = subject.annot_path(hemi, annot_name)
            if not annot_path.exists():
                raise FileNotFoundError(
                    f"Built-in atlas '{atlas.name}' annot not found at {annot_path}. "
                    f"Was recon-all completed for {subject.subject_id}?"
                )
            result[hemi] = annot_path
        return result

    # Determine annot name for the output in subject's label dir
    annot_name = _atlas_annot_name(atlas)
    result = {}

    for hemi in ("lh", "rh"):
        tgt_annot = subject.label_dir / f"{hemi}.{annot_name}.annot"

        if tgt_annot.exists() and not overwrite:
            logger.info(f"  {hemi}: annot already exists at {tgt_annot}, skipping")
            result[hemi] = tgt_annot
            continue

        # Get source annot path
        src_key = f"{hemi}.annot"
        src_annot = atlas.get_file(src_key)

        # For catalog atlases, the source is in fsaverage label dir.
        # We need it to be accessible — either symlink or copy to fsaverage/label
        # or pass it directly to mri_surf2surf via --sval-annot.
        logger.info(f"  {hemi}: mri_surf2surf {src_annot} -> {tgt_annot}")

        cmd = [
            "mri_surf2surf",
            "--srcsubject", "fsaverage",
            "--trgsubject", subject.subject_id,
            "--hemi", hemi,
            "--sval-annot", str(src_annot),
            "--tval", str(tgt_annot),
        ]

        _run_fs_command(cmd, env)
        result[hemi] = tgt_annot

    return result


def transfer_volumetric_atlas(
    atlas: AnyAtlasSpec,
    subject: SubjectPaths,
    env: FreeSurferEnv,
    overwrite: bool = False,
) -> Path:
    """Transfer a volumetric atlas from MNI space to subject native space.

    Uses mri_vol2vol with the inverse talairach transform to bring the
    atlas from MNI152 space into the subject's native (orig.mgz) space.

    Returns:
        Path to the resampled atlas volume in subject space.
    """
    atlas_name = atlas.name
    out_dir = subject.mri_dir / "atlas"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{atlas_name}_native.nii.gz"

    if out_path.exists() and not overwrite:
        if _nifti_shape_matches(out_path, subject.norm_mgz):
            logger.info(f"  Volumetric atlas already at {out_path}, skipping")
            return out_path
        logger.warning(
            f"  Existing {out_path} has wrong dimensions (stale cache); re-running transfer."
        )

    src_nifti = _get_nifti_file(atlas)

    # Use mri_vol2vol with talairach.xfm (inverse) to go MNI -> native
    # --interp nearest is critical for label volumes
    logger.info(f"  mri_vol2vol {src_nifti} -> {out_path}")

    cmd = [
        "mri_vol2vol",
        "--mov", str(src_nifti),
        "--targ", str(subject.norm_mgz),
        "--xfm", str(subject.talairach_xfm),
        "--interp", "nearest",
        "--o", str(out_path),
        "--no-save-reg",
    ]

    _run_fs_command(cmd, env)
    return out_path


def transfer_atlas(
    atlas: AnyAtlasSpec,
    subject: SubjectPaths,
    env: FreeSurferEnv,
    overwrite: bool = False,
) -> dict[str, Path] | Path:
    """Transfer any atlas to subject space. Dispatches based on atlas type."""
    if atlas.type == "surface":
        return transfer_surface_atlas(atlas, subject, env, overwrite)
    elif atlas.type == "volumetric":
        return transfer_volumetric_atlas(atlas, subject, env, overwrite)
    else:
        raise ValueError(f"Unknown atlas type: {atlas.type}")


def _nifti_shape_matches(path_a: Path, path_b: Path) -> bool:
    """Return True if both NIfTI/MGZ files have the same spatial dimensions."""
    try:
        return nib.load(str(path_a)).shape[:3] == nib.load(str(path_b)).shape[:3]
    except Exception:
        return False


def _get_nifti_file(atlas: AnyAtlasSpec) -> Path:
    """Return the NIfTI source path for a volumetric atlas, trying both extensions."""
    for key in ("atlas.nii.gz", "atlas.nii"):
        try:
            return atlas.get_file(key)
        except KeyError:
            continue
    # Fallback: scan available keys for any .nii or .nii.gz entry
    files = atlas.files if isinstance(atlas, AtlasSpec) else atlas.paths
    for key in files:
        if key.endswith(".nii.gz") or key.endswith(".nii"):
            return atlas.get_file(key)
    raise KeyError(f"No NIfTI file found in atlas '{atlas.name}'. Available: {list(files)}")


def _atlas_annot_name(atlas: AnyAtlasSpec) -> str:
    """Derive a clean annotation name from an atlas spec."""
    return atlas.name.replace("/", "_").replace(" ", "_")


def _run_fs_command(cmd: list[str], env: FreeSurferEnv) -> subprocess.CompletedProcess:
    """Run a FreeSurfer command with proper environment."""
    fs_env = {
        **dict(__import__("os").environ),
        "FREESURFER_HOME": str(env.freesurfer_home),
        "SUBJECTS_DIR": str(env.subjects_dir),
    }

    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=fs_env,
        timeout=600,  # 10 min timeout
    )

    if result.returncode != 0:
        logger.error(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
        logger.error(f"stderr: {result.stderr}")
        raise RuntimeError(
            f"FreeSurfer command failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr: {result.stderr[:500]}"
        )

    return result
