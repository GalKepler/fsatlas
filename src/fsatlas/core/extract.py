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
    "normSNR",   # added by --snr
]

VOLUMETRIC_MEASURES: dict[str, str] = {
    "NVoxels": "num_voxels",
    "Volume_mm3": "volume_mm3",
    "normMean": "intensity_mean",
    "normStdDev": "intensity_std",
    "normMin": "intensity_min",
    "normMax": "intensity_max",
    "normRange": "intensity_range",
    "normSNR": "intensity_snr",
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
        "--pv", str(subject.norm_mgz),
        "--excludeid", "0",
        "--etiv",
        "--subcortgray",
        "--snr",
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

# Maps FreeSurfer header Measure short-names to output column names.
# Format differs between tools but the SHORT NAME (2nd field) is consistent:
#   mri_segstats:          # Measure eTIV, eTIV, ...
#   mris_anatomical_stats: # Measure EstimatedTotalIntraCranialVol, eTIV, ...
# Matching on the short name handles both.
_HEADER_MEASURE_MAP: dict[str, str] = {
    # Universal
    "eTIV":                   "tiv_mm3",
    "BrainSegVol":            "brain_seg_vol_mm3",
    "BrainSegVolNotVent":     "brain_seg_no_vent_mm3",
    "SupraTentorialVol":      "supratentorial_vol_mm3",
    # Cortical (mris_anatomical_stats)
    "CortexVol":              "cortex_vol_mm3",
    "WhiteSurfArea":          "white_surf_area_mm2",
    # Subcortical (mri_segstats --subcortgray)
    "SubCortGrayVol":         "subcort_gray_mm3",
}

# Capture the SHORT NAME (2nd token) and the numeric value.
_HEADER_MEASURE_RE = re.compile(r"#\s+Measure\s+\w+,\s*(\w+),\s*.+?,\s*([\d.]+),")


def _parse_header_measures(stats_path: Path) -> dict[str, float]:
    """Extract global header measures from a FreeSurfer stats file.

    Parses all ``# Measure TAG, ...`` lines and returns a dict mapping output
    column names (e.g. ``"tiv_mm3"``) to float values.  Unknown tags are silently
    ignored.  Works for both cortical (.stats from mris_anatomical_stats) and
    volumetric (.stats from mri_segstats) files.
    """
    measures: dict[str, float] = {}
    for line in stats_path.read_text().splitlines():
        m = _HEADER_MEASURE_RE.search(line)
        if m:
            tag, value_str = m.group(1), m.group(2)
            if tag in _HEADER_MEASURE_MAP:
                measures[_HEADER_MEASURE_MAP[tag]] = float(value_str)
    return measures


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
    """Parse a .stats file produced by mri_segstats.

    Handles both the standard 10-column output and the 11-column output
    produced when ``--snr`` is passed (adds ``normSNR`` as the last column).
    """
    if not stats_path.exists():
        raise FileNotFoundError(f"Stats file not found: {stats_path}")
    lines = stats_path.read_text().splitlines()
    data_lines = [ln for ln in lines if ln.strip() and not ln.startswith("#")]
    if not data_lines:
        logger.warning(f"No data rows in {stats_path}")
        return pd.DataFrame(columns=VOLUMETRIC_COLUMNS)
    n_cols = len(data_lines[0].split())
    names = VOLUMETRIC_COLUMNS[:n_cols]
    return pd.read_csv(
        io.StringIO("\n".join(data_lines)),
        sep=r"\s+",
        header=None,
        names=names,
    )
