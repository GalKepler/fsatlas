"""Tests for fsatlas.core.aggregate."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fsatlas.core.aggregate import (
    _parse_entities_from_path,
    _standardize_dataframe,
    aggregate,
    discover_atlases,
    discover_csv_files,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CORTICAL_COLS = [
    "subject_id", "index", "label", "hemisphere", "hemi",
    "num_vertices", "surface_area_mm2", "gray_matter_volume_mm3",
    "thickness_mean_mm", "thickness_std_mm", "mean_curvature",
    "gaussian_curvature", "folding_index", "curvature_index", "tiv_mm3",
]
_SUBCORTICAL_COLS = [
    "subject_id", "index", "label", "name", "hemisphere", "structure",
    "num_voxels", "volume_mm3", "intensity_mean", "intensity_std",
    "intensity_min", "intensity_max", "intensity_range", "tiv_mm3",
]


def _make_cortical_csv(path: Path, subject_id: str, n_regions: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "subject_id": subject_id,
            "index": i,
            "label": f"region_{i}",
            "hemisphere": "bilateral",
            "hemi": "lh" if i % 2 == 0 else "rh",
            "num_vertices": 100 * i,
            "surface_area_mm2": 50.0 * i,
            "gray_matter_volume_mm3": 200.0 * i,
            "thickness_mean_mm": 2.5,
            "thickness_std_mm": 0.3,
            "mean_curvature": 0.1,
            "gaussian_curvature": 0.01,
            "folding_index": 5,
            "curvature_index": 0.5,
            "tiv_mm3": 1500000.0,
        }
        for i in range(1, n_regions + 1)
    ]
    pd.DataFrame(rows, columns=_CORTICAL_COLS).to_csv(path, index=False)


def _make_subcortical_csv(path: Path, subject_id: str, n_regions: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "subject_id": subject_id,
            "index": i,
            "label": f"subcortex_{i}",
            "name": f"subcortex_{i}",
            "hemisphere": "L" if i % 2 == 0 else "R",
            "structure": "subcortex",
            "num_voxels": 1000 * i,
            "volume_mm3": 1000.0 * i,
            "intensity_mean": 80.0,
            "intensity_std": 10.0,
            "intensity_min": 50.0,
            "intensity_max": 110.0,
            "intensity_range": 60.0,
            "tiv_mm3": 1500000.0,
        }
        for i in range(1, n_regions + 1)
    ]
    pd.DataFrame(rows, columns=_SUBCORTICAL_COLS).to_csv(path, index=False)


@pytest.fixture()
def bids_dir(tmp_path: Path) -> Path:
    """BIDS directory with 2 subjects, 1 atlas, cortex + subcortex."""
    atlas = "TestAtlas"
    for sub in ["S001", "S002"]:
        subject_id = f"sub-{sub}"
        anat = tmp_path / subject_id / "anat" / f"atlas-{atlas}"
        _make_cortical_csv(
            anat / f"{subject_id}_atlas-{atlas}_structure-cortex.csv",
            subject_id,
        )
        _make_subcortical_csv(
            anat / f"{subject_id}_atlas-{atlas}_structure-subcortex.csv",
            subject_id,
        )
    return tmp_path


@pytest.fixture()
def bids_dir_with_session(tmp_path: Path) -> Path:
    """BIDS directory with session-level layout."""
    atlas = "TestAtlas"
    sub, ses = "S001", "baseline.cross"
    subject_id = f"sub-{sub}"
    anat = tmp_path / subject_id / f"ses-{ses}" / "anat" / f"atlas-{atlas}"
    _make_cortical_csv(
        anat / f"{subject_id}_ses-{ses}_atlas-{atlas}_structure-cortex.csv",
        subject_id,
    )
    return tmp_path


# ---------------------------------------------------------------------------
# discover_atlases
# ---------------------------------------------------------------------------

class TestDiscoverAtlases:
    def test_finds_atlases(self, bids_dir: Path):
        atlases = discover_atlases(bids_dir)
        assert atlases == ["TestAtlas"]

    def test_multiple_atlases(self, tmp_path: Path):
        for atlas in ["AtlasA", "AtlasB"]:
            d = tmp_path / "sub-01" / "anat" / f"atlas-{atlas}"
            d.mkdir(parents=True)
        assert discover_atlases(tmp_path) == ["AtlasA", "AtlasB"]

    def test_session_layout(self, bids_dir_with_session: Path):
        atlases = discover_atlases(bids_dir_with_session)
        assert "TestAtlas" in atlases

    def test_empty_dir(self, tmp_path: Path):
        assert discover_atlases(tmp_path) == []


# ---------------------------------------------------------------------------
# discover_csv_files
# ---------------------------------------------------------------------------

class TestDiscoverCsvFiles:
    def test_finds_both_structures(self, bids_dir: Path):
        files = discover_csv_files(bids_dir, "TestAtlas")
        assert len(files) == 4  # 2 subjects × 2 structures

    def test_filter_by_structure_cortex(self, bids_dir: Path):
        files = discover_csv_files(bids_dir, "TestAtlas", structure="cortex")
        assert len(files) == 2
        assert all("structure-cortex" in f.name for f in files)

    def test_filter_by_structure_subcortex(self, bids_dir: Path):
        files = discover_csv_files(bids_dir, "TestAtlas", structure="subcortex")
        assert len(files) == 2
        assert all("structure-subcortex" in f.name for f in files)

    def test_filter_by_subjects(self, bids_dir: Path):
        files = discover_csv_files(bids_dir, "TestAtlas", subjects=["S001"])
        assert len(files) == 2
        assert all("sub-S001" in str(f) for f in files)

    def test_unknown_subject_returns_empty(self, bids_dir: Path):
        files = discover_csv_files(bids_dir, "TestAtlas", subjects=["XXXX"])
        assert files == []

    def test_unknown_atlas_returns_empty(self, bids_dir: Path):
        files = discover_csv_files(bids_dir, "NoSuchAtlas")
        assert files == []

    def test_session_layout_discovered(self, bids_dir_with_session: Path):
        files = discover_csv_files(bids_dir_with_session, "TestAtlas", structure="cortex")
        assert len(files) == 1


# ---------------------------------------------------------------------------
# _parse_entities_from_path
# ---------------------------------------------------------------------------

class TestParseEntitiesFromPath:
    def test_no_session(self):
        p = Path("sub-S001_atlas-TestAtlas_structure-cortex.csv")
        e = _parse_entities_from_path(p)
        assert e == {"sub": "S001", "ses": None, "atlas": "TestAtlas", "structure": "cortex"}

    def test_with_session(self):
        p = Path("sub-S001_ses-baseline_atlas-TestAtlas_structure-subcortex.csv")
        e = _parse_entities_from_path(p)
        assert e["ses"] == "baseline"
        assert e["structure"] == "subcortex"

    def test_with_dotted_session(self):
        p = Path("sub-S001_ses-baseline.cross_atlas-TestAtlas_structure-cortex.csv")
        e = _parse_entities_from_path(p)
        assert e["ses"] == "baseline.cross"

    def test_invalid_filename_raises(self):
        p = Path("not_a_bids_file.csv")
        with pytest.raises(ValueError, match="Cannot parse BIDS"):
            _parse_entities_from_path(p)


# ---------------------------------------------------------------------------
# _standardize_dataframe
# ---------------------------------------------------------------------------

class TestStandardizeDataframe:
    def test_cortex_drops_extra_cols(self, tmp_path: Path):
        csv = tmp_path / "sub-S001_atlas-TestAtlas_structure-cortex.csv"
        _make_cortical_csv(csv, "sub-S001")
        df = pd.read_csv(csv)
        out = _standardize_dataframe(df, "cortex", "TestAtlas", None)
        assert "hemi" not in out.columns
        assert "num_vertices" in out.columns
        assert "tiv_mm3" in out.columns

    def test_subcortex_drops_extra_cols(self, tmp_path: Path):
        csv = tmp_path / "sub-S001_atlas-TestAtlas_structure-subcortex.csv"
        _make_subcortical_csv(csv, "sub-S001")
        df = pd.read_csv(csv)
        out = _standardize_dataframe(df, "subcortex", "TestAtlas", None)
        assert "name" not in out.columns
        assert "structure" in out.columns  # metadata column injected by _standardize
        assert "num_voxels" in out.columns

    def test_metadata_columns_injected(self, tmp_path: Path):
        csv = tmp_path / "sub-S001_atlas-TestAtlas_structure-cortex.csv"
        _make_cortical_csv(csv, "sub-S001")
        df = pd.read_csv(csv)
        out = _standardize_dataframe(df, "cortex", "TestAtlas", "baseline.cross")
        assert list(out.columns[:4]) == ["subject_id", "session", "atlas", "structure"]
        assert out["session"].iloc[0] == "baseline.cross"
        assert out["atlas"].iloc[0] == "TestAtlas"
        assert out["structure"].iloc[0] == "cortex"

    def test_session_none_preserved(self, tmp_path: Path):
        csv = tmp_path / "sub-S001_atlas-TestAtlas_structure-cortex.csv"
        _make_cortical_csv(csv, "sub-S001")
        df = pd.read_csv(csv)
        out = _standardize_dataframe(df, "cortex", "TestAtlas", None)
        assert pd.isna(out["session"].iloc[0])


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

class TestAggregate:
    def test_basic_both_structures(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas")
        assert not result.empty
        assert set(result["structure"].unique()) == {"cortex", "subcortex"}
        assert result["subject_id"].nunique() == 2

    def test_cortex_only(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas", structures=["cortex"])
        assert set(result["structure"].unique()) == {"cortex"}

    def test_subcortex_only(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas", structures=["subcortex"])
        assert set(result["structure"].unique()) == {"subcortex"}

    def test_subject_filter(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas", subjects=["S001"])
        assert result["subject_id"].unique().tolist() == ["sub-S001"]

    def test_unknown_atlas_returns_empty(self, bids_dir: Path):
        result = aggregate(bids_dir, "NoSuchAtlas")
        assert result.empty

    def test_sorted_output(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas")
        # subject_id column should be sorted
        subjects = result["subject_id"].tolist()
        assert subjects == sorted(subjects)

    def test_tiv_column_present(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas")
        assert "tiv_mm3" in result.columns

    def test_mixed_structures_nan_for_nonapplicable_measures(self, bids_dir: Path):
        result = aggregate(bids_dir, "TestAtlas")
        cortex_rows = result[result["structure"] == "cortex"]
        subcortex_rows = result[result["structure"] == "subcortex"]
        # cortex rows should have cortical measures
        assert cortex_rows["num_vertices"].notna().all()
        # subcortex rows should have subcortical measures
        assert subcortex_rows["num_voxels"].notna().all()

    def test_session_layout(self, bids_dir_with_session: Path):
        result = aggregate(bids_dir_with_session, "TestAtlas", structures=["cortex"])
        assert not result.empty
        assert result["session"].notna().all()
