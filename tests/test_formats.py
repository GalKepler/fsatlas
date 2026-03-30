"""Tests for fsatlas.core.formats — handler registry, utilities, TransferResult."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fsatlas.atlases.registry import AtlasSpec, CustomAtlasSpec
from fsatlas.core.formats import (
    FORMAT_HANDLERS,
    AnnotHandler,
    GcaHandler,
    NiftiHandler,
    TransferResult,
    _AnnotProxy,
    _atlas_annot_name,
    _get_nifti_file,
    get_handler,
)


# ---------------------------------------------------------------------------
# _atlas_annot_name
# ---------------------------------------------------------------------------

class TestAtlasAnnotName:
    def test_basic_name(self):
        spec = MagicMock()
        spec.name = "schaefer100"
        assert _atlas_annot_name(spec) == "schaefer100"

    def test_slashes_replaced(self):
        spec = MagicMock()
        spec.name = "schaefer/100"
        assert _atlas_annot_name(spec) == "schaefer_100"

    def test_spaces_replaced(self):
        spec = MagicMock()
        spec.name = "my atlas"
        assert _atlas_annot_name(spec) == "my_atlas"

    def test_combined(self):
        spec = MagicMock()
        spec.name = "my/atlas name"
        assert _atlas_annot_name(spec) == "my_atlas_name"


# ---------------------------------------------------------------------------
# _get_nifti_file
# ---------------------------------------------------------------------------

class TestGetNiftiFile:
    def _make_custom_spec(self, paths: dict) -> CustomAtlasSpec:
        return CustomAtlasSpec(
            name="testatlas",
            type="volumetric",
            format="nifti",
            paths={k: Path(v) for k, v in paths.items()},
        )

    def test_finds_atlas_nii_gz(self):
        spec = self._make_custom_spec({"atlas.nii.gz": "/tmp/atlas.nii.gz"})
        p = _get_nifti_file(spec)
        assert p == Path("/tmp/atlas.nii.gz")

    def test_finds_atlas_nii(self):
        spec = self._make_custom_spec({"atlas.nii": "/tmp/atlas.nii"})
        p = _get_nifti_file(spec)
        assert p == Path("/tmp/atlas.nii")

    def test_finds_nii_gz_by_extension_fallback(self):
        spec = self._make_custom_spec({"custom_name.nii.gz": "/tmp/custom_name.nii.gz"})
        p = _get_nifti_file(spec)
        assert p == Path("/tmp/custom_name.nii.gz")

    def test_raises_if_no_nifti_found(self):
        spec = self._make_custom_spec({"some_file.gca": "/tmp/file.gca"})
        with pytest.raises(KeyError, match="No NIfTI"):
            _get_nifti_file(spec)


# ---------------------------------------------------------------------------
# TransferResult
# ---------------------------------------------------------------------------

class TestTransferResult:
    def test_default_values(self):
        tr = TransferResult()
        assert tr.paths == {}
        assert tr.format_id == ""

    def test_construction(self):
        paths = {"lh": Path("/tmp/lh.annot"), "rh": Path("/tmp/rh.annot")}
        tr = TransferResult(paths=paths, format_id="annot")
        assert tr.paths == paths
        assert tr.format_id == "annot"


# ---------------------------------------------------------------------------
# FORMAT_HANDLERS registry / get_handler
# ---------------------------------------------------------------------------

class TestFormatHandlers:
    def test_all_formats_registered(self):
        for fmt in ("annot", "nifti", "dlabel_gii", "gca"):
            assert fmt in FORMAT_HANDLERS

    def test_get_handler_returns_correct_type(self):
        assert isinstance(get_handler("annot"), AnnotHandler)
        assert isinstance(get_handler("nifti"), NiftiHandler)
        assert isinstance(get_handler("gca"), GcaHandler)

    def test_get_handler_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown atlas format"):
            get_handler("unknown_format")

    def test_annot_handler_format_id(self):
        assert get_handler("annot").format_id == "annot"

    def test_nifti_handler_join_on_index(self):
        assert get_handler("nifti").join_on == "index"

    def test_annot_handler_join_on_label(self):
        assert get_handler("annot").join_on == "label"

    def test_gca_handler_join_on_index(self):
        assert get_handler("gca").join_on == "index"

    def test_dlabel_gii_join_on_label(self):
        assert get_handler("dlabel_gii").join_on == "label"


# ---------------------------------------------------------------------------
# _AnnotProxy
# ---------------------------------------------------------------------------

class TestAnnotProxy:
    def test_delegates_attribute_to_atlas(self):
        atlas = MagicMock()
        atlas.name = "myatlas"
        proxy = _AnnotProxy(atlas, {})
        assert proxy.name == "myatlas"

    def test_get_file_returns_annot_path(self, tmp_path):
        atlas = MagicMock()
        annot_paths = {"lh": tmp_path / "lh.annot", "rh": tmp_path / "rh.annot"}
        proxy = _AnnotProxy(atlas, annot_paths)
        assert proxy.get_file("lh") == tmp_path / "lh.annot"

    def test_get_file_delegates_to_atlas_for_other_keys(self, tmp_path):
        atlas = MagicMock()
        atlas.get_file.return_value = tmp_path / "other.file"
        proxy = _AnnotProxy(atlas, {"lh": tmp_path / "lh.annot"})
        result = proxy.get_file("some_other_key")
        atlas.get_file.assert_called_once_with("some_other_key")


# ---------------------------------------------------------------------------
# AnnotHandler.transfer — builtin atlas path
# ---------------------------------------------------------------------------

class TestAnnotHandlerTransferBuiltin:
    def _make_builtin_atlas(self, annot_name: str = "aparc") -> MagicMock:
        atlas = MagicMock(spec=AtlasSpec)
        atlas.builtin = True
        atlas.name = "desikan"
        atlas.annot_name = annot_name
        return atlas

    def _make_subject(self, tmp_path: Path, annot_name: str = "aparc") -> MagicMock:
        label_dir = tmp_path / "label"
        label_dir.mkdir(parents=True)
        lh = label_dir / f"lh.{annot_name}.annot"
        rh = label_dir / f"rh.{annot_name}.annot"
        lh.touch()
        rh.touch()
        subject = MagicMock()
        subject.annot_path.side_effect = lambda hemi, name: label_dir / f"{hemi}.{name}.annot"
        subject.label_dir = label_dir
        return subject

    def test_builtin_returns_existing_annot_paths(self, tmp_path):
        atlas = self._make_builtin_atlas("aparc")
        subject = self._make_subject(tmp_path, "aparc")
        env = MagicMock()
        handler = AnnotHandler()
        result = handler.transfer(atlas, subject, env)
        assert isinstance(result, TransferResult)
        assert "lh" in result.paths
        assert "rh" in result.paths

    def test_builtin_raises_if_annot_missing(self, tmp_path):
        atlas = self._make_builtin_atlas("aparc")
        # Subject with no annot files
        label_dir = tmp_path / "label"
        label_dir.mkdir(parents=True)
        subject = MagicMock()
        subject.annot_path.side_effect = lambda hemi, name: label_dir / f"{hemi}.{name}.annot"
        env = MagicMock()
        handler = AnnotHandler()
        with pytest.raises(FileNotFoundError):
            handler.transfer(atlas, subject, env)


# ---------------------------------------------------------------------------
# NiftiHandler — aseg builtin shortcut
# ---------------------------------------------------------------------------

class TestNiftiHandlerTransferAseg:
    def test_aseg_builtin_returns_aseg_mgz(self, tmp_path):
        atlas = MagicMock()
        atlas.builtin = True
        atlas.name = "aseg"
        aseg = tmp_path / "aseg.mgz"
        aseg.touch()
        subject = MagicMock()
        subject.aseg_mgz = aseg
        env = MagicMock()
        handler = NiftiHandler()
        result = handler.transfer(atlas, subject, env)
        assert result.paths["volume"] == aseg
        assert result.format_id == "nifti"


# ---------------------------------------------------------------------------
# GcaHandler.transfer — missing transforms
# ---------------------------------------------------------------------------

class TestGcaHandlerTransfer:
    def _make_gca_atlas(self, tmp_path: Path) -> tuple[MagicMock, Path]:
        gca_file = tmp_path / "myatlas.gca"
        gca_file.touch()
        atlas = MagicMock()
        atlas.name = "myatlas"
        atlas.builtin = False
        atlas.get_file.return_value = gca_file
        return atlas, gca_file

    def test_raises_if_no_transform_found(self, tmp_path):
        atlas, _ = self._make_gca_atlas(tmp_path)
        # Subject with no transform files
        mri_dir = tmp_path / "mri"
        transforms_dir = mri_dir / "transforms"
        transforms_dir.mkdir(parents=True)
        atlas_out_dir = mri_dir / "atlas"

        subject = MagicMock()
        subject.mri_dir = mri_dir
        subject.talairach_m3z = transforms_dir / "talairach.m3z"  # doesn't exist
        subject.talairach_xfm = transforms_dir / "talairach.xfm"  # doesn't exist

        env = MagicMock()
        handler = GcaHandler()
        with pytest.raises(FileNotFoundError, match="Talairach"):
            handler.transfer(atlas, subject, env)

    def test_skips_if_output_exists_no_overwrite(self, tmp_path):
        atlas, _ = self._make_gca_atlas(tmp_path)
        mri_dir = tmp_path / "mri"
        atlas_dir = mri_dir / "atlas"
        atlas_dir.mkdir(parents=True)
        out_path = atlas_dir / "myatlas_native.mgz"
        out_path.touch()

        subject = MagicMock()
        subject.mri_dir = mri_dir

        env = MagicMock()
        handler = GcaHandler()
        result = handler.transfer(atlas, subject, env, overwrite=False)
        assert result.paths["volume"] == out_path
        # run_command should not have been called
        env.assert_not_called()
