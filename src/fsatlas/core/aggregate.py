"""Aggregate per-subject BIDS CSV outputs into a single wide-format table."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from .extract import CORTICAL_MEASURES, VOLUMETRIC_MEASURES

logger = logging.getLogger(__name__)

# Universal ID columns kept from every CSV (atlas-specific extras are dropped)
_ID_COLS = ["subject_id", "index", "label", "hemisphere"]

# Known measure column sets by structure type
_CORTICAL_MEASURE_COLS: frozenset[str] = frozenset(CORTICAL_MEASURES.values())
_SUBCORTICAL_MEASURE_COLS: frozenset[str] = frozenset(VOLUMETRIC_MEASURES.values())

# Filename patterns produced by bids.py:build_bids_path
# With session:    sub-{sub}_ses-{ses}_atlas-{atlas}_structure-{structure}.csv
# Without session: sub-{sub}_atlas-{atlas}_structure-{structure}.csv
_BIDS_FNAME_RE = re.compile(
    r"^sub-(?P<sub>[a-zA-Z0-9.]+)"
    r"(?:_ses-(?P<ses>[a-zA-Z0-9.]+))?"
    r"_atlas-(?P<atlas>[a-zA-Z0-9]+)"
    r"_structure-(?P<structure>cortex|subcortex)"
    r"\.csv$"
)


def discover_atlases(bids_dir: Path) -> list[str]:
    """Return sorted list of atlas names found in a BIDS output directory.

    Scans for ``atlas-{name}`` directories under ``sub-*/[ses-*/]anat/``.
    """
    names: set[str] = set()
    for pattern in ("sub-*/anat/atlas-*", "sub-*/ses-*/anat/atlas-*"):
        for atlas_dir in bids_dir.glob(pattern):
            if atlas_dir.is_dir():
                names.add(atlas_dir.name.split("atlas-", 1)[1])
    return sorted(names)


def discover_csv_files(
    bids_dir: Path,
    atlas: str,
    structure: str | None = None,
    subjects: list[str] | None = None,
) -> list[Path]:
    """Find CSV files for *atlas*, optionally filtered by structure and subjects.

    Searches both session and no-session layouts.

    Parameters
    ----------
    bids_dir:
        Root BIDS output directory.
    atlas:
        Atlas name as it appears in ``atlas-{name}`` directory components.
    structure:
        ``"cortex"``, ``"subcortex"``, or ``None`` for both.
    subjects:
        Subject labels (without ``sub-`` prefix) to include. ``None`` means all.
    """
    struct_glob = f"*_structure-{structure}.csv" if structure else "*_structure-*.csv"
    patterns = [
        f"sub-*/anat/atlas-{atlas}/{struct_glob}",
        f"sub-*/ses-*/anat/atlas-{atlas}/{struct_glob}",
    ]

    paths: list[Path] = []
    for pattern in patterns:
        for p in sorted(bids_dir.glob(pattern)):
            if p.is_file():
                if subjects is not None:
                    # Extract sub label from the immediate sub-* directory component
                    sub_dir = next(part for part in p.parts if part.startswith("sub-"))
                    sub_label = sub_dir[4:]  # strip "sub-"
                    if sub_label not in subjects:
                        continue
                paths.append(p)
    return paths


def _parse_entities_from_path(csv_path: Path) -> dict[str, str | None]:
    """Extract BIDS entities from a CSV filename.

    Returns dict with keys ``sub``, ``ses`` (or ``None``), ``atlas``, ``structure``.
    """
    m = _BIDS_FNAME_RE.match(csv_path.name)
    if not m:
        raise ValueError(f"Cannot parse BIDS entities from filename: {csv_path.name!r}")
    return {
        "sub": m.group("sub"),
        "ses": m.group("ses"),
        "atlas": m.group("atlas"),
        "structure": m.group("structure"),
    }


def _standardize_dataframe(
    df: pd.DataFrame,
    structure: str,
    atlas: str,
    session: str | None,
) -> pd.DataFrame:
    """Normalise a per-subject wide CSV to the canonical aggregated schema.

    Keeps universal ID columns, known measure columns, and ``tiv_mm3``.
    Injects ``session``, ``atlas``, and ``structure`` metadata columns.
    Atlas-specific extras (e.g. ``hemi``, ``name``, ``brainnetome246ext_index``)
    are silently dropped.
    """
    known_measures = (
        _CORTICAL_MEASURE_COLS if structure == "cortex" else _SUBCORTICAL_MEASURE_COLS
    )
    _GLOBAL_MEASURE_COLS = [
        "tiv_mm3",
        "brain_seg_vol_mm3",
        "brain_seg_no_vent_mm3",
        "supratentorial_vol_mm3",
        "cortex_vol_mm3",
        "white_surf_area_mm2",
        "total_gray_mm3",
        "subcort_gray_mm3",
    ]
    keep_cols = (
        [c for c in _ID_COLS if c in df.columns]
        + [c for c in df.columns if c in known_measures]
        + [c for c in _GLOBAL_MEASURE_COLS if c in df.columns]
    )
    out = df[keep_cols].copy().rename(columns={"gray_matter_volume_mm3": "volume_mm3"})

    # Insert metadata columns right after subject_id
    insert_at = 1
    out.insert(insert_at, "structure", structure)
    out.insert(insert_at, "atlas", atlas)
    out.insert(insert_at, "session", session)

    return out


def aggregate(
    bids_dir: Path,
    atlas: str,
    structures: list[str] | None = None,
    subjects: list[str] | None = None,
) -> pd.DataFrame:
    """Aggregate per-subject BIDS CSVs into a single wide-format DataFrame.

    Parameters
    ----------
    bids_dir:
        Root BIDS output directory.
    atlas:
        Atlas name (as in ``atlas-{name}`` directories).
    structures:
        List of ``"cortex"`` and/or ``"subcortex"`` to include. Defaults to both.
    subjects:
        Subject labels (without ``sub-`` prefix) to include. ``None`` means all.

    Returns
    -------
    Wide-format DataFrame sorted by subject_id, session, structure, index.
    Returns an empty DataFrame if no matching files are found.
    """
    if structures is None:
        structures = ["cortex", "subcortex"]

    frames: list[pd.DataFrame] = []
    for structure in structures:
        csv_files = discover_csv_files(bids_dir, atlas, structure, subjects)
        if not csv_files:
            logger.info("No %s files found for atlas %r.", structure, atlas)
            continue

        for csv_path in csv_files:
            try:
                entities = _parse_entities_from_path(csv_path)
            except ValueError as exc:
                logger.warning("Skipping %s: %s", csv_path, exc)
                continue

            try:
                df = pd.read_csv(csv_path)
            except Exception as exc:
                logger.warning("Could not read %s: %s", csv_path, exc)
                continue

            if df.empty:
                logger.info("Skipping empty file: %s", csv_path)
                continue

            frames.append(
                _standardize_dataframe(df, structure, entities["atlas"], entities["ses"])
            )

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    sort_cols = [c for c in ["subject_id", "session", "structure", "index"] if c in result.columns]
    return result.sort_values(sort_cols).reset_index(drop=True)
