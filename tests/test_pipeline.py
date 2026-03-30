"""Tests for fsatlas.core.pipeline — OutputWriter strategies and run_extraction."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fsatlas.atlases.registry import CustomAtlasSpec
from fsatlas.core.environment import FreeSurferEnv, SubjectPaths
from fsatlas.core.pipeline import BidsWriter, FlatWriter, _load_lut, run_extraction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_env(tmp_path: Path) -> FreeSurferEnv:
    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir()
    subjects_dir = tmp_path / "subjects"
    subjects_dir.mkdir()
    return FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=subjects_dir, version="8.0.0")


def _make_atlas(name: str = "testatlas") -> CustomAtlasSpec:
    return CustomAtlasSpec(
        name=name,
        type="surface",
        format="annot",
        paths={},
    )


def _make_df(subject_id: str = "sub-01") -> pd.DataFrame:
    return pd.DataFrame({
        "subject_id": [subject_id, subject_id],
        "index": [1, 2],
        "label": ["lh_region_A", "rh_region_B"],
        "hemisphere": ["lh", "rh"],
        "thickness_mean_mm": [2.5, 2.8],
        "tiv_mm3": [1500000.0, 1500000.0],
    })


# ---------------------------------------------------------------------------
# FlatWriter
# ---------------------------------------------------------------------------

class TestFlatWriter:
    def test_write_single_subject_accumulated(self, tmp_path):
        atlas = _make_atlas()
        writer = FlatWriter(tmp_path, atlas)
        df = _make_df("sub-01")
        writer.write_subject(df, "sub-01", atlas)
        assert len(writer._frames) == 1

    def test_finalize_writes_tsv(self, tmp_path):
        atlas = _make_atlas()
        writer = FlatWriter(tmp_path, atlas)
        writer.write_subject(_make_df("sub-01"), "sub-01", atlas)
        result = writer.finalize()
        assert "output" in result
        assert result["output"].exists()

    def test_finalize_tsv_has_correct_name(self, tmp_path):
        atlas = _make_atlas("myatlas")
        writer = FlatWriter(tmp_path, atlas)
        writer.write_subject(_make_df("sub-01"), "sub-01", atlas)
        result = writer.finalize()
        assert result["output"].name == "myatlas.tsv"

    def test_finalize_concatenates_multiple_subjects(self, tmp_path):
        atlas = _make_atlas()
        writer = FlatWriter(tmp_path, atlas)
        writer.write_subject(_make_df("sub-01"), "sub-01", atlas)
        writer.write_subject(_make_df("sub-02"), "sub-02", atlas)
        result = writer.finalize()
        df = pd.read_csv(result["output"], sep="\t")
        assert set(df["subject_id"]) == {"sub-01", "sub-02"}

    def test_finalize_empty_returns_empty_dict(self, tmp_path):
        atlas = _make_atlas()
        writer = FlatWriter(tmp_path, atlas)
        result = writer.finalize()
        assert result == {}


# ---------------------------------------------------------------------------
# BidsWriter
# ---------------------------------------------------------------------------

def _make_mock_atlas(name: str = "testatlas") -> MagicMock:
    atlas = MagicMock()
    atlas.name = name
    atlas.bids_atlas_name = "TestAtlas"
    atlas.structure = "cortex"
    return atlas


class TestBidsWriter:
    def test_write_subject_creates_file(self, tmp_path):
        writer = BidsWriter(tmp_path)
        atlas = _make_mock_atlas()
        df = _make_df("sub-01")
        path = writer.write_subject(df, "sub-01", atlas)
        assert path is not None
        assert path.exists()

    def test_write_subject_creates_bids_directory(self, tmp_path):
        writer = BidsWriter(tmp_path)
        atlas = _make_mock_atlas()
        df = _make_df("sub-01")
        path = writer.write_subject(df, "sub-01", atlas)
        assert "sub-01" in str(path)

    def test_finalize_returns_first_written_path(self, tmp_path):
        writer = BidsWriter(tmp_path)
        atlas = _make_mock_atlas()
        writer.write_subject(_make_df("sub-01"), "sub-01", atlas)
        writer.write_subject(_make_df("sub-02"), "sub-02", atlas)
        result = writer.finalize()
        assert "output" in result

    def test_finalize_empty_returns_empty_dict(self, tmp_path):
        writer = BidsWriter(tmp_path)
        result = writer.finalize()
        assert result == {}

    def test_write_creates_parent_directories(self, tmp_path):
        writer = BidsWriter(tmp_path)
        atlas = _make_mock_atlas()
        path = writer.write_subject(_make_df("sub-99"), "sub-99", atlas)
        assert path.parent.is_dir()


# ---------------------------------------------------------------------------
# _load_lut
# ---------------------------------------------------------------------------

class TestLoadLut:
    def test_loads_from_labels_tsv_path(self, tmp_path):
        lut_file = tmp_path / "labels.tsv"
        lut_file.write_text("index\tlabel\themisphere\n1\tlh_region\tlh\n")
        atlas = MagicMock()
        atlas.labels_tsv_path = lut_file
        lut = _load_lut(atlas)
        assert len(lut.df) == 1

    def test_raises_if_no_lut_and_custom_atlas(self, tmp_path):
        atlas = CustomAtlasSpec(name="x", type="surface", format="annot", paths={})
        # labels_tsv_path is None for CustomAtlasSpec with no labels_tsv
        with pytest.raises(RuntimeError, match="No LUT found"):
            _load_lut(atlas)


# ---------------------------------------------------------------------------
# run_extraction — integration with mocks
# ---------------------------------------------------------------------------

class TestRunExtraction:
    def _make_lut_file(self, tmp_path: Path) -> Path:
        lut = tmp_path / "labels.tsv"
        lut.write_text("index\tlabel\themisphere\n1\tlh_region\tlh\n2\trh_region\trh\n")
        return lut

    def _make_subject_dir(self, subjects_dir: Path, name: str) -> Path:
        subj = subjects_dir / name
        surf = subj / "surf"
        mri = subj / "mri" / "transforms"
        label = subj / "label"
        stats = subj / "stats"
        for d in [surf, mri, label, stats]:
            d.mkdir(parents=True)
        for f in ["lh.white", "rh.white", "lh.pial", "rh.pial", "lh.sphere.reg", "rh.sphere.reg"]:
            (surf / f).touch()
        (subj / "mri" / "aseg.mgz").touch()
        (subj / "mri" / "norm.mgz").touch()
        return subj

    def test_flat_layout_creates_tsv(self, tmp_path):
        subjects_dir = tmp_path / "subjects"
        subjects_dir.mkdir()
        self._make_subject_dir(subjects_dir, "sub-01")
        output_dir = tmp_path / "output"
        lut_file = self._make_lut_file(tmp_path)

        env = FreeSurferEnv(
            freesurfer_home=tmp_path / "fs",
            subjects_dir=subjects_dir,
            version="8.0.0",
        )
        (tmp_path / "fs").mkdir()

        atlas = MagicMock(spec=CustomAtlasSpec)
        atlas.name = "testatlas"
        atlas.format = "annot"
        atlas.structure = "cortex"
        atlas.bids_atlas_name = "TestAtlas"
        atlas.labels_tsv_path = lut_file

        raw_df = pd.DataFrame({
            "StructName": ["lh_region", "rh_region"],
            "ThickAvg": [2.5, 2.8],
        })

        mock_handler = MagicMock()
        mock_handler.join_on = "label"
        mock_handler.measure_map = {"ThickAvg": "thickness_mean_mm"}
        mock_handler.transfer.return_value = MagicMock(paths={"lh": Path("/tmp/lh.annot"),
                                                              "rh": Path("/tmp/rh.annot")})
        mock_handler.extract.return_value = (raw_df, 1500000.0)

        with patch("fsatlas.core.pipeline.get_handler", return_value=mock_handler):
            result = run_extraction(
                atlas=atlas,
                subjects=["sub-01"],
                env=env,
                output_dir=output_dir,
                force=False,
                output_layout="flat",
            )

        assert "output" in result
        assert result["output"].exists()

    def test_bids_layout_creates_csv(self, tmp_path):
        subjects_dir = tmp_path / "subjects"
        subjects_dir.mkdir()
        self._make_subject_dir(subjects_dir, "sub-01")
        output_dir = tmp_path / "output"
        lut_file = self._make_lut_file(tmp_path)

        env = FreeSurferEnv(
            freesurfer_home=tmp_path / "fs",
            subjects_dir=subjects_dir,
            version="8.0.0",
        )
        (tmp_path / "fs").mkdir()

        atlas = MagicMock(spec=CustomAtlasSpec)
        atlas.name = "testatlas"
        atlas.format = "annot"
        atlas.structure = "cortex"
        atlas.bids_atlas_name = "TestAtlas"
        atlas.labels_tsv_path = lut_file

        raw_df = pd.DataFrame({
            "StructName": ["lh_region"],
            "ThickAvg": [2.5],
        })

        mock_handler = MagicMock()
        mock_handler.join_on = "label"
        mock_handler.measure_map = {"ThickAvg": "thickness_mean_mm"}
        mock_handler.transfer.return_value = MagicMock(paths={"lh": Path("/tmp/lh.annot")})
        mock_handler.extract.return_value = (raw_df, 1500000.0)

        with patch("fsatlas.core.pipeline.get_handler", return_value=mock_handler):
            result = run_extraction(
                atlas=atlas,
                subjects=["sub-01"],
                env=env,
                output_dir=output_dir,
                force=False,
                output_layout="bids",
            )

        assert "output" in result

    def test_failed_subject_recorded_in_failures_csv(self, tmp_path):
        subjects_dir = tmp_path / "subjects"
        subjects_dir.mkdir()
        output_dir = tmp_path / "output"
        lut_file = self._make_lut_file(tmp_path)

        env = FreeSurferEnv(
            freesurfer_home=tmp_path / "fs",
            subjects_dir=subjects_dir,
            version="8.0.0",
        )
        (tmp_path / "fs").mkdir()

        atlas = MagicMock(spec=CustomAtlasSpec)
        atlas.name = "testatlas"
        atlas.format = "annot"
        atlas.structure = "cortex"
        atlas.bids_atlas_name = "TestAtlas"
        atlas.labels_tsv_path = lut_file

        mock_handler = MagicMock()
        mock_handler.join_on = "label"
        mock_handler.measure_map = {}
        mock_handler.transfer.side_effect = RuntimeError("transfer failed")

        # Subject dir doesn't exist → find_subject will raise FileNotFoundError
        with patch("fsatlas.core.pipeline.get_handler", return_value=mock_handler):
            result = run_extraction(
                atlas=atlas,
                subjects=["sub-nonexistent"],
                env=env,
                output_dir=output_dir,
            )

        assert "failures" in result
        fail_df = pd.read_csv(result["failures"])
        assert "sub-nonexistent" in fail_df["subject_id"].values

    def test_subject_with_missing_files_goes_to_failures(self, tmp_path):
        subjects_dir = tmp_path / "subjects"
        subjects_dir.mkdir()
        output_dir = tmp_path / "output"
        lut_file = self._make_lut_file(tmp_path)

        # Create incomplete subject (missing required files)
        subj = subjects_dir / "sub-bad"
        (subj / "surf").mkdir(parents=True)
        (subj / "mri").mkdir(parents=True)
        # Only lh.white present — validate() will find missing files

        env = FreeSurferEnv(
            freesurfer_home=tmp_path / "fs",
            subjects_dir=subjects_dir,
            version="8.0.0",
        )
        (tmp_path / "fs").mkdir()

        atlas = MagicMock(spec=CustomAtlasSpec)
        atlas.name = "testatlas"
        atlas.format = "annot"
        atlas.structure = "cortex"
        atlas.bids_atlas_name = "TestAtlas"
        atlas.labels_tsv_path = lut_file

        mock_handler = MagicMock()
        mock_handler.join_on = "label"
        mock_handler.measure_map = {}

        with patch("fsatlas.core.pipeline.get_handler", return_value=mock_handler):
            result = run_extraction(
                atlas=atlas,
                subjects=["sub-bad"],
                env=env,
                output_dir=output_dir,
            )

        # sub-bad has no lh.white (needed for validate) → but find_subject won't fail,
        # validate() will return missing list → it ends in failures
        assert "failures" in result
