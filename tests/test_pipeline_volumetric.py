"""Tests for pipeline volumetric (ctab) path and _extract_with_ctab."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from fsatlas.atlases.registry import AtlasSpec, CustomAtlasSpec
from fsatlas.core.environment import FreeSurferEnv
from fsatlas.core.pipeline import _extract_with_ctab, _load_lut, run_extraction


def _make_env(tmp_path: Path) -> FreeSurferEnv:
    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir(exist_ok=True)
    subjects_dir = tmp_path / "subjects"
    subjects_dir.mkdir(exist_ok=True)
    return FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=subjects_dir, version="8.0.0")


def _make_subject_dir(subjects_dir: Path, name: str) -> Path:
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


SEGSTATS = textwrap.dedent("""\
    # Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1600000.0, mm^3
    1 10 500 450.0 Left-Putamen 90.5 8.2 60.0 120.0 60.0
    2 20 600 550.0 Right-Putamen 88.0 7.5 55.0 115.0 60.0
""")


# ---------------------------------------------------------------------------
# _load_lut with AtlasSpec (downloads if not cached)
# ---------------------------------------------------------------------------

class TestLoadLutAtlasSpec:
    def test_loads_after_download_for_atlas_spec(self, tmp_path):
        """_load_lut triggers download when labels_tsv_path is None for AtlasSpec."""
        lut_file = tmp_path / "labels.tsv"
        lut_file.write_text("index\tlabel\themisphere\n1\tlh_r\tlh\n")

        atlas = MagicMock(spec=AtlasSpec)
        atlas.name = "test_atlas"
        # labels_tsv_path returns None on first call, then the file on second
        atlas.labels_tsv_path = None

        mock_registry = MagicMock()

        def side_effect_download(name, env=None):
            # After download, update labels_tsv_path
            atlas.labels_tsv_path = lut_file

        mock_registry.download.side_effect = side_effect_download

        with patch("fsatlas.core.pipeline.AtlasRegistry", return_value=mock_registry):
            lut = _load_lut(atlas, env=None)

        assert len(lut.df) == 1

    def test_raises_if_still_none_after_download(self, tmp_path):
        """If download doesn't produce a LUT, _load_lut raises RuntimeError."""
        atlas = MagicMock(spec=AtlasSpec)
        atlas.name = "bad_atlas"
        atlas.labels_tsv_path = None  # stays None even after download

        mock_registry = MagicMock()
        mock_registry.download.return_value = None  # download doesn't set labels_tsv_path

        with patch("fsatlas.core.pipeline.AtlasRegistry", return_value=mock_registry):
            with pytest.raises(RuntimeError, match="No LUT found"):
                _load_lut(atlas)


# ---------------------------------------------------------------------------
# run_extraction with volumetric handler (ctab path)
# ---------------------------------------------------------------------------

class TestRunExtractionVolumetric:
    def _make_lut_file(self, tmp_path: Path) -> Path:
        lut = tmp_path / "labels.tsv"
        lut.write_text(
            "index\tlabel\themisphere\n"
            "10\tLeft-Putamen\tlh\n"
            "20\tRight-Putamen\trh\n"
        )
        return lut

    def test_volumetric_creates_ctab_then_cleans_up(self, tmp_path):
        subjects_dir = tmp_path / "subjects"
        subjects_dir.mkdir()
        _make_subject_dir(subjects_dir, "sub-01")
        output_dir = tmp_path / "output"
        lut_file = self._make_lut_file(tmp_path)

        env = _make_env(tmp_path)

        atlas = MagicMock(spec=CustomAtlasSpec)
        atlas.name = "testvol"
        atlas.type = "volumetric"
        atlas.format = "nifti"
        atlas.structure = "subcortex"
        atlas.space = "MNI152NLin2009cAsym"
        atlas.description = "Custom nifti atlas: testvol"
        atlas.citation = "User-provided"
        atlas.bids_atlas_name = "TestVol"
        atlas.labels_tsv_path = lut_file

        raw_df = pd.DataFrame({
            "SegId": [10, 20],
            "NVoxels": [500, 600],
            "Volume_mm3": [450.0, 550.0],
            "StructName": ["Left-Putamen", "Right-Putamen"],
            "normMean": [90.5, 88.0],
            "normStdDev": [8.2, 7.5],
            "normMin": [60.0, 55.0],
            "normMax": [120.0, 115.0],
            "normRange": [60.0, 60.0],
        })

        mock_handler = MagicMock()
        mock_handler.join_on = "index"  # triggers ctab path
        mock_handler.measure_map = {"NVoxels": "num_voxels", "Volume_mm3": "volume_mm3"}
        mock_handler.transfer.return_value = MagicMock(paths={"volume": tmp_path / "seg.mgz"})

        with patch("fsatlas.core.pipeline.get_handler", return_value=mock_handler):
            with patch("fsatlas.core.pipeline._extract_with_ctab", return_value=(raw_df, 1600000.0)):
                result = run_extraction(
                    atlas=atlas,
                    subjects=["sub-01"],
                    env=env,
                    output_dir=output_dir,
                    output_layout="flat",
                )

        assert "output" in result


# ---------------------------------------------------------------------------
# _extract_with_ctab
# ---------------------------------------------------------------------------

class TestExtractWithCtab:
    def test_calls_run_segstats_with_ctab(self, tmp_path):
        # Create minimal stats file for parsing
        stats_file = tmp_path / "atlas.subcortical.stats"
        stats_file.write_text(SEGSTATS)

        handler = MagicMock()
        atlas = MagicMock()
        atlas.name = "myatlas"
        subject = MagicMock()
        subject.stats_dir = tmp_path
        subject.norm_mgz = tmp_path / "norm.mgz"
        (tmp_path / "norm.mgz").touch()
        env = MagicMock()
        transfer_result = MagicMock()
        transfer_result.paths = {"volume": tmp_path / "seg.mgz"}
        ctab_path = tmp_path / "labels.ctab"
        ctab_path.touch()

        with patch("fsatlas.core.extract._run_segstats", return_value=stats_file) as mock_seg:
            df, tiv = _extract_with_ctab(
                handler, atlas, subject, env, transfer_result, ctab_path, force=False
            )

        mock_seg.assert_called_once()
        call_kwargs = mock_seg.call_args.kwargs
        assert call_kwargs["ctab_path"] == ctab_path
        assert isinstance(df, pd.DataFrame)
        assert tiv == pytest.approx(1600000.0)
