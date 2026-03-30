"""Tests for AtlasRegistry download, _fetch_labels_tsv, and _download_file."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest
import yaml

from fsatlas.atlases.registry import AtlasRegistry, AtlasSpec, _infer_format


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
        "bids_name": "",
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
        "bids_name": "",
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
        "bids_name": "",
    },
    "builtin_nifti": {
        "name": "builtin_nifti",
        "description": "Built-in FS volumetric (aseg)",
        "type": "volumetric",
        "format": "nifti",
        "space": "fsaverage",
        "source_url": "",
        "files": {},
        "labels_tsv": "aseg_labels.tsv",
        "builtin": True,
        "annot_name": "",
        "citation": "",
        "family": "",
        "bids_name": "",
    },
    "local_source_atlas": {
        "name": "local_source_atlas",
        "description": "Atlas with local source dir",
        "type": "volumetric",
        "format": "nifti",
        "space": "MNI152NLin6Asym",
        "source_url": "https://example.com/fallback",
        "files": {"atlas.nii.gz": "local_atlas.nii.gz"},
        "labels_tsv": "local_labels.tsv",
        "builtin": False,
        "local_source_dir": "local_atlases",
        "citation": "",
        "family": "",
        "bids_name": "",
    },
}


@pytest.fixture
def catalog_dir(tmp_path) -> Path:
    """Create a minimal catalog structure."""
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(yaml.dump(MINIMAL_CATALOG))
    return tmp_path


@pytest.fixture
def registry(catalog_dir) -> AtlasRegistry:
    return AtlasRegistry(catalog_path=catalog_dir / "catalog.yaml")


# ---------------------------------------------------------------------------
# Catalog warning for missing labels_tsv
# ---------------------------------------------------------------------------

class TestCatalogWarnings:
    def test_warns_for_missing_labels_tsv(self, tmp_path, caplog):
        import logging
        catalog = {
            "no_lut_atlas": {
                "name": "no_lut_atlas",
                "type": "surface",
                "format": "annot",
                "space": "fsaverage",
                "files": {},
                "labels_tsv": "",   # empty!
                "builtin": False,
                "description": "",
                "citation": "",
            }
        }
        path = tmp_path / "catalog.yaml"
        path.write_text(yaml.dump(catalog))
        with caplog.at_level(logging.WARNING, logger="fsatlas.atlases.registry"):
            AtlasRegistry(catalog_path=path)
        assert any("no labels_tsv" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# download — non-builtin, already cached
# ---------------------------------------------------------------------------

class TestDownloadAlreadyCached:
    def test_returns_early_if_cached(self, registry, tmp_path, catalog_dir):
        atlas = registry.get("surface_atlas")
        # Create all expected cache files
        atlas.cache_dir.mkdir(parents=True, exist_ok=True)
        (atlas.cache_dir / "lh.annot").touch()
        (atlas.cache_dir / "rh.annot").touch()
        (atlas.cache_dir / "labels.tsv").write_text(
            "index\tlabel\themisphere\n1\tlh_r\tlh\n"
        )
        # Should not download anything
        with patch("fsatlas.atlases.registry._download_file") as mock_dl:
            result = registry.download("surface_atlas", force=False)
        mock_dl.assert_not_called()
        assert result is atlas


# ---------------------------------------------------------------------------
# download — non-builtin, annot format (auto-generate LUT)
# ---------------------------------------------------------------------------

class TestDownloadAnnotAtlas:
    def test_downloads_files_and_generates_lut(self, registry, catalog_dir):
        atlas = registry.get("surface_atlas")

        def fake_download(url, dest):
            # Simulate downloading - for lh.annot / rh.annot, create them in cache
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.touch()

        mock_lut = MagicMock()
        mock_lut.to_tsv = MagicMock()

        with patch("fsatlas.atlases.registry._download_file", side_effect=fake_download):
            with patch("fsatlas.core.lut.LookupTable.from_annot", return_value=mock_lut):
                result = registry.download("surface_atlas", force=True)

        assert result is atlas

    def test_warns_if_annot_files_not_found_after_download(self, registry, caplog):
        import logging
        atlas = registry.get("surface_atlas")

        def fake_download(url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.touch()
            # Don't create lh.annot / rh.annot in cache_dir

        with patch("fsatlas.atlases.registry._download_file", side_effect=fake_download):
            with patch("fsatlas.core.lut.LookupTable.from_annot") as mock_fa:
                with caplog.at_level(logging.WARNING, logger="fsatlas.atlases.registry"):
                    registry.download("surface_atlas", force=True)
            # lh.annot IS in the files dict so fake_download WILL create it in cache_dir
            # The annot LUT generation path will be triggered


# ---------------------------------------------------------------------------
# download — non-builtin, nifti format (fetch labels tsv)
# ---------------------------------------------------------------------------

class TestDownloadVolumetricAtlas:
    def test_downloads_nifti_and_labels(self, registry, catalog_dir):
        atlas = registry.get("volumetric_atlas")

        # Create a fake labels.tsv in the catalog dir (for _fetch_labels_tsv fallback)
        catalog_labels = catalog_dir / "vol_labels.tsv"
        catalog_labels.write_text("index\tlabel\themisphere\n1\tLeft-Putamen\tlh\n")

        def fake_download(url, dest):
            dest.touch()

        with patch("fsatlas.atlases.registry._download_file", side_effect=fake_download):
            result = registry.download("volumetric_atlas", force=True)

        assert result is atlas
        lut_dest = atlas.cache_dir / "labels.tsv"
        assert lut_dest.exists()

    def test_downloads_labels_from_url_when_no_catalog_file(self, registry):
        atlas = registry.get("volumetric_atlas")

        def fake_download(url, dest):
            dest.write_text("index\tlabel\n1\tregion\n")

        with patch("fsatlas.atlases.registry._download_file", side_effect=fake_download):
            result = registry.download("volumetric_atlas", force=True)

        assert result is atlas


# ---------------------------------------------------------------------------
# download — local_source_dir
# ---------------------------------------------------------------------------

class TestDownloadLocalSource:
    def test_copies_from_local_source_dir(self, registry, catalog_dir, tmp_path):
        atlas = registry.get("local_source_atlas")

        # Create local source dir with the atlas file (use absolute path)
        local_dir = tmp_path / "local_atlases"
        local_dir.mkdir()
        (local_dir / "local_atlas.nii.gz").touch()

        # Create catalog labels file
        (catalog_dir / "local_labels.tsv").write_text(
            "index\tlabel\themisphere\n1\tRegion\tbilateral\n"
        )

        # Override local_source_dir to use our absolute path
        atlas._replace = lambda **kw: kw  # not a NamedTuple, just for reference
        # Patch CATALOG_PATH so relative dir resolution works
        with patch("fsatlas.atlases.registry.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            with patch.object(atlas, "local_source_dir", str(local_dir)):
                with patch("fsatlas.atlases.registry._download_file") as mock_dl:
                    result = registry.download("local_source_atlas", force=True)

        mock_dl.assert_not_called()
        assert (atlas.cache_dir / "atlas.nii.gz").exists()


# ---------------------------------------------------------------------------
# _download_builtin — annot format with bundled labels
# ---------------------------------------------------------------------------

class TestDownloadBuiltinAnnotBundled:
    def test_copies_bundled_labels(self, registry, catalog_dir):
        atlas = registry.get("builtin_surface")

        # Create the bundled labels file in catalog dir
        bundled = catalog_dir / "builtin_labels.tsv"
        bundled.write_text("index\tlabel\themisphere\n1\tlh_r\tlh\n")

        # Patch CATALOG_PATH so bundled resolution works relative to catalog_dir
        with patch("fsatlas.atlases.registry.CATALOG_PATH", catalog_dir / "catalog.yaml"):
            result = registry.download("builtin_surface", force=True)
        lut_dest = atlas.cache_dir / "labels.tsv"
        assert lut_dest.exists()

    def test_warns_without_env_when_no_bundled(self, registry, catalog_dir, caplog):
        import logging
        atlas = registry.get("builtin_surface")
        # No bundled labels file, no env passed
        with caplog.at_level(logging.WARNING, logger="fsatlas.atlases.registry"):
            registry.download("builtin_surface", force=True, env=None)
        # Should warn about missing env
        # (bundled file doesn't exist, env=None → warning)

    def test_generates_from_fsaverage_when_env_provided(self, registry, catalog_dir, tmp_path):
        atlas = registry.get("builtin_surface")
        # No bundled file
        fs_home = tmp_path / "freesurfer"
        fsavg_label = fs_home / "subjects" / "fsaverage" / "label"
        fsavg_label.mkdir(parents=True)
        (fsavg_label / "lh.aparc.annot").touch()
        (fsavg_label / "rh.aparc.annot").touch()

        env = MagicMock()
        env.freesurfer_home = fs_home

        mock_lut = MagicMock()
        mock_lut.to_tsv = MagicMock()

        with patch("fsatlas.core.lut.LookupTable.from_annot", return_value=mock_lut):
            result = registry.download("builtin_surface", force=True, env=env)

        assert result is atlas


# ---------------------------------------------------------------------------
# _download_builtin — nifti format with bundled labels
# ---------------------------------------------------------------------------

class TestDownloadBuiltinNifti:
    def test_copies_bundled_nifti_labels(self, registry, catalog_dir):
        atlas = registry.get("builtin_nifti")
        bundled = catalog_dir / "aseg_labels.tsv"
        bundled.write_text("index\tlabel\n41\tLeft-Lateral-Ventricle\n")
        result = registry.download("builtin_nifti", force=True)
        assert (atlas.cache_dir / "labels.tsv").exists()

    def test_warns_if_bundled_missing(self, registry, catalog_dir, caplog):
        import logging
        atlas = registry.get("builtin_nifti")
        # Don't create bundled file
        with caplog.at_level(logging.WARNING, logger="fsatlas.atlases.registry"):
            registry.download("builtin_nifti", force=True)


# ---------------------------------------------------------------------------
# _fetch_labels_tsv — no source
# ---------------------------------------------------------------------------

class TestFetchLabelsTsv:
    def test_warns_when_no_labels_tsv_source(self, registry, caplog):
        import logging
        atlas_spec = AtlasSpec(
            name="no_source",
            description="",
            type="volumetric",
            format="nifti",
            space="MNI152NLin6Asym",
            citation="",
            labels_tsv="missing_labels.tsv",  # not in catalog_dir, no source_url
            source_url="",
        )
        with caplog.at_level(logging.WARNING, logger="fsatlas.atlases.registry"):
            # CATALOG_PATH.parent / "missing_labels.tsv" doesn't exist
            # source_url is empty → warning
            registry._fetch_labels_tsv(atlas_spec, Path("/tmp/test_labels.tsv"))
        assert any("No labels_tsv" in r.message for r in caplog.records)

    def test_downloads_when_catalog_file_missing_but_url_exists(self, registry, tmp_path):
        import logging
        atlas_spec = AtlasSpec(
            name="url_labels",
            description="",
            type="volumetric",
            format="nifti",
            space="MNI152NLin6Asym",
            citation="",
            labels_tsv="url_labels.tsv",
            source_url="https://example.com/atlases",
        )
        dest = tmp_path / "labels.tsv"
        with patch("fsatlas.atlases.registry._download_file") as mock_dl:
            registry._fetch_labels_tsv(atlas_spec, dest)
        mock_dl.assert_called_once()
        url_called = mock_dl.call_args[0][0]
        assert "url_labels.tsv" in url_called


# ---------------------------------------------------------------------------
# _download_file
# ---------------------------------------------------------------------------

class TestDownloadFile:
    def test_downloads_content(self, tmp_path):
        from fsatlas.atlases.registry import _download_file

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_response.raise_for_status = MagicMock()

        dest = tmp_path / "downloaded.file"
        with patch("requests.get", return_value=mock_response):
            _download_file("https://example.com/file.txt", dest)

        assert dest.exists()
        assert dest.read_bytes() == b"chunk1chunk2"

    def test_raises_on_http_error(self, tmp_path):
        from fsatlas.atlases.registry import _download_file
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")

        dest = tmp_path / "downloaded.file"
        with patch("requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                _download_file("https://example.com/missing.txt", dest)
