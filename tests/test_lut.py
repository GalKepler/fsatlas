"""Tests for fsatlas.core.lut — LookupTable parsing, merging, and export."""

from __future__ import annotations

import gzip
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fsatlas.core.lut import (
    REQUIRED_COLS,
    LookupTable,
    _infer_hemisphere,
)


# ---------------------------------------------------------------------------
# _infer_hemisphere
# ---------------------------------------------------------------------------

class TestInferHemisphere:
    @pytest.mark.parametrize("label,expected", [
        # lh prefixes
        ("lh_precentral", "lh"),
        ("lh-precentral", "lh"),
        ("left_superior", "lh"),
        ("left-superior", "lh"),
        ("l_frontal", "lh"),
        # rh prefixes
        ("rh_postcentral", "rh"),
        ("rh-postcentral", "rh"),
        ("right_parietal", "rh"),
        ("right-parietal", "rh"),
        ("r_temporal", "rh"),
        # lh contained
        ("precentral_lh_gyrus", "lh"),
        ("precentral-lh-gyrus", "lh"),
        # rh contained
        ("postcentral_rh_gyrus", "rh"),
        ("postcentral-rh-gyrus", "rh"),
        # lh suffixes
        ("precentral-lh", "lh"),
        ("precentral_lh", "lh"),
        ("frontal-left", "lh"),
        ("frontal_left", "lh"),
        ("superior-l", "lh"),
        ("superior_l", "lh"),
        # rh suffixes
        ("postcentral-rh", "rh"),
        ("postcentral_rh", "rh"),
        ("parietal-right", "rh"),
        ("parietal_right", "rh"),
        ("temporal-r", "rh"),
        ("temporal_r", "rh"),
        # bilateral / unknown
        ("precentral", "bilateral"),
        ("Putamen", "bilateral"),
        ("Unknown_region", "bilateral"),
        # case insensitive
        ("LH_Frontal", "lh"),
        ("RH_Parietal", "rh"),
    ])
    def test_inference(self, label, expected):
        assert _infer_hemisphere(label) == expected


# ---------------------------------------------------------------------------
# LookupTable.from_tsv — format 1: header row
# ---------------------------------------------------------------------------

class TestFromTsvHeaderFormat:
    def test_basic_tsv_with_header(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("index\tlabel\themisphere\n1\tlh_precentral\tlh\n2\trh_postcentral\trh\n")
        lut = LookupTable.from_tsv(tsv)
        assert list(lut.df.columns[:3]) == REQUIRED_COLS
        assert len(lut.df) == 2
        assert lut.df.iloc[0]["index"] == 1
        assert lut.df.iloc[0]["label"] == "lh_precentral"
        assert lut.df.iloc[0]["hemisphere"] == "lh"

    def test_tsv_without_hemisphere_column_infers(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("index\tlabel\n1\tlh_precentral\n2\trh_postcentral\n")
        lut = LookupTable.from_tsv(tsv)
        assert "hemisphere" in lut.df.columns
        assert lut.df.iloc[0]["hemisphere"] == "lh"
        assert lut.df.iloc[1]["hemisphere"] == "rh"

    def test_tsv_preserves_extra_columns(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text(
            "index\tlabel\themisphere\tnetwork\n"
            "1\tlh_region_A\tlh\tDefault\n"
            "2\trh_region_B\trh\tVisual\n"
        )
        lut = LookupTable.from_tsv(tsv)
        assert "network" in lut.df.columns
        assert lut.df.iloc[0]["network"] == "Default"

    def test_tsv_skips_comment_lines(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("# comment\nindex\tlabel\n1\tRegionA\n2\tRegionB\n")
        lut = LookupTable.from_tsv(tsv)
        assert len(lut.df) == 2

    def test_tsv_index_cast_to_int(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("index\tlabel\n1\tRegionA\n2\tRegionB\n")
        lut = LookupTable.from_tsv(tsv)
        assert lut.df["index"].dtype == int

    def test_tsv_gzipped(self, tmp_path):
        content = b"index\tlabel\themisphere\n1\tlh_region\tlh\n"
        gz_path = tmp_path / "labels.tsv.gz"
        gz_path.write_bytes(gzip.compress(content))
        lut = LookupTable.from_tsv(gz_path)
        assert len(lut.df) == 1
        assert lut.df.iloc[0]["label"] == "lh_region"

    def test_tsv_empty_raises(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("# only comments\n")
        with pytest.raises(ValueError, match="empty"):
            LookupTable.from_tsv(tsv)


# ---------------------------------------------------------------------------
# LookupTable.from_tsv — format 2: two-column headerless
# ---------------------------------------------------------------------------

class TestFromTsvTwoColumnFormat:
    def test_two_column_space_separated(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("1 Precentral_L\n2 Postcentral_R\n")
        lut = LookupTable.from_tsv(tsv)
        assert len(lut.df) == 2
        assert lut.df.iloc[0]["index"] == 1
        assert lut.df.iloc[0]["label"] == "Precentral_L"

    def test_two_column_hemisphere_inferred(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("1 lh_precentral\n2 rh_postcentral\n")
        lut = LookupTable.from_tsv(tsv)
        assert lut.df.iloc[0]["hemisphere"] == "lh"
        assert lut.df.iloc[1]["hemisphere"] == "rh"


# ---------------------------------------------------------------------------
# LookupTable.from_tsv — format 3: name-only headerless
# ---------------------------------------------------------------------------

class TestFromTsvNameOnlyFormat:
    def test_name_only_assigns_1based_indices(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("RegionA\nRegionB\nRegionC\n")
        lut = LookupTable.from_tsv(tsv)
        assert list(lut.df["index"]) == [1, 2, 3]
        assert list(lut.df["label"]) == ["RegionA", "RegionB", "RegionC"]


# ---------------------------------------------------------------------------
# LookupTable.to_tsv / to_ctab
# ---------------------------------------------------------------------------

class TestLookupTableExport:
    def _make_lut(self) -> LookupTable:
        df = pd.DataFrame({
            "index": [1, 2],
            "label": ["lh_region_A", "rh_region_B"],
            "hemisphere": ["lh", "rh"],
        })
        return LookupTable(df=df)

    def test_to_tsv_roundtrip(self, tmp_path):
        lut = self._make_lut()
        out = tmp_path / "out.tsv"
        lut.to_tsv(out)
        lut2 = LookupTable.from_tsv(out)
        pd.testing.assert_frame_equal(lut.df.reset_index(drop=True), lut2.df.reset_index(drop=True))

    def test_to_ctab_format(self, tmp_path):
        lut = self._make_lut()
        ctab_path = lut.to_ctab()
        try:
            lines = Path(ctab_path).read_text().splitlines()
            assert len(lines) == 2
            parts = lines[0].split()
            # index label R G B A
            assert len(parts) == 6
            assert parts[0] == "1"
            assert parts[1] == "lh_region_A"
            # default grey colours
            assert parts[2] == "100"
        finally:
            Path(ctab_path).unlink(missing_ok=True)

    def test_to_ctab_uses_color_columns(self, tmp_path):
        df = pd.DataFrame({
            "index": [1],
            "label": ["Region"],
            "hemisphere": ["bilateral"],
            "color_r": [200],
            "color_g": [150],
            "color_b": [50],
            "color_a": [255],
        })
        lut = LookupTable(df=df)
        ctab_path = lut.to_ctab()
        try:
            line = Path(ctab_path).read_text().strip()
            parts = line.split()
            assert parts[2] == "200"
            assert parts[3] == "150"
            assert parts[4] == "50"
            assert parts[5] == "255"
        finally:
            Path(ctab_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# LookupTable.merge_measures — label-based join (cortical)
# ---------------------------------------------------------------------------

class TestMergeMeasuresLabel:
    def _make_lut(self) -> LookupTable:
        df = pd.DataFrame({
            "index": [1, 2, 3],
            "label": ["lh_precentral", "rh_postcentral", "lh_superior"],
            "hemisphere": ["lh", "rh", "lh"],
        })
        return LookupTable(df=df)

    def _make_raw_stats(self) -> pd.DataFrame:
        return pd.DataFrame({
            "StructName": ["lh_precentral", "rh_postcentral"],
            "NumVert": [1000, 2000],
            "ThickAvg": [2.5, 3.1],
            "SurfArea": [500.0, 800.0],
        })

    def test_join_on_label_basic(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        measure_map = {"NumVert": "num_vertices", "ThickAvg": "thickness_mean_mm"}
        result = lut.merge_measures(raw, subject_id="sub-01", tiv=1500000.0, measure_map=measure_map)
        assert "subject_id" in result.columns
        assert result.iloc[0]["subject_id"] == "sub-01"
        assert "num_vertices" in result.columns
        assert "thickness_mean_mm" in result.columns
        assert "tiv_mm3" in result.columns

    def test_tiv_propagated(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=1234567.8,
                                    measure_map={"ThickAvg": "thickness_mean_mm"})
        assert (result["tiv_mm3"] == 1234567.8).all()

    def test_tiv_none_becomes_nan(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"ThickAvg": "thickness_mean_mm"})
        assert result["tiv_mm3"].isna().all()

    def test_unmatched_region_is_nan(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"ThickAvg": "thickness_mean_mm"})
        # lh_superior has no stats row → should be NaN
        unmatched = result[result["label"] == "lh_superior"]
        assert unmatched["thickness_mean_mm"].isna().all()

    def test_subject_id_is_first_column(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"ThickAvg": "thickness_mean_mm"})
        assert result.columns[0] == "subject_id"

    def test_measure_columns_cast_to_float(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"NumVert": "num_vertices"})
        assert result["num_vertices"].dtype == float

    def test_extra_lut_cols_preserved(self):
        df = pd.DataFrame({
            "index": [1, 2],
            "label": ["lh_precentral", "rh_postcentral"],
            "hemisphere": ["lh", "rh"],
            "network": ["Default", "Visual"],
        })
        lut = LookupTable(df=df)
        raw = pd.DataFrame({
            "StructName": ["lh_precentral"],
            "ThickAvg": [2.5],
        })
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"ThickAvg": "thickness_mean_mm"})
        assert "network" in result.columns


# ---------------------------------------------------------------------------
# LookupTable.merge_measures — index-based join (volumetric)
# ---------------------------------------------------------------------------

class TestMergeMeasuresIndex:
    def _make_lut(self) -> LookupTable:
        df = pd.DataFrame({
            "index": [10, 20, 30],
            "label": ["Left-Putamen", "Right-Putamen", "Left-Caudate"],
            "hemisphere": ["lh", "rh", "lh"],
        })
        return LookupTable(df=df)

    def _make_raw_stats(self) -> pd.DataFrame:
        return pd.DataFrame({
            "SegId": [10, 20],
            "NVoxels": [500, 600],
            "Volume_mm3": [450.0, 550.0],
            "normMean": [90.0, 88.5],
        })

    def test_join_on_index_basic(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        measure_map = {"NVoxels": "num_voxels", "Volume_mm3": "volume_mm3"}
        result = lut.merge_measures(raw, "sub-01", tiv=1600000.0,
                                    measure_map=measure_map, join_on="index")
        assert "num_voxels" in result.columns
        assert "volume_mm3" in result.columns

    def test_unmatched_index_is_nan(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"NVoxels": "num_voxels"}, join_on="index")
        unmatched = result[result["label"] == "Left-Caudate"]
        assert unmatched["num_voxels"].isna().all()

    def test_result_has_all_lut_rows(self):
        lut = self._make_lut()
        raw = self._make_raw_stats()
        result = lut.merge_measures(raw, "sub-01", tiv=None,
                                    measure_map={"NVoxels": "num_voxels"}, join_on="index")
        assert len(result) == 3  # all LUT rows preserved


# ---------------------------------------------------------------------------
# LookupTable._finalise edge cases
# ---------------------------------------------------------------------------

class TestFinalise:
    def test_case_insensitive_column_normalisation(self, tmp_path):
        # from_tsv lowercases column headers
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("Index\tLabel\tHemisphere\n1\tRegionA\tlh\n")
        lut = LookupTable.from_tsv(tsv)
        assert "index" in lut.df.columns
        assert "label" in lut.df.columns

    def test_hemisphere_inferred_when_missing(self, tmp_path):
        tsv = tmp_path / "labels.tsv"
        tsv.write_text("index\tlabel\n1\tlh_frontal\n2\trh_parietal\n")
        lut = LookupTable.from_tsv(tsv)
        assert lut.df.iloc[0]["hemisphere"] == "lh"
        assert lut.df.iloc[1]["hemisphere"] == "rh"
