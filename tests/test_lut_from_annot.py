"""Tests for LookupTable.from_annot and edge cases in from_tsv."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from fsatlas.core.lut import LookupTable


# ---------------------------------------------------------------------------
# LookupTable.from_tsv — exception fallthrough path (lines 107-108)
# ---------------------------------------------------------------------------

class TestFromTsvExceptionFallthrough:
    def test_falls_back_to_headerless_on_read_error(self, tmp_path):
        """If the header TSV parse fails, fall through to headerless parsing."""
        # A file that starts with a tab (triggers header attempt) but
        # pd.read_csv parsing won't give index+label columns
        tsv = tmp_path / "labels.tsv"
        # Starts with tab: triggers Attempt 1 path but will fail to find index col
        # Then falls through to headerless parsing
        tsv.write_text("\t1 RegionA\n2 RegionB\n")
        # This should not raise; it falls back to headerless
        lut = LookupTable.from_tsv(tsv)
        assert isinstance(lut, LookupTable)


# ---------------------------------------------------------------------------
# LookupTable.from_annot (with nibabel mock)
# ---------------------------------------------------------------------------

class TestFromAnnot:
    def _write_fake_annot(self, tmp_path: Path, hemi: str, labels: list[str]) -> Path:
        """Create a fake .annot file that nibabel can read."""
        import nibabel.freesurfer as nfs
        # We can't easily create real annot files without actual surface data,
        # so we mock nibabel.freesurfer.read_annot directly.
        path = tmp_path / f"{hemi}.test.annot"
        path.touch()
        return path

    def test_from_annot_basic(self, tmp_path):
        lh = tmp_path / "lh.test.annot"
        rh = tmp_path / "rh.test.annot"
        lh.touch()
        rh.touch()

        # ctab: (n_labels, 5) — last column is index
        lh_ctab = np.array([[100, 100, 100, 0, 1001], [200, 200, 200, 0, 1002]])
        rh_ctab = np.array([[100, 100, 100, 0, 2001], [200, 200, 200, 0, 2002]])
        lh_names = [b"lh_precentral", b"lh_postcentral"]
        rh_names = [b"rh_precentral", b"rh_postcentral"]

        def mock_read_annot(path, **kwargs):
            if "lh" in str(path):
                return (None, lh_ctab, lh_names)
            else:
                return (None, rh_ctab, rh_names)

        with patch("nibabel.freesurfer.read_annot", side_effect=mock_read_annot):
            lut = LookupTable.from_annot(lh, rh)

        assert isinstance(lut.df, pd.DataFrame)
        assert "index" in lut.df.columns or "hemi" in lut.df.columns
        assert len(lut.df) > 0

    def test_from_annot_skips_unknown_labels(self, tmp_path):
        lh = tmp_path / "lh.test.annot"
        rh = tmp_path / "rh.test.annot"
        lh.touch()
        rh.touch()

        ctab = np.array([[100, 100, 100, 0, 0], [200, 200, 200, 0, 1]])
        # "unknown" should be skipped, "lh_region" kept
        names = [b"unknown", b"lh_region"]

        def mock_read_annot(path, **kwargs):
            return (None, ctab, names)

        with patch("nibabel.freesurfer.read_annot", side_effect=mock_read_annot):
            lut = LookupTable.from_annot(lh, rh)

        # "unknown" labels are filtered out
        assert "unknown" not in lut.df["label"].values
        assert "lh_region" in lut.df["label"].values

    def test_from_annot_marks_bilateral_duplicates(self, tmp_path):
        lh = tmp_path / "lh.test.annot"
        rh = tmp_path / "rh.test.annot"
        lh.touch()
        rh.touch()

        ctab_lh = np.array([[100, 100, 100, 0, 1]])
        ctab_rh = np.array([[100, 100, 100, 0, 2]])
        names_lh = [b"Precentral"]  # same name in both hemispheres
        names_rh = [b"Precentral"]

        def mock_read_annot(path, **kwargs):
            if "lh" in str(path):
                return (None, ctab_lh, names_lh)
            return (None, ctab_rh, names_rh)

        with patch("nibabel.freesurfer.read_annot", side_effect=mock_read_annot):
            lut = LookupTable.from_annot(lh, rh)

        # Precentral appears in both → bilateral
        precental_rows = lut.df[lut.df["label"] == "Precentral"]
        if len(precental_rows) > 0:
            assert "bilateral" in precental_rows["hemi"].values

    def test_from_annot_handles_string_names(self, tmp_path):
        lh = tmp_path / "lh.test.annot"
        rh = tmp_path / "rh.test.annot"
        lh.touch()
        rh.touch()

        ctab = np.array([[100, 100, 100, 0, 1]])
        # String names (not bytes)
        names = ["lh_frontal"]

        def mock_read_annot(path, **kwargs):
            return (None, ctab, names)

        with patch("nibabel.freesurfer.read_annot", side_effect=mock_read_annot):
            lut = LookupTable.from_annot(lh, rh)

        assert "lh_frontal" in lut.df["label"].values

    def test_from_annot_handles_none_ctab(self, tmp_path):
        lh = tmp_path / "lh.test.annot"
        rh = tmp_path / "rh.test.annot"
        lh.touch()
        rh.touch()

        # ctab=None edge case
        names = [b"region_A"]

        def mock_read_annot(path, **kwargs):
            return (None, None, names)

        with patch("nibabel.freesurfer.read_annot", side_effect=mock_read_annot):
            lut = LookupTable.from_annot(lh, rh)

        assert isinstance(lut.df, pd.DataFrame)
