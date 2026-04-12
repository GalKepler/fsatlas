"""Nonlinear registration of MNI152 atlases to subject space via ANTs.

Public API
----------
ensure_subject_ref_nifti(subject, env) -> Path
    Convert norm.mgz → subject_T1w.nii.gz (cached).

ensure_subject_to_template_warp(subject, space, env) -> WarpPaths
    Compute (or load from cache) a SyN warp between the subject T1 and an
    MNI152 template fetched from templateflow.

apply_template_to_subject(atlas_nii, warp, out_path) -> list[str]
    Resample an atlas NIfTI from template space to subject space with
    GenericLabel interpolation.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import numpy as np

from .command import run_command
from .environment import FreeSurferEnv, SubjectPaths

logger = logging.getLogger(__name__)

_SUPPORTED_SPACES = ("MNI152NLin2009cAsym", "MNI152NLin6Asym")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class WarpPaths:
    """Paths to cached ANTs warp outputs for one subject ↔ template pair."""

    affine: Path  # *0GenericAffine.mat
    warp: Path  # *1Warp.nii.gz
    inverse_warp: Path  # *1InverseWarp.nii.gz
    reference: Path  # subject T1w NIfTI (fixed image)
    commands_run: list[list[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_template(space: str) -> tuple[Path, Path, Path | None]:
    """Return (T1w, brain_mask) templateflow paths for *space*."""
    import templateflow.api as tflow

    # first, try locating the exact skull-stripped version
    t1w_brain = tflow.get(space, resolution=1, desc="brain", suffix="T1w", extension=".nii.gz")
    if t1w_brain is not None:
        if isinstance(t1w_brain, list):
            t1w_brain = Path(t1w_brain[0])

    t1w = tflow.get(space, resolution=1, suffix="T1w", extension=".nii.gz")
    mask = tflow.get(space, resolution=1, desc="brain", suffix="mask", extension=".nii.gz")
    if t1w is None:
        raise RuntimeError(f"templateflow: T1w not found for space {space!r}")
    if mask is None:
        raise RuntimeError(
            f"templateflow: brain mask not found for space {space!r}. "
            "Try: import templateflow.api; templateflow.api.get(...)"
        )
    # templateflow.get() may return a list when multiple resolutions match.
    if isinstance(t1w, list):
        t1w = t1w[0]
    if isinstance(mask, list):
        mask = mask[0]
    return Path(t1w), Path(mask), t1w_brain


def _mask_template(t1w: Path, mask: Path, out: Path) -> None:
    """Multiply template T1w by its brain mask and write to *out*."""
    if out.exists():
        return
    img = nib.load(str(t1w))
    msk = nib.load(str(mask))
    masked = img.get_fdata() * msk.get_fdata().astype(bool)
    out.parent.mkdir(parents=True, exist_ok=True)
    nib.save(
        nib.Nifti1Image(masked.astype(np.float32), img.affine, img.header),
        str(out),
    )


def _ants_threads(env: FreeSurferEnv) -> int:
    """Number of threads for ANTs: OMP_NUM_THREADS or 1."""
    try:
        return int(os.environ.get("OMP_NUM_THREADS", "1"))
    except ValueError:
        return 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_subject_ref_nifti(subject: SubjectPaths, env: FreeSurferEnv) -> Path:
    """Convert *norm.mgz* to a NIfTI file suitable as the ANTs fixed image.

    The result is cached at ``<sub>/mri/ants/subject_T1w.nii.gz``.
    """
    out = subject.subject_t1w_nii
    if out.exists():
        logger.info(f"  Subject T1w NIfTI already at {out}, skipping mri_convert")
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"  Converting {subject.norm_mgz} → {out}")
    run_command(["mri_convert", str(subject.norm_mgz), str(out)], env)
    return out


def ensure_subject_to_template_warp(
    subject: SubjectPaths,
    space: str,
    env: FreeSurferEnv,
) -> WarpPaths:
    """Compute a nonlinear SyN warp between the subject T1 and *space*.

    Registration is computed once and cached under
    ``<sub>/mri/transforms/ants/tpl-{space}/``.  Subsequent calls return the
    cached result immediately.

    Parameters
    ----------
    subject:
        Paths helper for the FreeSurfer subject.
    space:
        Template space, one of ``MNI152NLin2009cAsym`` or ``MNI152NLin6Asym``.
    env:
        FreeSurfer environment (used for ``mri_convert`` call).

    Returns
    -------
    WarpPaths
        Paths to the affine, SyN warp, and inverse warp.
    """
    if space not in _SUPPORTED_SPACES:
        raise ValueError(
            f"ANTs registration: unsupported space {space!r}. Supported: {_SUPPORTED_SPACES}"
        )

    tpl_dir = subject.ants_dir / f"tpl-{space}"
    affine = tpl_dir / "xfm_0GenericAffine.mat"
    warp = tpl_dir / "xfm_1Warp.nii.gz"
    inv_warp = tpl_dir / "xfm_1InverseWarp.nii.gz"
    ref = ensure_subject_ref_nifti(subject, env)

    if affine.exists() and warp.exists() and inv_warp.exists():
        logger.info(f"  ANTs warp for {space} already cached at {tpl_dir}, skipping")
        return WarpPaths(affine=affine, warp=warp, inverse_warp=inv_warp, reference=ref)

    logger.info(f"  Computing ANTs SyN warp: subject ({subject.subject_id}) ↔ {space}")

    # Fetch and mask the template.
    t1w_tpl, mask_tpl, t1w_brain_tpl = _get_template(space)
    masked_tpl = (
        subject.ants_dir / f"tpl-{space}_T1w_brain.nii.gz"
        if t1w_brain_tpl is None
        else t1w_brain_tpl
    )
    subject.ants_dir.mkdir(parents=True, exist_ok=True)
    _mask_template(t1w_tpl, mask_tpl, masked_tpl)

    # Run registration in a temp staging directory; atomically rename on success.
    tmp_dir = tpl_dir.parent / f"tpl-{space}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    prefix = str(tmp_dir / "xfm_")

    try:
        from nipype.interfaces.ants import Registration

        reg = Registration()
        reg.inputs.fixed_image = str(ref)
        reg.inputs.moving_image = str(masked_tpl)
        reg.inputs.output_transform_prefix = prefix
        reg.inputs.num_threads = _ants_threads(env)

        # Equivalent to antsRegistrationSyN.sh -t s (Rigid + Affine + SyN)
        reg.inputs.transforms = ["Rigid", "Affine", "SyN"]
        reg.inputs.transform_parameters = [(0.1,), (0.1,), (0.1, 3.0, 0.0)]
        reg.inputs.metric = ["MI", "MI", "CC"]
        reg.inputs.metric_weight = [1, 1, 1]
        reg.inputs.radius_or_number_of_bins = [32, 32, 4]
        reg.inputs.sampling_strategy = ["Regular", "Regular", None]
        reg.inputs.sampling_percentage = [0.25, 0.25, None]
        reg.inputs.number_of_iterations = [
            [1000, 500, 250, 100],
            [1000, 500, 250, 100],
            [100, 70, 50, 20],
        ]
        reg.inputs.convergence_threshold = [1e-6, 1e-6, 1e-6]
        reg.inputs.convergence_window_size = [10, 10, 10]
        reg.inputs.smoothing_sigmas = [[3, 2, 1, 0], [3, 2, 1, 0], [3, 2, 1, 0]]
        reg.inputs.shrink_factors = [[8, 4, 2, 1], [8, 4, 2, 1], [8, 4, 2, 1]]
        reg.inputs.sigma_units = ["vox"] * 3
        reg.inputs.use_histogram_matching = [False, False, True]
        reg.inputs.write_composite_transform = False

        logger.info(f"  antsRegistration cmdline: {reg.cmdline}")
        reg.run()

    except ImportError:
        raise RuntimeError(
            "nipype is required for ANTs registration. Install it with: pip install nipype"
        )

    # Verify outputs landed in the staging dir.
    tmp_affine = tmp_dir / "xfm_0GenericAffine.mat"
    tmp_warp = tmp_dir / "xfm_1Warp.nii.gz"
    tmp_inv = tmp_dir / "xfm_1InverseWarp.nii.gz"
    for p in (tmp_affine, tmp_warp, tmp_inv):
        if not p.exists():
            raise RuntimeError(
                f"antsRegistration completed but expected output missing: {p}. "
                "Check nipype working directory for logs."
            )

    # Atomic promotion: rename staging dir → final dir.
    if tpl_dir.exists():
        shutil.rmtree(tpl_dir)
    os.replace(str(tmp_dir), str(tpl_dir))

    return WarpPaths(
        affine=affine,
        warp=warp,
        inverse_warp=inv_warp,
        reference=ref,
        commands_run=[[reg.cmdline]],
    )


def apply_template_to_subject(
    atlas_nii: Path,
    warp: WarpPaths,
    out_path: Path,
) -> list[str]:
    """Resample *atlas_nii* from template space into subject space.

    Uses ``antsApplyTransforms`` with ``GenericLabel`` interpolation to
    preserve integer label values.

    Parameters
    ----------
    atlas_nii:
        Source atlas NIfTI in template (MNI152) space.
    warp:
        Cached :class:`WarpPaths` from :func:`ensure_subject_to_template_warp`.
    out_path:
        Destination path for the resampled atlas.

    Returns
    -------
    list[str]
        The ``antsApplyTransforms`` command line (for sidecar provenance).
    """
    try:
        from nipype.interfaces.ants import ApplyTransforms
    except ImportError:
        raise RuntimeError(
            "nipype is required for ANTs transforms. Install it with: pip install nipype"
        )

    at = ApplyTransforms()
    at.inputs.input_image = str(atlas_nii)
    at.inputs.reference_image = str(warp.reference)
    # Apply SyN warp first, then affine (ANTs convention for forward mapping).
    at.inputs.transforms = [str(warp.warp), str(warp.affine)]
    at.inputs.invert_transform_flags = [False, False]
    at.inputs.interpolation = "GenericLabel"
    at.inputs.output_image = str(out_path)
    at.inputs.input_image_type = 0  # scalar

    logger.info(f"  antsApplyTransforms cmdline: {at.cmdline}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        at.inputs.environ = {"ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS": "1"}
        result = at.run(cwd=tmp)
        _ = result  # nipype writes directly to out_path (absolute path)

    return [at.cmdline]
