"""Nonlinear registration of MNI152 atlases to subject space via mri_easyreg.

Public API
----------
ensure_template_synthseg(space, env) -> Path
    Run mri_synthseg --parc on the templateflow MNI152 T1w (cached globally).

ensure_subject_synthseg(subject, env) -> Path
    Return the per-subject SynthSeg parcellation (recon-all output reused when
    present; fallback runs mri_synthseg --parc on norm.mgz).

ensure_subject_to_template_warp(subject, space, env) -> EasyRegWarpPaths
    Compute (or load from cache) forward/backward deformation fields between
    the subject's norm.mgz and an MNI152 template using mri_easyreg.

apply_template_to_subject(atlas_nii, warp, out_path) -> list[str]
    Resample an atlas NIfTI from template space to subject space using
    mri_easywarp with nearest-neighbour interpolation.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .command import run_command
from .environment import FreeSurferEnv, SubjectPaths

logger = logging.getLogger(__name__)

_SUPPORTED_SPACES = ("MNI152NLin2009cAsym", "MNI152NLin6Asym")

# Long-running registration; allow up to 3 hours.
_EASYREG_TIMEOUT = 10_800
_SYNTHSEG_TIMEOUT = 3_600


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EasyRegWarpPaths:
    """Paths to cached mri_easyreg outputs for one subject ↔ template pair."""

    fwd_field: Path  # native_to_mni.nii.gz
    bak_field: Path  # mni_to_native.nii.gz
    reference: Path  # subject norm.mgz (used as the resampling reference grid)
    commands_run: list[list[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _easyreg_threads() -> int:
    """Number of threads: OMP_NUM_THREADS or 1."""
    try:
        return int(os.environ.get("OMP_NUM_THREADS", "1"))
    except ValueError:
        return 1


def _resolve_cache_dir() -> Path:
    """Return the root directory for fsatlas-managed caches.

    Priority:
      1. $FSATLAS_CACHE_DIR (explicit override)
      2. $XDG_CACHE_HOME/fsatlas
      3. ~/.cache/fsatlas
    """
    if fsatlas_cache := os.environ.get("FSATLAS_CACHE_DIR"):
        return Path(fsatlas_cache)
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "fsatlas"
    return Path.home() / ".cache" / "fsatlas"


def _get_template_t1w(space: str) -> Path:
    """Return the templateflow T1w path for *space* (resolution 1)."""
    import templateflow.api as tflow

    t1w = tflow.get(space, resolution=1, suffix="T1w", extension=".nii.gz")
    if t1w is None:
        raise RuntimeError(f"templateflow: T1w not found for space {space!r}")
    if isinstance(t1w, list):
        t1w = t1w[0]
    return Path(t1w)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ensure_template_synthseg(space: str, env: FreeSurferEnv) -> Path:
    """Return the SynthSeg parcellation of the MNI152 template for *space*.

    The result is cached at
    ``$FSATLAS_CACHE_DIR/synthseg/tpl-{space}_synthseg.nii.gz`` and computed
    only once.

    Parameters
    ----------
    space:
        Template space, one of ``MNI152NLin2009cAsym`` or ``MNI152NLin6Asym``.
    env:
        FreeSurfer environment.

    Returns
    -------
    Path
        Path to the cached SynthSeg NIfTI.
    """
    if space not in _SUPPORTED_SPACES:
        raise ValueError(
            f"easyreg: unsupported space {space!r}. Supported: {_SUPPORTED_SPACES}"
        )

    cache_dir = _resolve_cache_dir() / "synthseg"
    out = cache_dir / f"tpl-{space}_synthseg.nii.gz"

    if out.exists():
        logger.info(f"  Template SynthSeg already cached at {out}, skipping")
        return out

    t1w = _get_template_t1w(space)
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_suffix(".tmp.nii.gz")

    logger.info(f"  Running mri_synthseg on template {space} T1w → {out}")
    cmd = [
        "mri_synthseg",
        "--i", str(t1w),
        "--o", str(tmp_out),
        "--parc",
        "--threads", str(_easyreg_threads()),
    ]
    run_command(cmd, env, timeout=_SYNTHSEG_TIMEOUT)

    if not tmp_out.exists():
        raise RuntimeError(
            f"mri_synthseg completed but expected output missing: {tmp_out}"
        )
    os.replace(str(tmp_out), str(out))
    return out


def ensure_subject_synthseg(subject: SubjectPaths, env: FreeSurferEnv) -> Path:
    """Return the SynthSeg parcellation of the subject's ``norm.mgz``.

    Recon-all (FS 7.4+) writes this file to
    ``<sub>/mri/transforms/subject_synthseg.nii.gz`` as part of the standard
    pipeline.  When the file already exists, it is returned immediately.

    If the file is absent (older recon-all run or non-standard subject), this
    function runs ``mri_synthseg --parc`` on ``norm.mgz`` and writes the
    result to the same location.

    Parameters
    ----------
    subject:
        Paths helper for the FreeSurfer subject.
    env:
        FreeSurfer environment.

    Returns
    -------
    Path
        Path to the SynthSeg NIfTI.
    """
    out = subject.subject_synthseg

    if out.exists():
        logger.info(f"  Subject SynthSeg already at {out}, skipping")
        return out

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = out.with_suffix(".tmp.nii.gz")

    logger.info(f"  Running mri_synthseg on {subject.norm_mgz} → {out}")
    cmd = [
        "mri_synthseg",
        "--i", str(subject.norm_mgz),
        "--o", str(tmp_out),
        "--parc",
        "--threads", str(_easyreg_threads()),
    ]
    run_command(cmd, env, timeout=_SYNTHSEG_TIMEOUT)

    if not tmp_out.exists():
        raise RuntimeError(
            f"mri_synthseg completed but expected output missing: {tmp_out}"
        )
    os.replace(str(tmp_out), str(out))
    return out


def ensure_subject_to_template_warp(
    subject: SubjectPaths,
    space: str,
    env: FreeSurferEnv,
) -> EasyRegWarpPaths:
    """Compute (or load from cache) mri_easyreg warp fields for *subject* ↔ *space*.

    Registration outputs are cached under
    ``<sub>/mri/transforms/easyreg/tpl-{space}/``.  Subsequent calls return the
    cached result immediately.

    Uses an atomic staging directory (``tpl-{space}.tmp/``) so that a crashed
    or interrupted run never leaves a half-written cache that would be silently
    reused on the next invocation.

    Parameters
    ----------
    subject:
        Paths helper for the FreeSurfer subject.
    space:
        Template space, one of ``MNI152NLin2009cAsym`` or ``MNI152NLin6Asym``.
    env:
        FreeSurfer environment.

    Returns
    -------
    EasyRegWarpPaths
        Paths to the forward and backward warp fields.
    """
    if space not in _SUPPORTED_SPACES:
        raise ValueError(
            f"easyreg: unsupported space {space!r}. Supported: {_SUPPORTED_SPACES}"
        )

    tpl_dir = subject.easyreg_dir / f"tpl-{space}"
    fwd = tpl_dir / "native_to_mni.nii.gz"
    bak = tpl_dir / "mni_to_native.nii.gz"

    if fwd.exists() and bak.exists():
        logger.info(f"  EasyReg warp for {space} already cached at {tpl_dir}, skipping")
        return EasyRegWarpPaths(fwd_field=fwd, bak_field=bak, reference=subject.norm_mgz)

    logger.info(
        f"  Computing mri_easyreg warp: subject ({subject.subject_id}) ↔ {space}"
    )

    # Ensure SynthSeg inputs are ready.
    tpl_synthseg = ensure_template_synthseg(space, env)
    subj_synthseg = ensure_subject_synthseg(subject, env)
    t1w_tpl = _get_template_t1w(space)

    # Run in a staging directory; atomically promote to final on success.
    tmp_dir = tpl_dir.parent / f"tpl-{space}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    tmp_fwd = tmp_dir / "native_to_mni.nii.gz"
    tmp_bak = tmp_dir / "mni_to_native.nii.gz"

    cmd = [
        "mri_easyreg",
        "--ref", str(t1w_tpl),
        "--flo", str(subject.norm_mgz),
        "--ref_seg", str(tpl_synthseg),
        "--flo_seg", str(subj_synthseg),
        "--fwd_field", str(tmp_fwd),
        "--bak_field", str(tmp_bak),
        "--threads", str(_easyreg_threads()),
    ]

    run_command(cmd, env, timeout=_EASYREG_TIMEOUT)

    for p in (tmp_fwd, tmp_bak):
        if not p.exists():
            raise RuntimeError(
                f"mri_easyreg completed but expected output missing: {p}"
            )

    # Atomic promotion.
    if tpl_dir.exists():
        shutil.rmtree(tpl_dir)
    os.replace(str(tmp_dir), str(tpl_dir))

    return EasyRegWarpPaths(
        fwd_field=fwd,
        bak_field=bak,
        reference=subject.norm_mgz,
        commands_run=[cmd],
    )


def apply_template_to_subject(
    atlas_nii: Path,
    warp: EasyRegWarpPaths,
    out_path: Path,
    env: FreeSurferEnv | None = None,
) -> list[str]:
    """Resample *atlas_nii* from template space into subject space.

    Uses ``mri_easywarp --nearest`` to preserve integer ROI label values
    (equivalent to ANTs' ``GenericLabel`` interpolation).

    Parameters
    ----------
    atlas_nii:
        Source atlas NIfTI in template (MNI152) space.
    warp:
        Cached :class:`EasyRegWarpPaths` from
        :func:`ensure_subject_to_template_warp`.
    out_path:
        Destination path for the resampled atlas.
    env:
        FreeSurfer environment.  When *None*, a minimal env is constructed
        from the current ``FREESURFER_HOME`` / ``SUBJECTS_DIR`` env vars.

    Returns
    -------
    list[str]
        The ``mri_easywarp`` command line (for sidecar provenance).
    """
    if env is None:
        fs_home = os.environ.get("FREESURFER_HOME", "")
        subjects_dir = os.environ.get("SUBJECTS_DIR", "")
        env = FreeSurferEnv(
            freesurfer_home=Path(fs_home) if fs_home else Path("/"),
            subjects_dir=Path(subjects_dir) if subjects_dir else Path("/tmp"),
            version="",
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "mri_easywarp",
        "--i", str(atlas_nii),
        "--o", str(out_path),
        "--field", str(warp.bak_field),
        "--nearest",
        "--threads", str(_easyreg_threads()),
    ]
    logger.info(f"  mri_easywarp {atlas_nii.name} → {out_path}")
    run_command(cmd, env)
    return cmd
