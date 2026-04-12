"""Tests for fsatlas.atlases.registry — catalog loading and custom atlas factories."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from fsatlas.atlases.registry import (
    AtlasRegistry,
    AtlasSpec,
    CustomAtlasSpec,
    _infer_format,
)


# ---------------------------------------------------------------------------
# _infer_format
# ---------------------------------------------------------------------------

class TestInferFormat:
    @pytest.mark.parametrize("key,expected", [
        ("lh.dlabel.gii", "dlabel_gii"),
        ("atlas.gii", "dlabel_gii"),
        ("my_atlas.gca", "gca"),
        ("lh.annot", "annot"),
        ("atlas.nii.gz", "nifti"),
        ("atlas.nii", "nifti"),
    ])
    def test_infers_from_file_extension(self, key, expected):
        assert _infer_format("surface", {key: "remote_file"}) == expected

    def test_falls_back_surface_type_to_annot(self):
        assert _infer_format("surface", {"somefile.xyz": "file"}) == "annot"

    def test_falls_back_volumetric_type_to_nifti(self):
        assert _infer_format("volumetric", {"somefile.xyz": "file"}) == "nifti"

    def test_empty_files_uses_type(self):
        assert _infer_format("surface", {}) == "annot"
        assert _infer_format("volumetric", {}) == "nifti"


# ---------------------------------------------------------------------------
# Minimal catalog for testing
# ---------------------------------------------------------------------------

MINIMAL_CATALOG = {
    "test_surface": {
        "name": "test_surface",
        "description": "A test surface atlas",
        "type": "surface",
        "format": "annot",
        "space": "fsaverage",
        "source_url": "https://example.com/atlases",
        "files": {"lh.annot": "lh.test.annot", "rh.annot": "rh.test.annot"},
        "labels_tsv": "test_surface_labels.tsv",
        "builtin": False,
        "annot_name": "",
        "citation": "Test et al. 2023",
        "family": "TestFamily",
        "bids_name": "TestSurface",
    },
    "test_volumetric": {
        "name": "test_volumetric",
        "description": "A test volumetric atlas",
        "type": "volumetric",
        "format": "nifti",
        "space": "MNI152NLin6Asym",
        "source_url": "https://example.com/atlases",
        "files": {"atlas.nii.gz": "test_atlas.nii.gz"},
        "labels_tsv": "test_vol_labels.tsv",
        "builtin": False,
        "citation": "Volumetric et al. 2023",
        "family": "TestFamily",
        "bids_name": "TestVolumetric",
    },
    "test_builtin": {
        "name": "test_builtin",
        "description": "A built-in FreeSurfer atlas",
        "type": "surface",
        "format": "annot",
        "space": "fsaverage",
        "source_url": "",
        "files": {},
        "labels_tsv": "builtin_labels.tsv",
        "builtin": True,
        "annot_name": "aparc",
        "citation": "",
        "family": "FreeSurfer",
        "bids_name": "",
    },
}


@pytest.fixture
def catalog_file(tmp_path) -> Path:
    p = tmp_path / "catalog.yaml"
    p.write_text(yaml.dump(MINIMAL_CATALOG))
    return p


@pytest.fixture
def registry(catalog_file) -> AtlasRegistry:
    return AtlasRegistry(catalog_path=catalog_file)


# ---------------------------------------------------------------------------
# AtlasRegistry catalog loading
# ---------------------------------------------------------------------------

class TestAtlasRegistryCatalog:
    def test_loads_atlases(self, registry):
        atlases = registry.list_atlases()
        assert len(atlases) == 3

    def test_get_existing_atlas(self, registry):
        atlas = registry.get("test_surface")
        assert atlas.name == "test_surface"
        assert atlas.type == "surface"
        assert atlas.format == "annot"

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(KeyError, match="not found"):
            registry.get("nonexistent_atlas")

    def test_get_volumetric_atlas(self, registry):
        atlas = registry.get("test_volumetric")
        assert atlas.type == "volumetric"
        assert atlas.format == "nifti"

    def test_get_builtin_atlas(self, registry):
        atlas = registry.get("test_builtin")
        assert atlas.builtin is True
        assert atlas.annot_name == "aparc"

    def test_list_atlases_returns_all(self, registry):
        names = {a.name for a in registry.list_atlases()}
        assert names == {"test_surface", "test_volumetric", "test_builtin"}

    def test_loads_real_catalog(self):
        """Test that the real catalog can be loaded without errors."""
        registry = AtlasRegistry()
        atlases = registry.list_atlases()
        assert len(atlases) > 0

    def test_real_catalog_has_schaefer(self):
        registry = AtlasRegistry()
        names = [a.name for a in registry.list_atlases()]
        assert any("schaefer" in n.lower() for n in names)


# ---------------------------------------------------------------------------
# AtlasSpec properties
# ---------------------------------------------------------------------------

class TestAtlasSpecProperties:
    def test_structure_surface(self, registry):
        atlas = registry.get("test_surface")
        assert atlas.structure == "cortex"

    def test_structure_volumetric(self, registry):
        atlas = registry.get("test_volumetric")
        assert atlas.structure == "subcortex"

    def test_bids_atlas_name_uses_bids_name(self, registry):
        atlas = registry.get("test_surface")
        assert atlas.bids_atlas_name == "TestSurface"

    def test_bids_atlas_name_sanitizes_when_no_bids_name(self, registry):
        import re as _re
        atlas = registry.get("test_builtin")
        # bids_name is empty → sanitize the name (alphanumeric only)
        assert bool(_re.match(r"^[a-zA-Z0-9]+$", atlas.bids_atlas_name))

    def test_atlas_dir_contains_bids_name(self, registry):
        atlas = registry.get("test_surface")
        # atlas_dir is {atlas_root}/atlas-{bids_atlas_name}
        assert "atlas-TestSurface" in str(atlas.atlas_dir)

    def test_get_file_lh_annot_bids_name(self, registry):
        atlas = registry.get("test_surface")
        p = atlas.get_file("lh.annot")
        # BIDS-named: atlas-TestSurface_space-fsaverage_hemi-L_dseg.annot
        assert "hemi-L" in p.name
        assert p.name.endswith("_dseg.annot")

    def test_get_file_nifti(self, registry):
        atlas = registry.get("test_volumetric")
        p = atlas.get_file("atlas.nii.gz")
        assert p.name.endswith("_dseg.nii.gz")

    def test_get_file_unknown_key_raises(self, registry):
        atlas = registry.get("test_surface")
        with pytest.raises(KeyError):
            atlas.get_file("completely_unknown.xyz")

    def test_labels_tsv_path_none_when_dir_absent(self, registry):
        atlas = registry.get("test_surface")
        # atlas_dir doesn't exist => labels TSV not present
        assert atlas.labels_tsv_path is None

    def test_is_available_false_when_dir_absent(self, registry):
        atlas = registry.get("test_surface")
        assert atlas.is_available() is False

    # backward-compatible alias
    def test_is_downloaded_alias(self, registry):
        atlas = registry.get("test_surface")
        assert atlas.is_downloaded() is False

    def test_is_available_builtin_requires_only_lut(self, registry, tmp_path, monkeypatch):
        atlas = registry.get("test_builtin")
        # Point the atlas dir to tmp_path via env var
        monkeypatch.setenv("FSATLAS_ATLAS_DIR", str(tmp_path))
        atlas_subdir = tmp_path / f"atlas-{atlas.bids_atlas_name}"
        atlas_subdir.mkdir(parents=True)
        # Create the LUT file with the correct BIDS name
        lut_file = atlas_subdir / f"atlas-{atlas._safe_name}_dseg.tsv"
        lut_file.touch()
        assert atlas.is_available() is True


def re_sub_check(s: str) -> bool:
    """Check that a string contains only alphanumeric characters."""
    import re
    return bool(re.match(r"^[a-zA-Z0-9]+$", s))


# ---------------------------------------------------------------------------
# CustomAtlasSpec
# ---------------------------------------------------------------------------

class TestCustomAtlasSpec:
    def test_description_property(self):
        spec = CustomAtlasSpec(
            name="myatlas",
            type="surface",
            format="annot",
            paths={"lh.annot": Path("/tmp/lh.annot"), "rh.annot": Path("/tmp/rh.annot")},
        )
        assert "myatlas" in spec.description

    def test_citation_property(self):
        spec = CustomAtlasSpec(
            name="myatlas", type="surface", format="annot",
            paths={},
        )
        assert spec.citation == "User-provided"

    def test_builtin_property_false(self):
        spec = CustomAtlasSpec(
            name="myatlas", type="surface", format="annot",
            paths={},
        )
        assert spec.builtin is False

    def test_structure_surface(self):
        spec = CustomAtlasSpec(name="x", type="surface", format="annot", paths={})
        assert spec.structure == "cortex"

    def test_structure_volumetric(self):
        spec = CustomAtlasSpec(name="x", type="volumetric", format="nifti", paths={})
        assert spec.structure == "subcortex"

    def test_bids_atlas_name_sanitized(self):
        spec = CustomAtlasSpec(name="my atlas/v2", type="surface", format="annot", paths={})
        assert spec.bids_atlas_name == "myatlasv2"

    def test_labels_tsv_path_none_when_not_set(self):
        spec = CustomAtlasSpec(name="x", type="surface", format="annot", paths={})
        assert spec.labels_tsv_path is None

    def test_labels_tsv_path_set(self, tmp_path):
        lut = tmp_path / "lut.tsv"
        lut.touch()
        spec = CustomAtlasSpec(name="x", type="surface", format="annot",
                               paths={}, labels_tsv=lut)
        assert spec.labels_tsv_path == lut

    def test_get_file_success(self, tmp_path):
        p = tmp_path / "lh.annot"
        p.touch()
        spec = CustomAtlasSpec(name="x", type="surface", format="annot",
                               paths={"lh.annot": p})
        assert spec.get_file("lh.annot") == p

    def test_get_file_missing_raises(self):
        spec = CustomAtlasSpec(name="x", type="surface", format="annot", paths={})
        with pytest.raises(KeyError):
            spec.get_file("missing.annot")


# ---------------------------------------------------------------------------
# AtlasRegistry custom atlas factories
# ---------------------------------------------------------------------------

class TestFromCustomSurface:
    def test_creates_spec_from_existing_files(self, tmp_path):
        lh = tmp_path / "lh.aparc.annot"
        rh = tmp_path / "rh.aparc.annot"
        lh.touch()
        rh.touch()
        spec = AtlasRegistry.from_custom_surface(lh, rh, name="myatlas")
        assert spec.name == "myatlas"
        assert spec.format == "annot"
        assert spec.type == "surface"
        assert spec.paths["lh.annot"] == lh
        assert spec.paths["rh.annot"] == rh

    def test_name_inferred_from_lh_annot(self, tmp_path):
        lh = tmp_path / "lh.myatlas.annot"
        rh = tmp_path / "rh.myatlas.annot"
        lh.touch()
        rh.touch()
        spec = AtlasRegistry.from_custom_surface(lh, rh)
        # stem of lh.myatlas.annot without "lh." is "myatlas"
        assert "myatlas" in spec.name

    def test_raises_if_lh_missing(self, tmp_path):
        rh = tmp_path / "rh.aparc.annot"
        rh.touch()
        with pytest.raises(FileNotFoundError):
            AtlasRegistry.from_custom_surface(tmp_path / "nonexistent.annot", rh)

    def test_raises_if_rh_missing(self, tmp_path):
        lh = tmp_path / "lh.aparc.annot"
        lh.touch()
        with pytest.raises(FileNotFoundError):
            AtlasRegistry.from_custom_surface(lh, tmp_path / "nonexistent.annot")

    def test_labels_tsv_set_when_provided(self, tmp_path):
        lh = tmp_path / "lh.annot"
        rh = tmp_path / "rh.annot"
        lut = tmp_path / "labels.tsv"
        lh.touch()
        rh.touch()
        lut.touch()
        spec = AtlasRegistry.from_custom_surface(lh, rh, labels_tsv=lut)
        assert spec.labels_tsv == lut

    def test_default_space(self, tmp_path):
        lh = tmp_path / "lh.annot"
        rh = tmp_path / "rh.annot"
        lh.touch()
        rh.touch()
        spec = AtlasRegistry.from_custom_surface(lh, rh)
        assert spec.space == "fsaverage"


class TestFromCustomVolumetric:
    def test_creates_spec_from_existing_file(self, tmp_path):
        nii = tmp_path / "atlas.nii.gz"
        nii.touch()
        spec = AtlasRegistry.from_custom_volumetric(nii, name="myvol")
        assert spec.name == "myvol"
        assert spec.format == "nifti"
        assert spec.type == "volumetric"

    def test_name_inferred_from_path(self, tmp_path):
        nii = tmp_path / "myvol.nii.gz"
        nii.touch()
        spec = AtlasRegistry.from_custom_volumetric(nii)
        assert "myvol" in spec.name

    def test_raises_if_nifti_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            AtlasRegistry.from_custom_volumetric(tmp_path / "nonexistent.nii.gz")

    def test_default_space(self, tmp_path):
        nii = tmp_path / "atlas.nii.gz"
        nii.touch()
        spec = AtlasRegistry.from_custom_volumetric(nii)
        assert spec.space == "MNI152NLin2009cAsym"

    def test_labels_tsv_set(self, tmp_path):
        nii = tmp_path / "atlas.nii.gz"
        lut = tmp_path / "labels.tsv"
        nii.touch()
        lut.touch()
        spec = AtlasRegistry.from_custom_volumetric(nii, labels_tsv=lut)
        assert spec.labels_tsv == lut


class TestFromCustomDlabelGii:
    def test_creates_spec_from_existing_files(self, tmp_path):
        lh = tmp_path / "lh.atlas.dlabel.gii"
        rh = tmp_path / "rh.atlas.dlabel.gii"
        lh.touch()
        rh.touch()
        spec = AtlasRegistry.from_custom_dlabel_gii(lh, rh, name="myatlas")
        assert spec.name == "myatlas"
        assert spec.format == "dlabel_gii"

    def test_raises_if_file_missing(self, tmp_path):
        rh = tmp_path / "rh.dlabel.gii"
        rh.touch()
        with pytest.raises(FileNotFoundError):
            AtlasRegistry.from_custom_dlabel_gii(tmp_path / "nonexistent.gii", rh)


class TestFromCustomGca:
    def test_creates_spec_from_existing_file(self, tmp_path):
        gca = tmp_path / "myatlas.gca"
        gca.touch()
        spec = AtlasRegistry.from_custom_gca(gca, name="myatlas")
        assert spec.name == "myatlas"
        assert spec.format == "gca"
        assert spec.type == "volumetric"

    def test_space_is_subject(self, tmp_path):
        gca = tmp_path / "myatlas.gca"
        gca.touch()
        spec = AtlasRegistry.from_custom_gca(gca)
        assert spec.space == "subject"

    def test_raises_if_gca_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            AtlasRegistry.from_custom_gca(tmp_path / "nonexistent.gca")

    def test_name_inferred_from_path(self, tmp_path):
        gca = tmp_path / "BN_Atlas.gca"
        gca.touch()
        spec = AtlasRegistry.from_custom_gca(gca)
        assert spec.name == "BN_Atlas"
