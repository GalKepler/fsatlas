"""Stats extraction utilities: run FreeSurfer stats commands and parse their output.

The public functions ``extract_cortical_stats`` / ``extract_volumetric_stats``
are kept for backward compatibility but the primary dispatch path now goes
through ``formats.py`` handlers, which call the private helpers directly.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import pandas as pd

from .command import run_command
from .environment import FreeSurferEnv, SubjectPaths

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

CORTICAL_COLUMNS = [
    "StructName",
    "NumVert",
    "SurfArea",
    "GrayVol",
    "ThickAvg",
    "ThickStd",
    "MeanCurv",
    "GausCurv",
    "FoldInd",
    "CurvInd",
]

# Maps raw .stats column names to BIDS-inspired output column names
CORTICAL_MEASURES: dict[str, str] = {
    "NumVert": "num_vertices",
    "SurfArea": "surface_area_mm2",
    "GrayVol": "gray_matter_volume_mm3",
    "ThickAvg": "thickness_mean_mm",
    "ThickStd": "thickness_std_mm",
    "MeanCurv": "mean_curvature",
    "GausCurv": "gaussian_curvature",
    "FoldInd": "folding_index",
    "CurvInd": "curvature_index",
}

VOLUMETRIC_COLUMNS = [
    "Index",
    "SegId",
    "NVoxels",
    "Volume_mm3",
    "StructName",
    "normMean",
    "normStdDev",
    "normMin",
    "normMax",
    "normRange",
]

VOLUMETRIC_MEASURES: dict[str, str] = {
    "NVoxels": "num_voxels",
    "Volume_mm3": "volume_mm3",
    "normMean": "intensity_mean",
    "normStdDev": "intensity_std",
    "normMin": "intensity_min",
    "normMax": "intensity_max",
    "normRange": "intensity_range",
}


# ---------------------------------------------------------------------------
# FreeSurfer command runners
# ---------------------------------------------------------------------------

def _run_anatomical_stats(
    subject: SubjectPaths,
    env: FreeSurferEnv,
    hemi: str,
    annot_path: Path,
    atlas_name: str,
    force: bool = False,
    command_log: list[list[str]] | None = None,
) -> Path:
    """Run mris_anatomical_stats and return the output .stats path."""
    stats_dir = subject.stats_dir
    stats_dir.mkdir(exist_ok=True)
    stats_path = stats_dir / f"{hemi}.{atlas_name}.stats"

    if stats_path.exists() and not force:
        logger.info(f"  Stats already exist at {stats_path}, skipping (use --force to recompute)")
        return stats_path

    logger.info(f"  Running mris_anatomical_stats for {hemi} {atlas_name}")
    cmd = [
        "mris_anatomical_stats",
        "-a", str(annot_path),
        "-f", str(stats_path),
        "-b",
        "-sdir", str(env.subjects_dir),
        subject.subject_id,
        hemi,
    ]
    if command_log is not None:
        command_log.append(cmd)
    run_command(cmd, env)
    return stats_path


def _run_segstats(
    subject: SubjectPaths,
    env: FreeSurferEnv,
    seg_path: Path,
    atlas_name: str,
    ctab_path: Path | None = None,
    force: bool = False,
    command_log: list[list[str]] | None = None,
) -> Path:
    """Run mri_segstats and return the output .stats path."""
    stats_dir = subject.stats_dir
    stats_dir.mkdir(exist_ok=True)
    stats_path = stats_dir / f"{atlas_name}.subcortical.stats"

    if stats_path.exists() and not force:
        logger.info(f"  Stats already exist at {stats_path}, skipping (use --force to recompute)")
        return stats_path

    logger.info(f"  Running mri_segstats for {atlas_name}")
    cmd = [
        "mri_segstats",
        "--seg", str(seg_path),
        "--i", str(subject.norm_mgz),
        "--excludeid", "0",
        "--etiv",
        "--sum", str(stats_path),
        "--subject", subject.subject_id,
        "--sd", str(env.subjects_dir),
    ]
    if ctab_path is not None:
        cmd += ["--ctab", str(ctab_path)]
    if command_log is not None:
        command_log.append(cmd)
    run_command(cmd, env)
    return stats_path


# ---------------------------------------------------------------------------
# Stats file parsers
# ---------------------------------------------------------------------------

def _parse_etiv_from_header(stats_path: Path) -> float | None:
    """Extract eTIV from the stats file header (works for both cortical and volumetric)."""
    for line in stats_path.read_text().splitlines():
        m = re.search(r"Measure\s+\w+,\s*eTIV\s*,.*,\s*([\d.]+)\s*,\s*mm\^3", line)
        if m:
            return float(m.group(1))
    return None


def _parse_cortical_stats_file(stats_path: Path) -> pd.DataFrame:
    """Parse a .stats file produced by mris_anatomical_stats."""
    if not stats_path.exists():
        raise FileNotFoundError(f"Stats file not found: {stats_path}")
    lines = stats_path.read_text().splitlines()
    data_lines = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    if not data_lines:
        logger.warning(f"No data rows in {stats_path}")
        return pd.DataFrame(columns=CORTICAL_COLUMNS)
    return pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=r"\s+",
        header=None,
        names=CORTICAL_COLUMNS,
    )


def _parse_segstats_file(stats_path: Path) -> pd.DataFrame:
    """Parse a .stats file produced by mri_segstats."""
    if not stats_path.exists():
        raise FileNotFoundError(f"Stats file not found: {stats_path}")
    lines = stats_path.read_text().splitlines()
    data_lines = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    if not data_lines:
        logger.warning(f"No data rows in {stats_path}")
        return pd.DataFrame(columns=VOLUMETRIC_COLUMNS)
    return pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=r"\s+",
        header=None,
        names=VOLUMETRIC_COLUMNS,
    )
