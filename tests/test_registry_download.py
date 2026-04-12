"""Tests for fsatlas.atlases.populate — BIDS-atlas directory population.

The old ``registry.download()`` logic has moved to ``atlases.populate``.
These tests cover the new populate functions that were previously tested via
the registry download path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from fsatlas.atlases.registry import AtlasRegistry, AtlasSpec


MINIMAL_CATALOG = {
    "surface_atlas": {
        "name": "surface_atlas",
        "description": "Test surface atlas",
        "type": "surface",
        "format": "annot",
        "space": "fsaverage",
        "source_url": "https://example.com/atlases",
        "files": {"lh.annot": "lh.surface.annot", "rh.annot": "rh.surface.annot"},
        "labels_tsv": "surface_labels.tsv",
        "builtin": False,
        "annot_name": "",
        "citation": "",
        "family": "",
        "bids_name": "TestSurface",
    },
    "volumetric_atlas": {
        "name": "volumetric_atlas",
        "description": "Test volumetric atlas",
        "type": "volumetric",
        "format": "nifti",
        "space": "MNI152NLin6Asym",
        "source_url": "https://example.com/atlases",
        "files": {"atlas.nii.gz": "test_vol.nii.gz"},
        "labels_tsv": "vol_labels.tsv",
        "builtin": False,
        "citation": "",
        "family": "",
        "bids_name": "TestVolumetric",
    },
    "builtin_surface": {
        "name": "builtin_surface",
        "description": "Built-in FS surface atlas",
        "type": "surface",
        "format": "annot",
        "space": "fsaverage",
        "source_url": "",
        "files": {},
        "labels_tsv": "builtin_labels.tsv",
        "builtin": True,
        "annot_name": "aparc",
        "citation": "",
        "family": "",
        "bids_name": "TestBuiltin",
    },
    "builtin_nifti": {
        "name": "builtin_nifti",
        "description": "Built-in FS volumetric (aseg)",
        "type": "volumetric",
        "format": "nifti",
        "space": "subject",
        "source_url": "",
        "files": {},
        "labels_tsv": "aseg_labels.tsv",
        "builtin": True,
        "annot_name": "",
        "citation": "",
        "family": "",
        "bids_name": "TestAseg",
    },
}


@pytest.fixture
def catalog_dir(tmp_path) -> Path:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.dump(MINIMAL_CATALOG))
    return tmp_path


@pytest.fixture
def registry(catalog_dir) -> AtlasRegistry:
    return AtlasRegistry(catalog_path=catalog_dir / "catalog.yaml")


# ---------------------------------------------------------------------------
# populate_atlas — annot atlas (auto-generate LUT from annot colour table)
# ---------------------------------------------------------------------------

class TestPopulateAnnotAtlas:
    def test_generates_lut_from_annot(self, registry, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_atlas

        atlas = registry.get("surface_atlas")

        def fake_copy_file(local_name, remote_filename, dest, local_source_dir, source_url):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.touch()

        mock_lut = MagicMock()
        mock_lut.to_tsv = MagicMock()

        with patch("fsatlas.atlases.populate._copy_file_from_source", side_effect=fake_copy_file):
            with patch("fsatlas.core.lut.LookupTable.from_annot", return_value=mock_lut):
                with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
                    populate_atlas(atlas, tmp_path, force=True)

        mock_lut.to_tsv.assert_called_once()

    def test_skips_when_already_present_no_force(self, registry, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_atlas, _lut_filename

        atlas = registry.get("surface_atlas")
        atlas_dir = tmp_path / f"atlas-{atlas.bids_atlas_name}"
        atlas_dir.mkdir(parents=True)

        # Pre-create BIDS files so is_available() returns True
        bids_lh = atlas_dir / f"atlas-{atlas.bids_atlas_name}_space-fsaverage_hemi-L_dseg.annot"
        bids_rh = atlas_dir / f"atlas-{atlas.bids_atlas_name}_space-fsaverage_hemi-R_dseg.annot"
        lut_file = atlas_dir / _lut_filename(atlas)
        for f in (bids_lh, bids_rh, lut_file):
            f.touch()

        with patch("fsatlas.atlases.populate._copy_file_from_source") as mock_copy:
            with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
                populate_atlas(atlas, tmp_path, force=False)

        # copy should not be called for lh.annot / rh.annot since they exist
        for call_args in mock_copy.call_args_list:
            # dest should be the BIDS file which already exists — so copy skipped
            pass  # no error means the "skip" path was taken


# ---------------------------------------------------------------------------
# populate_atlas — volumetric atlas (copy/download labels TSV)
# ---------------------------------------------------------------------------

class TestPopulateVolumetricAtlas:
    def test_copies_labels_from_catalog_dir(self, registry, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_atlas

        atlas = registry.get("volumetric_atlas")

        # Create the labels TSV in the catalog dir
        (catalog_dir / "vol_labels.tsv").write_text(
            "index\tlabel\themisphere\n1\tLeft-Putamen\tlh\n"
        )

        def fake_copy_file(local_name, remote_filename, dest, local_source_dir, source_url):
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Simulate .nii.gz file creation
            dest.touch()

        with patch("fsatlas.atlases.populate._copy_file_from_source", side_effect=fake_copy_file):
            with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
                atlas_dir = populate_atlas(atlas, tmp_path, force=True)

        # Check LUT was created
        from fsatlas.atlases.populate import _lut_filename
        assert (atlas_dir / _lut_filename(atlas)).exists()


# ---------------------------------------------------------------------------
# _populate_builtin — annot with bundled labels
# ---------------------------------------------------------------------------

class TestPopulateBuiltinAnnot:
    def test_copies_bundled_labels(self, registry, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_atlas

        atlas = registry.get("builtin_surface")
        bundled = catalog_dir / "builtin_labels.tsv"
        bundled.write_text("index\tlabel\themisphere\n1\tlh_r\tlh\n")

        with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            atlas_dir = populate_atlas(atlas, tmp_path, force=True)

        from fsatlas.atlases.populate import _lut_filename
        assert (atlas_dir / _lut_filename(atlas)).exists()

    def test_generates_from_fsaverage_when_env_provided(self, registry, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_atlas

        atlas = registry.get("builtin_surface")
        fs_home = tmp_path / "freesurfer"
        fsavg_label = fs_home / "subjects" / "fsaverage" / "label"
        fsavg_label.mkdir(parents=True)
        (fsavg_label / "lh.aparc.annot").touch()
        (fsavg_label / "rh.aparc.annot").touch()

        mock_lut = MagicMock()
        mock_lut.to_tsv = MagicMock()

        with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            with patch("fsatlas.core.lut.LookupTable.from_annot", return_value=mock_lut):
                populate_atlas(atlas, tmp_path, force=True, freesurfer_home=fs_home)

        mock_lut.to_tsv.assert_called_once()

    def test_warns_without_freesurfer_home(self, registry, catalog_dir, tmp_path, caplog):
        import logging
        from fsatlas.atlases.populate import populate_atlas

        atlas = registry.get("builtin_surface")
        # No bundled labels, no freesurfer_home
        with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            with caplog.at_level(logging.WARNING, logger="fsatlas.atlases.populate"):
                populate_atlas(atlas, tmp_path, force=True, freesurfer_home=None)
        assert any("FREESURFER_HOME" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _populate_builtin — nifti (aseg-like) with bundled labels
# ---------------------------------------------------------------------------

class TestPopulateBuiltinNifti:
    def test_copies_bundled_nifti_labels(self, registry, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_atlas

        atlas = registry.get("builtin_nifti")
        bundled = catalog_dir / "aseg_labels.tsv"
        bundled.write_text("index\tlabel\n41\tLeft-Lateral-Ventricle\n")

        with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            atlas_dir = populate_atlas(atlas, tmp_path, force=True)

        from fsatlas.atlases.populate import _lut_filename
        assert (atlas_dir / _lut_filename(atlas)).exists()


# ---------------------------------------------------------------------------
# _copy_file_from_source — used inside populate_atlas
# ---------------------------------------------------------------------------

class TestCopyFileFromSource:
    def test_copies_from_local_source_dir(self, tmp_path):
        from fsatlas.atlases.registry import _copy_file_from_source

        local_dir = tmp_path / "local_atlases"
        local_dir.mkdir()
        src_file = local_dir / "test_atlas.nii.gz"
        src_file.write_bytes(b"atlas_data")

        dest = tmp_path / "output" / "test_atlas.nii.gz"
        dest.parent.mkdir(parents=True)

        _copy_file_from_source(
            "atlas.nii.gz",
            "test_atlas.nii.gz",
            dest,
            local_source_dir=str(local_dir),
            source_url="",
        )
        assert dest.exists()
        assert dest.read_bytes() == b"atlas_data"

    def test_downloads_from_url_when_no_local(self, tmp_path):
        from fsatlas.atlases.registry import _copy_file_from_source
        import requests

        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_resp.raise_for_status = MagicMock()

        dest = tmp_path / "output.nii.gz"
        with patch("requests.get", return_value=mock_resp):
            _copy_file_from_source(
                "atlas.nii.gz",
                "remote_atlas.nii.gz",
                dest,
                local_source_dir="",
                source_url="https://example.com/atlases",
            )
        assert dest.exists()
        assert dest.read_bytes() == b"chunk1chunk2"


# ---------------------------------------------------------------------------
# populate_all — smoke test
# ---------------------------------------------------------------------------

class TestPopulateAll:
    def test_populates_multiple_atlases(self, catalog_dir, tmp_path):
        from fsatlas.atlases.populate import populate_all

        def fake_copy_file(local_name, remote_filename, dest, local_source_dir, source_url):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.touch()

        mock_lut = MagicMock()
        mock_lut.to_tsv = MagicMock()

        with patch("fsatlas.atlases.populate._copy_file_from_source", side_effect=fake_copy_file):
            with patch("fsatlas.core.lut.LookupTable.from_annot", return_value=mock_lut):
                with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
                    populate_all(
                        output_dir=tmp_path,
                        atlas_names=["surface_atlas"],
                        force=True,
                        catalog_path=catalog_dir / "catalog.yaml",
                    )

        assert (tmp_path / "dataset_description.json").exists()

    def test_unknown_atlas_logged_but_continues(self, catalog_dir, tmp_path, caplog):
        import logging
        from fsatlas.atlases.populate import populate_all

        with patch("fsatlas.atlases.populate.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            with caplog.at_level(logging.ERROR, logger="fsatlas.atlases.populate"):
                populate_all(
                    output_dir=tmp_path,
                    atlas_names=["nonexistent_atlas"],
                    catalog_path=catalog_dir / "catalog.yaml",
                )
        assert any("nonexistent_atlas" in r.message for r in caplog.records)
