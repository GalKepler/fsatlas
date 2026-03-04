"""Stats extraction: extract morphometric measures from transferred atlases.

Surface atlases → mris_anatomical_stats → parse .stats file
Volumetric atlases → mri_segstats → parse .stats file

Both are then converted to long-format pandas DataFrames.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

from ..atlases.registry import AtlasSpec, CustomAtlasSpec
from .environment import FreeSurferEnv, SubjectPaths
from .transfer import _atlas_annot_name, _run_fs_command

logger = logging.getLogger(__name__)

AnyAtlasSpec = AtlasSpec | CustomAtlasSpec

# Column names from mris_anatomical_stats output
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

# Measures we pivot into long format
CORTICAL_MEASURES = {
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

# Column names from mri_segstats output
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

VOLUMETRIC_MEASURES = {
    "NVoxels": "num_voxels",
    "Volume_mm3": "volume_mm3",
    "normMean": "intensity_mean",
    "normStdDev": "intensity_std",
    "normMin": "intensity_min",
    "normMax": "intensity_max",
    "normRange": "intensity_range",
}


def extract_cortical_stats(
    atlas: AnyAtlasSpec,
    subject: SubjectPaths,
    env: FreeSurferEnv,
    annot_paths: dict[str, Path],
) -> pd.DataFrame:
    """Extract cortical morphometrics using mris_anatomical_stats.

    Args:
        atlas: The atlas specification.
        subject: Subject paths.
        env: FreeSurfer environment.
        annot_paths: Dict of hemi -> annot path (from transfer step).

    Returns:
        Long-format DataFrame with columns:
        subject_id, atlas, hemisphere, region, measure, value
    """
    frames = []
    tiv: float | None = None

    for hemi, annot_path in annot_paths.items():
        stats_path = _run_anatomical_stats(
            subject=subject,
            env=env,
            hemi=hemi,
            annot_path=annot_path,
            atlas_name=atlas.name,
        )

        if tiv is None:
            tiv = _parse_etiv_from_header(stats_path)

        df = _parse_cortical_stats_file(stats_path)
        df_long = _cortical_to_long_format(
            df,
            subject_id=subject.subject_id,
            atlas_name=atlas.name,
            hemisphere=hemi,
            tiv=tiv,
        )
        frames.append(df_long)

    return pd.concat(frames, ignore_index=True)


def extract_volumetric_stats(
    atlas: AnyAtlasSpec,
    subject: SubjectPaths,
    env: FreeSurferEnv,
    atlas_native_path: Path,
) -> pd.DataFrame:
    """Extract volumetric stats using mri_segstats.

    Args:
        atlas: The atlas specification.
        subject: Subject paths.
        env: FreeSurfer environment.
        atlas_native_path: Path to atlas volume in subject native space.

    Returns:
        Long-format DataFrame with columns:
        subject_id, atlas, hemisphere, region, measure, value
    """
    stats_path = _run_segstats(
        subject=subject,
        env=env,
        seg_path=atlas_native_path,
        atlas_name=atlas.name,
    )

    tiv = _parse_etiv_from_header(stats_path)
    df = _parse_segstats_file(stats_path)
    df_long = _volumetric_to_long_format(
        df,
        subject_id=subject.subject_id,
        atlas_name=atlas.name,
        tiv=tiv,
    )
    return df_long


# ---------------------------------------------------------------------------
# FreeSurfer command runners
# ---------------------------------------------------------------------------


def _run_anatomical_stats(
    subject: SubjectPaths,
    env: FreeSurferEnv,
    hemi: str,
    annot_path: Path,
    atlas_name: str,
) -> Path:
    """Run mris_anatomical_stats and return the output .stats path."""
    stats_dir = subject.stats_dir
    stats_dir.mkdir(exist_ok=True)

    stats_path = stats_dir / f"{hemi}.{atlas_name}.stats"

    logger.info(f"  Running mris_anatomical_stats for {hemi} {atlas_name}")

    cmd = [
        "mris_anatomical_stats",
        "-a", str(annot_path),
        "-f", str(stats_path),
        "-b",  # include total brain volume in header
        subject.subject_id,
        hemi,
    ]

    _run_fs_command(cmd, env)
    return stats_path


def _run_segstats(
    subject: SubjectPaths,
    env: FreeSurferEnv,
    seg_path: Path,
    atlas_name: str,
) -> Path:
    """Run mri_segstats and return the output .stats path."""
    stats_dir = subject.stats_dir
    stats_dir.mkdir(exist_ok=True)

    stats_path = stats_dir / f"{atlas_name}.subcortical.stats"

    logger.info(f"  Running mri_segstats for {atlas_name}")

    cmd = [
        "mri_segstats",
        "--seg", str(seg_path),
        "--in", str(subject.norm_mgz),  # intensity source
        "--excludeid", "0",  # exclude background
        "--etiv",  # include eTIV in header
        "--sum", str(stats_path),
        "--subject", subject.subject_id,
    ]

    _run_fs_command(cmd, env)
    return stats_path


# ---------------------------------------------------------------------------
# Stats file parsers
# ---------------------------------------------------------------------------


def _parse_etiv_from_header(stats_path: Path) -> float | None:
    """Extract eTIV from the '# Measure eTIV, ..., VALUE, mm^3' header line."""
    for line in stats_path.read_text().splitlines():
        # e.g. "# Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1234567.0, mm^3"
        m = re.match(r"#\s+Measure\s+eTIV\s*,.*,\s*([\d.]+)\s*,\s*mm\^3", line)
        if m:
            return float(m.group(1))
    return None


def _parse_cortical_stats_file(stats_path: Path) -> pd.DataFrame:
    """Parse a .stats file produced by mris_anatomical_stats.

    The file has comment lines starting with '#' and a table header line
    starting with '# ColHeaders'. Data lines follow without '#'.
    """
    if not stats_path.exists():
        raise FileNotFoundError(f"Stats file not found: {stats_path}")

    lines = stats_path.read_text().splitlines()

    # Find the data lines (non-comment, non-empty)
    data_lines = [l for l in lines if l.strip() and not l.startswith("#")]

    if not data_lines:
        logger.warning(f"No data rows in {stats_path}")
        return pd.DataFrame(columns=CORTICAL_COLUMNS)

    # Parse whitespace-delimited data
    df = pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=r"\s+",
        header=None,
        names=CORTICAL_COLUMNS,
    )
    return df


def _parse_segstats_file(stats_path: Path) -> pd.DataFrame:
    """Parse a .stats file produced by mri_segstats.

    Similar format: comments with '#', ColHeaders line, then data.
    """
    if not stats_path.exists():
        raise FileNotFoundError(f"Stats file not found: {stats_path}")

    lines = stats_path.read_text().splitlines()
    data_lines = [l for l in lines if l.strip() and not l.startswith("#")]

    if not data_lines:
        logger.warning(f"No data rows in {stats_path}")
        return pd.DataFrame(columns=VOLUMETRIC_COLUMNS)

    df = pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=r"\s+",
        header=None,
        names=VOLUMETRIC_COLUMNS,
    )
    return df


# ---------------------------------------------------------------------------
# Long-format converters
# ---------------------------------------------------------------------------


def _cortical_to_long_format(
    df: pd.DataFrame,
    subject_id: str,
    atlas_name: str,
    hemisphere: str,
    tiv: float | None,
) -> pd.DataFrame:
    """Convert wide cortical stats to long format."""
    records = []
    for _, row in df.iterrows():
        region = row["StructName"]
        for col, measure_name in CORTICAL_MEASURES.items():
            value = row.get(col, np.nan)
            records.append(
                {
                    "subject_id": subject_id,
                    "atlas": atlas_name,
                    "hemisphere": hemisphere,
                    "region": region,
                    "measure": measure_name,
                    "value": float(value),
                    "tiv_mm3": tiv,
                }
            )
    return pd.DataFrame(records)


def _volumetric_to_long_format(
    df: pd.DataFrame,
    subject_id: str,
    atlas_name: str,
    tiv: float | None,
) -> pd.DataFrame:
    """Convert wide volumetric stats to long format."""
    records = []
    for _, row in df.iterrows():
        region = row["StructName"]
        # Try to infer hemisphere from region name
        hemisphere = _infer_hemisphere(region)
        for col, measure_name in VOLUMETRIC_MEASURES.items():
            value = row.get(col, np.nan)
            records.append(
                {
                    "subject_id": subject_id,
                    "atlas": atlas_name,
                    "hemisphere": hemisphere,
                    "region": region,
                    "measure": measure_name,
                    "value": float(value),
                    "tiv_mm3": tiv,
                }
            )
    return pd.DataFrame(records)


def _infer_hemisphere(region_name: str) -> str:
    """Infer hemisphere from region name conventions."""
    name_lower = region_name.lower()
    if name_lower.startswith(("lh_", "lh-", "left_", "left-", "l_")):
        return "lh"
    if name_lower.startswith(("rh_", "rh-", "right_", "right-", "r_")):
        return "rh"
    if "_lh_" in name_lower or "-lh-" in name_lower:
        return "lh"
    if "_rh_" in name_lower or "-rh-" in name_lower:
        return "rh"
    # Tian atlas uses "-lh" / "-rh" suffixes
    if name_lower.endswith(("-lh", "_lh")):
        return "lh"
    if name_lower.endswith(("-rh", "_rh")):
        return "rh"
    return "bilateral"
