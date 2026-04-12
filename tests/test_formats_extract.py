"""Tests for format handler extract paths and _nifti_shape_matches."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fsatlas.core.formats import (
    AnnotHandler,
    GcaHandler,
    NiftiHandler,
    TransferResult,
    _nifti_shape_matches,
)


CORTICAL_STATS = textwrap.dedent("""\
    # Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3
    lh_precentral 5000 2500.0 8000.0 2.500 0.400 0.100 0.020 10 1.5
    lh_postcentral 4500 2200.0 7000.0 2.200 0.350 0.090 0.018 9 1.2
""")

SEGSTATS = textwrap.dedent("""\
    # Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1600000.0, mm^3
    1 10 500 450.0 Left-Putamen 90.5 8.2 60.0 120.0 60.0
    2 20 600 550.0 Right-Putamen 88.0 7.5 55.0 115.0 60.0
""")


def _make_subject_paths(tmp_path: Path, name: str = "sub-01") -> MagicMock:
    subj_dir = tmp_path / "subjects" / name
    stats_dir = subj_dir / "stats"
    stats_dir.mkdir(parents=True)
    mri_dir = subj_dir / "mri"
    mri_dir.mkdir(parents=True)
    norm_mgz = mri_dir / "norm.mgz"
    norm_mgz.touch()
    sp = MagicMock()
    sp.subject_id = name
    sp.stats_dir = stats_dir
    sp.norm_mgz = norm_mgz
    return sp


# ---------------------------------------------------------------------------
# _nifti_shape_matches
# ---------------------------------------------------------------------------

class TestNiftiShapeMatches:
    def test_returns_false_on_exception(self, tmp_path):
        """If nibabel can't load, returns False."""
        result = _nifti_shape_matches(
            tmp_path / "nonexistent_a.nii.gz",
            tmp_path / "nonexistent_b.nii.gz",
        )
        assert result is False

    def test_matching_shapes(self, tmp_path):
        """Two NIfTI with same spatial dims → True."""
        import numpy as np
        import nibabel as nib

        data = np.zeros((10, 10, 10))
        img = nib.Nifti1Image(data, np.eye(4))
        path_a = tmp_path / "a.nii.gz"
        path_b = tmp_path / "b.nii.gz"
        nib.save(img, str(path_a))
        nib.save(img, str(path_b))
        assert _nifti_shape_matches(path_a, path_b) is True

    def test_mismatched_shapes(self, tmp_path):
        import numpy as np
        import nibabel as nib

        img_a = nib.Nifti1Image(np.zeros((10, 10, 10)), np.eye(4))
        img_b = nib.Nifti1Image(np.zeros((20, 20, 20)), np.eye(4))
        path_a = tmp_path / "a.nii.gz"
        path_b = tmp_path / "b.nii.gz"
        nib.save(img_a, str(path_a))
        nib.save(img_b, str(path_b))
        assert _nifti_shape_matches(path_a, path_b) is False


# ---------------------------------------------------------------------------
# AnnotHandler.extract
# ---------------------------------------------------------------------------

class TestAnnotHandlerExtract:
    def test_extract_returns_df_and_tiv(self, tmp_path):
        handler = AnnotHandler()
        atlas = MagicMock()
        atlas.name = "myatlas"
        subject = _make_subject_paths(tmp_path)
        env = MagicMock()

        # Pre-create stats files
        lh_stats = subject.stats_dir / "lh.myatlas.stats"
        rh_stats = subject.stats_dir / "rh.myatlas.stats"
        lh_stats.write_text(CORTICAL_STATS)
        rh_stats.write_text(CORTICAL_STATS)

        transfer_result = TransferResult(
            paths={"lh": tmp_path / "lh.annot", "rh": tmp_path / "rh.annot"},
            format_id="annot",
        )
        (tmp_path / "lh.annot").touch()
        (tmp_path / "rh.annot").touch()

        with patch("fsatlas.core.extract._run_anatomical_stats", side_effect=[lh_stats, rh_stats]):
            df, tiv = handler.extract(atlas, subject, env, transfer_result, force=False)

        assert isinstance(df, pd.DataFrame)
        assert tiv == pytest.approx(1500000.0)

    def test_extract_empty_transfer_result(self, tmp_path):
        handler = AnnotHandler()
        atlas = MagicMock()
        subject = MagicMock()
        env = MagicMock()
        transfer_result = TransferResult(paths={}, format_id="annot")
        df, tiv = handler.extract(atlas, subject, env, transfer_result)
        assert len(df) == 0
        assert tiv is None

    def test_extract_adds_hemi_column(self, tmp_path):
        handler = AnnotHandler()
        atlas = MagicMock()
        atlas.name = "myatlas"
        subject = _make_subject_paths(tmp_path)
        env = MagicMock()

        lh_stats = subject.stats_dir / "lh.myatlas.stats"
        lh_stats.write_text(CORTICAL_STATS)

        transfer_result = TransferResult(
            paths={"lh": tmp_path / "lh.annot"},
            format_id="annot",
        )
        (tmp_path / "lh.annot").touch()

        with patch("fsatlas.core.extract._run_anatomical_stats", return_value=lh_stats):
            df, _ = handler.extract(atlas, subject, env, transfer_result)

        assert "_hemi" in df.columns
        assert (df["_hemi"] == "lh").all()


# ---------------------------------------------------------------------------
# NiftiHandler.extract
# ---------------------------------------------------------------------------

class TestNiftiHandlerExtract:
    def test_extract_returns_df_and_tiv(self, tmp_path):
        handler = NiftiHandler()
        atlas = MagicMock()
        atlas.name = "myatlas"
        subject = _make_subject_paths(tmp_path)
        env = MagicMock()

        stats_file = subject.stats_dir / "myatlas.subcortical.stats"
        stats_file.write_text(SEGSTATS)

        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()
        transfer_result = TransferResult(paths={"volume": seg_path}, format_id="nifti")

        with patch("fsatlas.core.extract._run_segstats", return_value=stats_file):
            df, tiv = handler.extract(atlas, subject, env, transfer_result)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert tiv == pytest.approx(1600000.0)


# ---------------------------------------------------------------------------
# NiftiHandler.transfer (non-aseg)
# ---------------------------------------------------------------------------

class TestNiftiHandlerTransferNonAseg:
    def test_transfer_runs_vol2vol(self, tmp_path):
        """MNI305 atlases always use the linear mri_vol2vol path."""
        import numpy as np
        import nibabel as nib

        handler = NiftiHandler()
        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myvol"
        atlas.space = "MNI305"

        # Create atlas nifti and subject norm
        data = np.zeros((10, 10, 10))
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / "atlas.nii.gz"
        nib.save(img, str(nii_path))

        # Subject paths
        mri_dir = tmp_path / "mri"
        atlas_dir = mri_dir / "atlas"
        atlas_dir.mkdir(parents=True)
        norm_mgz = mri_dir / "norm.mgz"
        nib.save(img, str(norm_mgz))
        xfm = mri_dir / "transforms" / "talairach.xfm"
        (mri_dir / "transforms").mkdir(parents=True)
        xfm.touch()

        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.norm_mgz = norm_mgz
        subject.talairach_xfm = xfm

        atlas.get_file.return_value = nii_path

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            with patch("fsatlas.core.formats._get_nifti_file", return_value=nii_path):
                result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        mock_cmd.assert_called_once()
        assert "volume" in result.paths

    def test_transfer_mni152_uses_easyreg_by_default(self, tmp_path):
        """MNI152 atlases use the easyreg backend when registration_backend='easyreg'."""
        import numpy as np
        import nibabel as nib

        handler = NiftiHandler()
        assert handler.registration_backend == "easyreg"

        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myvol"
        atlas.space = "MNI152NLin2009cAsym"

        data = np.zeros((10, 10, 10))
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / "atlas.nii.gz"
        nib.save(img, str(nii_path))

        mri_dir = tmp_path / "mri"
        (mri_dir / "atlas").mkdir(parents=True)
        norm_mgz = mri_dir / "norm.mgz"
        nib.save(img, str(norm_mgz))

        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.norm_mgz = norm_mgz

        fake_warp = MagicMock()
        fake_warp.commands_run = []

        with patch("fsatlas.core.formats._get_nifti_file", return_value=nii_path):
            with patch(
                "fsatlas.core.easyreg_registration.ensure_subject_to_template_warp",
                return_value=fake_warp,
            ) as mock_warp:
                with patch(
                    "fsatlas.core.easyreg_registration.apply_template_to_subject",
                    return_value=["mri_easywarp", "--i", "..."],
                ) as mock_apply:
                    result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        mock_warp.assert_called_once()
        mock_apply.assert_called_once()
        assert "volume" in result.paths

    def test_transfer_mni152_ants_backend(self, tmp_path):
        """MNI152 atlases use the ANTs backend when registration_backend='ants'."""
        import numpy as np
        import nibabel as nib

        handler = NiftiHandler()
        handler.registration_backend = "ants"

        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myvol"
        atlas.space = "MNI152NLin2009cAsym"

        data = np.zeros((10, 10, 10))
        img = nib.Nifti1Image(data, np.eye(4))
        nii_path = tmp_path / "atlas.nii.gz"
        nib.save(img, str(nii_path))

        mri_dir = tmp_path / "mri"
        (mri_dir / "atlas").mkdir(parents=True)
        norm_mgz = mri_dir / "norm.mgz"
        nib.save(img, str(norm_mgz))

        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.norm_mgz = norm_mgz

        fake_warp = MagicMock()
        fake_warp.commands_run = []

        with patch("fsatlas.core.formats._get_nifti_file", return_value=nii_path):
            with patch(
                "fsatlas.core.formats.ensure_subject_to_template_warp",
                return_value=fake_warp,
            ) as mock_warp:
                with patch(
                    "fsatlas.core.formats.apply_template_to_subject",
                    return_value=["antsApplyTransforms", "..."],
                ) as mock_apply:
                    result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        mock_warp.assert_called_once()
        mock_apply.assert_called_once()
        assert "volume" in result.paths

    def test_transfer_skips_if_output_matches_norm(self, tmp_path):
        import numpy as np
        import nibabel as nib

        handler = NiftiHandler()
        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myvol"

        data = np.zeros((10, 10, 10))
        img = nib.Nifti1Image(data, np.eye(4))
        mri_dir = tmp_path / "mri"
        atlas_dir = mri_dir / "atlas"
        atlas_dir.mkdir(parents=True)
        norm_mgz = mri_dir / "norm.mgz"
        out_path = atlas_dir / "myvol_native.nii.gz"
        nib.save(img, str(norm_mgz))
        nib.save(img, str(out_path))  # pre-existing output with matching shape

        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.norm_mgz = norm_mgz

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            result = handler.transfer(atlas, subject, MagicMock(), overwrite=False)

        mock_cmd.assert_not_called()
        assert result.paths["volume"] == out_path


# ---------------------------------------------------------------------------
# GcaHandler.extract
# ---------------------------------------------------------------------------

class TestGcaHandlerExtract:
    def test_extract_returns_df_and_tiv(self, tmp_path):
        handler = GcaHandler()
        atlas = MagicMock()
        atlas.name = "myatlas"
        subject = _make_subject_paths(tmp_path)
        env = MagicMock()

        stats_file = subject.stats_dir / "myatlas.subcortical.stats"
        stats_file.write_text(SEGSTATS)

        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()
        transfer_result = TransferResult(paths={"volume": seg_path}, format_id="gca")

        with patch("fsatlas.core.extract._run_segstats", return_value=stats_file):
            df, tiv = handler.extract(atlas, subject, env, transfer_result)

        assert isinstance(df, pd.DataFrame)
        assert tiv == pytest.approx(1600000.0)


# ---------------------------------------------------------------------------
# AnnotHandler.transfer (non-builtin, runs mri_surf2surf)
# ---------------------------------------------------------------------------

class TestAnnotHandlerTransferNonBuiltin:
    def test_transfer_runs_surf2surf(self, tmp_path):
        handler = AnnotHandler()
        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myatlas"

        label_dir = tmp_path / "label"
        label_dir.mkdir()

        src_lh = tmp_path / "lh.myatlas.annot"
        src_rh = tmp_path / "rh.myatlas.annot"
        src_lh.touch()
        src_rh.touch()
        atlas.get_file.side_effect = lambda key: src_lh if "lh" in key else src_rh

        subject = MagicMock()
        subject.label_dir = label_dir

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            result = handler.transfer(atlas, subject, MagicMock(), overwrite=True)

        assert mock_cmd.call_count == 2  # lh + rh
        assert "lh" in result.paths
        assert "rh" in result.paths

    def test_transfer_skips_existing_without_overwrite(self, tmp_path):
        handler = AnnotHandler()
        atlas = MagicMock()
        atlas.builtin = False
        atlas.name = "myatlas"

        label_dir = tmp_path / "label"
        label_dir.mkdir()

        # Pre-create both annots
        (label_dir / "lh.myatlas.annot").touch()
        (label_dir / "rh.myatlas.annot").touch()

        subject = MagicMock()
        subject.label_dir = label_dir

        with patch("fsatlas.core.formats.run_command") as mock_cmd:
            result = handler.transfer(atlas, subject, MagicMock(), overwrite=False)

        mock_cmd.assert_not_called()
        assert "lh" in result.paths
