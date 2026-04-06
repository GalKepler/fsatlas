"""Atlas format handlers: each file format knows how to transfer and extract.

The handler pattern replaces the old ``atlas.type == "surface"/"volumetric"``
binary dispatch.  Adding support for a new atlas file format means implementing
one new ``AtlasFormatHandler`` subclass and registering it in ``FORMAT_HANDLERS``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import nibabel as nib
import pandas as pd

from ..atlases.registry import AtlasSpec, CustomAtlasSpec
from .command import run_command
from .environment import FreeSurferEnv, SubjectPaths
from .extract import (
    CORTICAL_COLUMNS,
    CORTICAL_MEASURES,
    VOLUMETRIC_MEASURES,
    _parse_cortical_stats_file,
    _parse_etiv_from_header,
    _parse_segstats_file,
    _run_anatomical_stats,
    _run_segstats,
)

logger = logging.getLogger(__name__)

AnyAtlasSpec = AtlasSpec | CustomAtlasSpec


# ---------------------------------------------------------------------------
# Shared atlas utilities (kept here to avoid circular imports with transfer.py)
# ---------------------------------------------------------------------------

def _atlas_annot_name(atlas: AnyAtlasSpec) -> str:
    """Derive a clean annotation name from an atlas spec."""
    return atlas.name.replace("/", "_").replace(" ", "_")


def _nifti_shape_matches(path_a: Path, path_b: Path) -> bool:
    """Return True if both NIfTI/MGZ files have the same spatial dimensions."""
    try:
        return nib.load(str(path_a)).shape[:3] == nib.load(str(path_b)).shape[:3]
    except Exception:
        return False


def _get_nifti_file(atlas: AnyAtlasSpec) -> Path:
    """Return the NIfTI source path for a volumetric atlas."""
    for key in ("atlas.nii.gz", "atlas.nii"):
        try:
            return atlas.get_file(key)
        except KeyError:
            continue
    files = atlas.files if isinstance(atlas, AtlasSpec) else atlas.paths
    for key in files:
        if key.endswith(".nii.gz") or key.endswith(".nii"):
            return atlas.get_file(key)
    raise KeyError(
        f"No NIfTI file found in atlas '{atlas.name}'. Available: {list(files)}"
    )


# ---------------------------------------------------------------------------
# TransferResult — uniform return type from any handler's transfer step
# ---------------------------------------------------------------------------

@dataclass
class TransferResult:
    """Unified result from any atlas transfer step.

    ``paths`` keys are handler-specific:
    - annot/dlabel_gii: ``{"lh": Path, "rh": Path}``
    - nifti/gca: ``{"volume": Path}``

    ``commands_run`` accumulates every actual command invocation (transfer + extract)
    so that the metadata sidecar can record exactly what was executed.
    """

    paths: dict[str, Path] = field(default_factory=dict)
    format_id: str = ""
    commands_run: list[list[str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class AtlasFormatHandler(ABC):
    """Abstract base for atlas format handlers.

    Each concrete subclass encapsulates the transfer and extraction logic for
    one atlas file format.
    """

    format_id: str = ""
    measure_map: dict[str, str] = {}   # raw stats col -> output col name
    join_on: str = "label"             # "label" for cortical, "index" for volumetric
    commands: list[str] = []           # FreeSurfer commands invoked by this handler

    @abstractmethod
    def transfer(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        overwrite: bool = False,
    ) -> TransferResult:
        """Project the atlas from template space into subject native space."""

    @abstractmethod
    def extract(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        transfer_result: TransferResult,
        force: bool = False,
    ) -> tuple[pd.DataFrame, float | None]:
        """Run the FreeSurfer stats command and return (raw_stats_df, tiv).

        The returned DataFrame contains the raw columns from the .stats file
        (e.g. StructName, ThickAvg …).  Merging with the LUT and producing
        the wide-format output is handled by ``LookupTable.merge_measures``,
        not here.
        """


# ---------------------------------------------------------------------------
# AnnotHandler — FreeSurfer .annot surface atlas
# ---------------------------------------------------------------------------

class AnnotHandler(AtlasFormatHandler):
    """Handler for FreeSurfer .annot surface atlases.

    Transfer: ``mri_surf2surf`` (fsaverage → subject).
    Extract:  ``mris_anatomical_stats`` → cortical .stats file.
    """

    format_id = "annot"
    measure_map = CORTICAL_MEASURES
    join_on = "label"
    commands = ["mri_surf2surf", "mris_anatomical_stats"]

    def transfer(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        overwrite: bool = False,
    ) -> TransferResult:
        if atlas.builtin:
            annot_name = atlas.annot_name
            paths: dict[str, Path] = {}
            for hemi in ("lh", "rh"):
                p = subject.annot_path(hemi, annot_name)
                if not p.exists():
                    raise FileNotFoundError(
                        f"Built-in atlas '{atlas.name}' annot not found at {p}. "
                        f"Was recon-all completed for {subject.subject_id}?"
                    )
                paths[hemi] = p
            return TransferResult(paths=paths, format_id=self.format_id)

        annot_name = _atlas_annot_name(atlas)
        paths = {}
        commands_run: list[list[str]] = []
        for hemi in ("lh", "rh"):
            tgt = subject.label_dir / f"{hemi}.{annot_name}.annot"
            if tgt.exists() and not overwrite:
                logger.info(f"  {hemi}: annot already exists at {tgt}, skipping")
                paths[hemi] = tgt
                continue
            src = atlas.get_file(f"{hemi}.annot")
            logger.info(f"  {hemi}: mri_surf2surf {src} -> {tgt}")
            cmd = [
                "mri_surf2surf",
                "--srcsubject", "fsaverage",
                "--trgsubject", subject.subject_id,
                "--hemi", hemi,
                "--sval-annot", str(src),
                "--tval", str(tgt),
                "--sd", str(env.subjects_dir),
            ]
            commands_run.append(cmd)
            run_command(cmd, env)
            paths[hemi] = tgt

        return TransferResult(paths=paths, format_id=self.format_id, commands_run=commands_run)

    def extract(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        transfer_result: TransferResult,
        force: bool = False,
    ) -> tuple[pd.DataFrame, float | None]:
        frames: list[pd.DataFrame] = []
        tiv: float | None = None

        for hemi, annot_path in transfer_result.paths.items():
            stats_path = _run_anatomical_stats(
                subject=subject,
                env=env,
                hemi=hemi,
                annot_path=annot_path,
                atlas_name=atlas.name,
                force=force,
                command_log=transfer_result.commands_run,
            )
            if tiv is None:
                tiv = _parse_etiv_from_header(stats_path)
            df = _parse_cortical_stats_file(stats_path)
            df["_hemi"] = hemi          # carry hemisphere through for the merge
            frames.append(df)

        if not frames:
            return pd.DataFrame(columns=CORTICAL_COLUMNS), None

        return pd.concat(frames, ignore_index=True), tiv


# ---------------------------------------------------------------------------
# mni152reg helper
# ---------------------------------------------------------------------------

def _ensure_mni152_reg(subject: SubjectPaths, env: FreeSurferEnv) -> list[list[str]]:
    """Run ``mni152reg`` if ``reg.mni152.2mm.dat`` does not already exist.

    ``mni152reg`` registers the MNI152 2mm template to the subject's native
    space via ``fslregister``, producing ``mri/transforms/reg.mni152.2mm.dat``.
    That file is required by ``mri_vol2vol --reg`` to correctly resample
    MNI152 atlases into native space.

    Returns the command list if mni152reg was run, empty list if it was skipped.
    """
    reg_dat = subject.mni152_reg_dat
    if reg_dat.exists():
        logger.info(f"  MNI152 registration already at {reg_dat}, skipping mni152reg")
        return []

    logger.info(f"  Running mni152reg for {subject.subject_id} → {reg_dat}")
    cmd = [
        "mni152reg",
        "--s", subject.subject_id,
    ]
    run_command(cmd, env)
    if not reg_dat.exists():
        raise RuntimeError(
            f"mni152reg completed but {reg_dat} was not created. "
            "Check the mni152reg log in the subject's scripts/ directory."
        )
    return [cmd]


# ---------------------------------------------------------------------------
# NiftiHandler — NIfTI volumetric atlas
# ---------------------------------------------------------------------------

class NiftiHandler(AtlasFormatHandler):
    """Handler for NIfTI volumetric atlases.

    Transfer: ``mni152reg`` (once per subject) + ``mri_vol2vol`` with the
              resulting ``reg.mni152.2mm.dat`` to resample MNI152 atlases into
              native space.
    Extract:  ``mri_segstats`` → volumetric .stats file.
    """

    format_id = "nifti"
    measure_map = VOLUMETRIC_MEASURES
    join_on = "index"
    commands = ["mni152reg", "mri_vol2vol", "mri_segstats"]

    def transfer(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        overwrite: bool = False,
    ) -> TransferResult:
        # aseg is already in subject space — no transfer needed
        if getattr(atlas, "builtin", False) and atlas.name == "aseg":
            return TransferResult(
                paths={"volume": subject.aseg_mgz},
                format_id=self.format_id,
            )

        out_dir = subject.mri_dir / "atlas"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{atlas.name}_native.nii.gz"

        if out_path.exists() and not overwrite:
            if _nifti_shape_matches(out_path, subject.norm_mgz):
                logger.info(f"  Volumetric atlas already at {out_path}, skipping")
                return TransferResult(paths={"volume": out_path}, format_id=self.format_id)
            logger.warning(
                f"  Existing {out_path} has wrong dimensions (stale cache); re-running transfer."
            )

        atlas_space = getattr(atlas, "space", "MNI152NLin2009cAsym")
        src = _get_nifti_file(atlas)
        commands_run: list[list[str]] = []

        if atlas_space in ("MNI152NLin6Asym", "MNI152NLin2009cAsym"):
            # Ensure reg.mni152.2mm.dat exists (run mni152reg if needed).
            # reg.mni152.2mm.dat was produced by fslregister with --mov $mni152
            # --s $subject, so it maps MNI152 (movable) → native (target).
            # mri_vol2vol --reg with this file and no --inv resamples the MNI152
            # atlas into the norm.mgz geometry: for each native output voxel the
            # tool looks up the atlas by applying inv(reg) = native→MNI152.
            commands_run += _ensure_mni152_reg(subject, env)
            reg_arg = ["--reg", str(subject.mni152_reg_dat)]
        elif atlas_space == "MNI305":
            # talairach.xfm maps native → MNI305 (correct direction for --xfm
            # without --inv: the XFM is applied directly as the targ→mov lookup).
            reg_arg = ["--xfm", str(subject.talairach_xfm)]
        else:
            raise ValueError(
                f"Atlas '{atlas.name}' has unsupported space '{atlas_space}' for "
                f"NIfTI volumetric transfer.  Supported: MNI152NLin6Asym, "
                f"MNI152NLin2009cAsym, MNI305."
            )

        logger.info(f"  mri_vol2vol {src} → {out_path} (space: {atlas_space})")
        cmd = [
            "mri_vol2vol",
            "--mov", str(src),
            "--targ", str(subject.norm_mgz),
            *reg_arg,
            "--interp", "nearest",
            "--o", str(out_path),
            "--no-save-reg",
        ]
        run_command(cmd, env)
        commands_run.append(cmd)
        return TransferResult(
            paths={"volume": out_path}, format_id=self.format_id, commands_run=commands_run
        )

    def extract(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        transfer_result: TransferResult,
        force: bool = False,
    ) -> tuple[pd.DataFrame, float | None]:
        seg_path = transfer_result.paths["volume"]
        stats_path = _run_segstats(
            subject=subject,
            env=env,
            seg_path=seg_path,
            atlas_name=atlas.name,
            ctab_path=None,   # ctab built from LUT in pipeline before calling this
            force=force,
            command_log=transfer_result.commands_run,
        )
        tiv = _parse_etiv_from_header(stats_path)
        df = _parse_segstats_file(stats_path)
        return df, tiv


# ---------------------------------------------------------------------------
# DlabelGiiHandler — CIFTI dense label (.dlabel.gii)
# ---------------------------------------------------------------------------

class DlabelGiiHandler(AtlasFormatHandler):
    """Handler for CIFTI .dlabel.gii surface atlases.

    Transfer: convert per-hemisphere to .annot via ``mris_convert``,
              then ``mri_surf2surf`` (fsaverage → subject).
    Extract:  delegates to ``AnnotHandler.extract``.
    """

    format_id = "dlabel_gii"
    measure_map = CORTICAL_MEASURES
    join_on = "label"
    commands = ["mris_convert", "mri_surf2surf", "mris_anatomical_stats"]

    def transfer(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        overwrite: bool = False,
    ) -> TransferResult:
        annot_handler = AnnotHandler()
        annot_paths: dict[str, Path] = {}
        convert_cmds: list[list[str]] = []

        for hemi in ("lh", "rh"):
            dlabel_key = f"{hemi}.dlabel.gii"
            dlabel_src = atlas.get_file(dlabel_key)

            # Convert .dlabel.gii -> .annot in the cache dir
            annot_name = _atlas_annot_name(atlas)
            converted_annot = atlas.cache_dir / f"{hemi}.{annot_name}.annot"
            if not converted_annot.exists() or overwrite:
                logger.info(f"  {hemi}: mris_convert {dlabel_src} -> {converted_annot}")
                sphere = (
                    env.freesurfer_home / "subjects" / "fsaverage" / "surf"
                    / f"{hemi}.sphere.reg"
                )
                cmd = [
                    "mris_convert",
                    "--dlabel-to-annot",
                    str(dlabel_src),
                    str(sphere),
                    str(converted_annot),
                ]
                convert_cmds.append(cmd)
                run_command(cmd, env)
            annot_paths[hemi] = converted_annot

        # Reuse AnnotHandler transfer logic with the converted annot files
        # by building a lightweight proxy that exposes get_file
        proxy = _AnnotProxy(atlas, annot_paths)
        result = annot_handler.transfer(proxy, subject, env, overwrite)
        result.commands_run = convert_cmds + result.commands_run
        return result

    def extract(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        transfer_result: TransferResult,
        force: bool = False,
    ) -> tuple[pd.DataFrame, float | None]:
        return AnnotHandler().extract(atlas, subject, env, transfer_result, force)


class _AnnotProxy:
    """Lightweight proxy that makes a dlabel atlas look like an annot atlas for transfer."""

    def __init__(self, atlas: AnyAtlasSpec, annot_paths: dict[str, Path]) -> None:
        self._atlas = atlas
        self._annot_paths = annot_paths

    def __getattr__(self, item: str):
        return getattr(self._atlas, item)

    def get_file(self, key: str) -> Path:
        if key in self._annot_paths:
            return self._annot_paths[key]
        return self._atlas.get_file(key)


# ---------------------------------------------------------------------------
# GcaHandler — FreeSurfer GCA (Gaussian Classifier Atlas)
# ---------------------------------------------------------------------------

class GcaHandler(AtlasFormatHandler):
    """Handler for FreeSurfer .gca atlas files.

    Transfer: ``mri_ca_label`` (GCA → subject-space segmentation volume).
    Extract:  ``mri_segstats`` → volumetric .stats file.
    """

    format_id = "gca"
    measure_map = VOLUMETRIC_MEASURES
    join_on = "index"
    commands = ["mri_ca_label", "mri_segstats"]

    def transfer(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        overwrite: bool = False,
    ) -> TransferResult:
        out_dir = subject.mri_dir / "atlas"
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / f"{atlas.name}_native.mgz"

        if out_path.exists() and not overwrite:
            logger.info(f"  GCA segmentation already at {out_path}, skipping")
            return TransferResult(paths={"volume": out_path}, format_id=self.format_id)

        gca_file = atlas.get_file(f"{atlas.name}.gca")
        if subject.talairach_m3z.exists():
            transform = subject.talairach_m3z
        elif subject.talairach_xfm.exists():
            logger.warning(
                f"  talairach.m3z not found for {subject.subject_id}; "
                "falling back to talairach.xfm (linear only — accuracy may be reduced)"
            )
            transform = subject.talairach_xfm
        else:
            raise FileNotFoundError(
                f"No Talairach transform found for {subject.subject_id}: "
                f"neither {subject.talairach_m3z} nor {subject.talairach_xfm} exist"
            )
        logger.info(f"  mri_ca_label {gca_file} -> {out_path}")
        cmd = [
            "mri_ca_label",
            str(subject.norm_mgz),
            str(transform),
            str(gca_file),
            str(out_path),
        ]
        run_command(cmd, env)
        return TransferResult(
            paths={"volume": out_path}, format_id=self.format_id, commands_run=[cmd]
        )

    def extract(
        self,
        atlas: AnyAtlasSpec,
        subject: SubjectPaths,
        env: FreeSurferEnv,
        transfer_result: TransferResult,
        force: bool = False,
    ) -> tuple[pd.DataFrame, float | None]:
        seg_path = transfer_result.paths["volume"]
        stats_path = _run_segstats(
            subject=subject,
            env=env,
            seg_path=seg_path,
            atlas_name=atlas.name,
            ctab_path=None,
            force=force,
            command_log=transfer_result.commands_run,
        )
        tiv = _parse_etiv_from_header(stats_path)
        df = _parse_segstats_file(stats_path)
        return df, tiv


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

FORMAT_HANDLERS: dict[str, AtlasFormatHandler] = {
    "annot":       AnnotHandler(),
    "nifti":       NiftiHandler(),
    "dlabel_gii":  DlabelGiiHandler(),
    "gca":         GcaHandler(),
}


def get_handler(format_id: str) -> AtlasFormatHandler:
    """Return the handler for the given format, raising ValueError if unknown."""
    if format_id not in FORMAT_HANDLERS:
        known = ", ".join(FORMAT_HANDLERS)
        raise ValueError(f"Unknown atlas format '{format_id}'. Known: {known}")
    return FORMAT_HANDLERS[format_id]
