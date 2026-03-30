"""Tests for remaining uncovered paths in formats.py."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import nibabel as nib
import pytest

from fsatlas.core.formats import (
    DlabelGiiHandler,
    GcaHandler,
    NiftiHandler,
    TransferResult,
)


def _make_nifti(path: Path, shape=(10, 10, 10)) -> None:
    img = nib.Nifti1Image(np.zeros(shape), np.eye(4))
    nib.save(img, str(path))


SEGSTATS = textwrap.dedent("""\
    # Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1600000.0, mm^3
    1 10 500 450.0 Left-Putamen 90.5 8.2 60.0 120.0 60.0
""")


# ---------------------------------------------------------------------------
# NiftiHandler.transfer — stale cache warning (shape mismatch)
# ---------------------------------------------------------------------------

class TestNiftiHandlerStaleCacheWarning:
    def test_reruns_transfer_when_shape_mismatch(self, tmp_path, caplog):
        import logging
        handler = NiftiHandler()
        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myvol"

        mri_dir = tmp_path / "mri"
        atlas_dir = mri_dir / "atlas"
        atlas_dir.mkdir(parents=True)

        # norm_mgz with shape (10, 10, 10)
        norm_mgz = mri_dir / "norm.mgz"
        _make_nifti(norm_mgz, shape=(10, 10, 10))

        # Pre-existing output with DIFFERENT shape (stale)
        out_path = atlas_dir / "myvol_native.nii.gz"
        _make_nifti(out_path, shape=(20, 20, 20))

        nii_path = tmp_path / "atlas.nii.gz"
        _make_nifti(nii_path)

        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.norm_mgz = norm_mgz

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            with patch("fsatlas.core.formats._get_nifti_file", return_value=nii_path):
                with caplog.at_level(logging.WARNING, logger="fsatlas.core.formats"):
                    result = handler.transfer(atlas, subject, MagicMock(), overwrite=False)

        # Should have re-run the command
        mock_cmd.assert_called_once()
        assert any("stale cache" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# GcaHandler.transfer — with m3z transform (preferred)
# ---------------------------------------------------------------------------

class TestGcaHandlerTransferWithTransforms:
    def _make_gca_atlas(self, tmp_path: Path) -> MagicMock:
        gca_file = tmp_path / "myatlas.gca"
        gca_file.touch()
        atlas = MagicMock()
        atlas.name = "myatlas"
        atlas.builtin = False
        atlas.get_file.return_value = gca_file
        return atlas

    def _make_subject_with_m3z(self, tmp_path: Path) -> MagicMock:
        mri_dir = tmp_path / "mri"
        transforms = mri_dir / "transforms"
        transforms.mkdir(parents=True)
        atlas_dir = mri_dir / "atlas"
        atlas_dir.mkdir()
        m3z = transforms / "talairach.m3z"
        m3z.touch()
        norm = mri_dir / "norm.mgz"
        norm.touch()
        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.talairach_m3z = m3z
        subject.talairach_xfm = transforms / "talairach.xfm"  # doesn't exist
        subject.norm_mgz = norm
        return subject

    def _make_subject_with_xfm_only(self, tmp_path: Path) -> MagicMock:
        mri_dir = tmp_path / "mri"
        transforms = mri_dir / "transforms"
        transforms.mkdir(parents=True)
        atlas_dir = mri_dir / "atlas"
        atlas_dir.mkdir()
        xfm = transforms / "talairach.xfm"
        xfm.touch()
        norm = mri_dir / "norm.mgz"
        norm.touch()
        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.talairach_m3z = transforms / "talairach.m3z"  # doesn't exist
        subject.talairach_xfm = xfm
        subject.norm_mgz = norm
        return subject

    def test_uses_m3z_when_available(self, tmp_path):
        handler = GcaHandler()
        atlas = self._make_gca_atlas(tmp_path)
        subject = self._make_subject_with_m3z(tmp_path)

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        mock_cmd.assert_called_once()
        cmd = mock_cmd.call_args[0][0]
        assert "talairach.m3z" in " ".join(cmd)

    def test_falls_back_to_xfm_with_warning(self, tmp_path, caplog):
        import logging
        handler = GcaHandler()
        atlas = self._make_gca_atlas(tmp_path)
        subject = self._make_subject_with_xfm_only(tmp_path)

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            with caplog.at_level(logging.WARNING, logger="fsatlas.core.formats"):
                result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        mock_cmd.assert_called_once()
        assert any("talairach.xfm" in r.message or "falling back" in r.message
                   for r in caplog.records)

    def test_transfer_output_format_id(self, tmp_path):
        handler = GcaHandler()
        atlas = self._make_gca_atlas(tmp_path)
        subject = self._make_subject_with_m3z(tmp_path)

        with patch("fsatlas.core.formats.run_command"):
            result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        assert result.format_id == "gca"
        assert "volume" in result.paths


# ---------------------------------------------------------------------------
# DlabelGiiHandler.extract — delegates to AnnotHandler
# ---------------------------------------------------------------------------

class TestDlabelGiiHandlerExtract:
    def test_extract_delegates_to_annot_handler(self, tmp_path):
        handler = DlabelGiiHandler()
        atlas = MagicMock()
        atlas.name = "myatlas"
        subject = MagicMock()
        env = MagicMock()
        transfer_result = TransferResult(paths={}, format_id="dlabel_gii")

        import pandas as pd
        mock_df = pd.DataFrame({"StructName": ["region_A"], "ThickAvg": [2.5]})

        with patch("fsatlas.core.formats.AnnotHandler.extract",
                   return_value=(mock_df, 1500000.0)) as mock_extract:
            df, tiv = handler.extract(atlas, subject, env, transfer_result)

        mock_extract.assert_called_once()
        assert tiv == 1500000.0


# ---------------------------------------------------------------------------
# DlabelGiiHandler.transfer
# ---------------------------------------------------------------------------

class TestDlabelGiiHandlerTransfer:
    def test_transfer_converts_dlabel_to_annot(self, tmp_path):
        handler = DlabelGiiHandler()

        # Create fake atlas
        atlas = MagicMock()
        atlas.name = "myatlas"
        atlas.builtin = False
        atlas.cache_dir = tmp_path / "cache"
        atlas.cache_dir.mkdir()

        lh_dlabel = tmp_path / "lh.myatlas.dlabel.gii"
        rh_dlabel = tmp_path / "rh.myatlas.dlabel.gii"
        lh_dlabel.touch()
        rh_dlabel.touch()
        atlas.get_file.side_effect = lambda k: lh_dlabel if "lh" in k else rh_dlabel

        # Subject
        label_dir = tmp_path / "label"
        label_dir.mkdir()
        subject = MagicMock()
        subject.label_dir = label_dir

        # FreeSurferEnv
        fs_home = tmp_path / "freesurfer"
        (fs_home / "subjects" / "fsaverage" / "surf").mkdir(parents=True)
        for hemi in ("lh", "rh"):
            (fs_home / "subjects" / "fsaverage" / "surf" / f"{hemi}.sphere.reg").touch()
        env = MagicMock()
        env.freesurfer_home = fs_home

        call_count = {"n": 0}

        def fake_run_command(cmd, env):
            call_count["n"] += 1
            # For mris_convert call, create the converted annot in cache
            if "mris_convert" in cmd[0]:
                out = Path(cmd[-1])
                out.touch()

        with patch("fsatlas.core.formats.run_command", side_effect=fake_run_command):
            result = handler.transfer(atlas, subject, env, overwrite=True)

        # Should have called run_command at least for mri_surf2surf per hemisphere
        assert call_count["n"] >= 2
        assert "lh" in result.paths
        assert "rh" in result.paths
