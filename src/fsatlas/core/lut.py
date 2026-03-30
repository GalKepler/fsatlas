"""LookupTable: the canonical mapping from integer index to region label.

Every atlas must have an associated LUT. The LUT drives:
  - the output schema (one row per region)
  - the ctab file passed to mri_segstats
  - hemisphere inference when not explicitly stored
"""

from __future__ import annotations

import gzip
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Minimum required columns (BIDS-inspired).
# Extra columns in the TSV (e.g. network, color_r/g/b) are preserved as-is.
_INDEX_COL = "index"
_LABEL_COL = "label"
_HEMI_COL = "hemisphere"

REQUIRED_COLS = [_INDEX_COL, _LABEL_COL, _HEMI_COL]


# ---------------------------------------------------------------------------
# Hemisphere inference (moved from extract.py)
# ---------------------------------------------------------------------------

def _infer_hemisphere(label: str) -> str:
    """Infer hemisphere from common naming conventions."""
    n = label.lower()
    if n.startswith(("lh_", "lh-", "left_", "left-", "l_")):
        return "lh"
    if n.startswith(("rh_", "rh-", "right_", "right-", "r_")):
        return "rh"
    if "_lh_" in n or "-lh-" in n:
        return "lh"
    if "_rh_" in n or "-rh-" in n:
        return "rh"
    if n.endswith(("-lh", "_lh", "-left", "_left", "-l", "_l")):
        return "lh"
    if n.endswith(("-rh", "_rh", "-right", "_right", "-r", "_r")):
        return "rh"
    return "bilateral"


# ---------------------------------------------------------------------------
# LookupTable
# ---------------------------------------------------------------------------

@dataclass
class LookupTable:
    """An atlas lookup table: maps integer indices to region labels.

    ``df`` must contain at least the columns ``index`` (int), ``label`` (str),
    and ``hemisphere`` (str).  Any extra columns present in the source TSV
    (e.g. *network*, *color_r*, *color_g*, *color_b*) are preserved and will
    appear in the merged output DataFrames.
    """

    df: pd.DataFrame

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_tsv(cls, path: Path) -> LookupTable:
        """Load a LUT from a TSV file.

        Handles three layouts (auto-detected):

        1. **Header row** — file starts with a tab-separated header that
           includes at least ``index`` and ``label`` columns.
        2. **Two-column headerless** — ``index<whitespace>label`` per line
           (e.g. ``1 Precentral_L``).
        3. **Name-only headerless** — one label per line; indices assigned
           as 1-based line numbers.

        All formats may optionally include a ``hemisphere`` column; if absent,
        hemisphere is inferred from the label name.
        """
        raw = path.read_bytes()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        text = raw.decode("utf-8", errors="replace")

        lines = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        if not lines:
            raise ValueError(f"LUT file is empty: {path}")

        # --- Attempt 1: TSV with header ---
        first = lines[0]
        if "\t" in first or re.match(r"^index\b", first, re.IGNORECASE):
            try:
                df = pd.read_csv(path, sep=r"\s+", comment="#")
                df.columns = [c.lower().strip() for c in df.columns]
                if _INDEX_COL in df.columns and _LABEL_COL in df.columns:
                    return cls._finalise(df)
            except Exception:
                pass  # fall through to heuristic parsing

        # --- Attempt 2 / 3: headerless ---
        entries: list[dict] = []
        for lineno, line in enumerate(lines, start=1):
            parts = line.split()
            try:
                idx = int(parts[0])
                label = parts[1] if len(parts) > 1 else f"region_{idx}"
            except (ValueError, IndexError):
                idx = lineno
                label = parts[0]
            entries.append({_INDEX_COL: idx, _LABEL_COL: label})

        df = pd.DataFrame(entries)
        return cls._finalise(df)

    @classmethod
    def from_annot(cls, lh_annot: Path, rh_annot: Path) -> LookupTable:
        """Extract a LUT from a pair of FreeSurfer .annot files.

        Uses ``nibabel.freesurfer.read_annot`` to read the embedded colour
        table.  The two hemispheres are merged; duplicate labels (same name in
        both) get a ``bilateral`` hemisphere.
        """
        import nibabel.freesurfer as nfs

        rows: list[dict] = []
        seen: dict[str, dict] = {}

        for hemi, annot_path in (("lh", lh_annot), ("rh", rh_annot)):
            _, ctab, names = nfs.read_annot(str(annot_path))
            # ctab shape: (n_labels, 5) — R G B A index
            for i, raw_name in enumerate(names):
                label = raw_name.decode() if isinstance(raw_name, bytes) else raw_name
                if label in ("unknown", "???", ""):
                    continue
                idx = int(ctab[i, 4]) if ctab is not None and i < len(ctab) else i
                entry = {
                    _INDEX_COL: idx,
                    _LABEL_COL: label,
                    _HEMI_COL: hemi,
                }
                if label in seen and seen[label][_HEMI_COL] != hemi:
                    seen[label][_HEMI_COL] = "bilateral"
                else:
                    seen[label] = entry
                    rows.append(entry)
        df = pd.DataFrame(rows).drop_duplicates(subset=[_INDEX_COL, _LABEL_COL])
        df = df.sort_values(_INDEX_COL).reset_index(drop=True)
        df["hemi"] = df[_LABEL_COL].map(_infer_hemisphere)
        return cls(df=df)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _finalise(cls, df: pd.DataFrame) -> LookupTable:
        """Ensure required columns exist, cast types, infer hemisphere."""
        if _HEMI_COL not in df.columns:
            df[_HEMI_COL] = df[_LABEL_COL].map(_infer_hemisphere)
        df[_INDEX_COL] = df[_INDEX_COL].astype(int)
        df[_LABEL_COL] = df[_LABEL_COL].astype(str)
        df[_HEMI_COL] = df[_HEMI_COL].astype(str)
        return cls(df=df.reset_index(drop=True))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def to_tsv(self, path: Path) -> None:
        """Write the LUT to a tab-separated file with a header row."""
        self.df.to_csv(path, sep="\t", index=False)

    def to_ctab(self) -> Path:
        """Write a FreeSurfer colour table (.ctab) to a temp file and return its path.

        Format: ``index label R G B A`` — colours are neutral grey (irrelevant
        for stats extraction).

        The caller is responsible for deleting the temp file when done.
        """
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".ctab", delete=False, prefix="fsatlas_"
        )
        for _, row in self.df.iterrows():
            r = int(row.get("color_r", 100))
            g = int(row.get("color_g", 100))
            b = int(row.get("color_b", 100))
            a = int(row.get("color_a", 0))
            tmp.write(f"{row[_INDEX_COL]} {row[_LABEL_COL]} {r} {g} {b} {a}\n")
        tmp.close()
        return Path(tmp.name)

    # ------------------------------------------------------------------
    # Merging extracted stats
    # ------------------------------------------------------------------

    def merge_measures(
        self,
        raw_stats: pd.DataFrame,
        subject_id: str,
        tiv: float | None,
        measure_map: dict[str, str],
        join_on: str = "label",
    ) -> pd.DataFrame:
        """Merge extracted .stats data onto the LUT, returning a wide-format DataFrame.

        Parameters
        ----------
        raw_stats:
            DataFrame parsed from a FreeSurfer .stats file.  Must contain a
            ``StructName`` column (for label-based joins) or a ``SegId`` column
            (for index-based joins).
        subject_id:
            Subject identifier to add as the first column.
        tiv:
            Estimated total intracranial volume (mm³), or None.
        measure_map:
            Mapping from raw_stats column names to output measure column names.
            E.g. ``{"ThickAvg": "thickness_mean_mm", ...}``.
        join_on:
            ``"label"`` to join on region name (cortical), or ``"index"`` to
            join on integer segment ID (volumetric).

        Returns
        -------
        Wide-format DataFrame:
            ``subject_id | index | label | hemisphere | [extra LUT cols] | measure1 | ...
            | tiv_mm3``
        """
        lut_df = self.df.copy()

        if join_on == "label":
            # Join on StructName ↔ label
            stats = raw_stats.rename(columns={"StructName": _LABEL_COL})
            measure_cols = [c for c in measure_map if c in stats.columns]
            stats_slim = stats[[_LABEL_COL] + measure_cols].copy()
            stats_slim = stats_slim.rename(columns=measure_map)
            merged = lut_df.merge(stats_slim, on=_LABEL_COL, how="left")
        else:
            # Join on SegId ↔ index
            stats = raw_stats.rename(columns={"SegId": _INDEX_COL})
            measure_cols = [c for c in measure_map if c in raw_stats.columns]
            stats_slim = stats[[_INDEX_COL] + measure_cols].copy()
            stats_slim = stats_slim.rename(columns=measure_map)
            merged = lut_df.merge(stats_slim, on=_INDEX_COL, how="left")

        # Cast renamed measure columns to float
        for out_col in measure_map.values():
            if out_col in merged.columns:
                merged[out_col] = pd.to_numeric(merged[out_col], errors="coerce")

        merged.insert(0, "subject_id", subject_id)
        merged["tiv_mm3"] = tiv if tiv is not None else np.nan
        return merged
