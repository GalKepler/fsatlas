"""Tests for fsatlas.core.extract — stats file parsers and column definitions."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pandas as pd
import pytest

from fsatlas.core.extract import (
    CORTICAL_COLUMNS,
    CORTICAL_MEASURES,
    VOLUMETRIC_COLUMNS,
    VOLUMETRIC_MEASURES,
    _parse_cortical_stats_file,
    _parse_etiv_from_header,
    _parse_segstats_file,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal stats file content
# ---------------------------------------------------------------------------

CORTICAL_STATS_CONTENT = textwrap.dedent("""\
    # CreationTime 2023-09-01
    # Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1234567.0, mm^3
    # Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1500000.5, mm^3
    # ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd
    lh_precentral 5000 2500.0 8000.0 2.500 0.400 0.100 0.020 10 1.5
    lh_postcentral 4500 2200.0 7000.0 2.200 0.350 0.090 0.018 9 1.2
""")

SEGSTATS_CONTENT = textwrap.dedent("""\
    # CreationTime 2023-09-01
    # Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1234567.0, mm^3
    # Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1600000.0, mm^3
    # ColHeaders Index SegId NVoxels Volume_mm3 StructName normMean normStdDev normMin normMax normRange
    1 10 500 450.0 Left-Putamen 90.5 8.2 60.0 120.0 60.0
    2 20 600 550.0 Right-Putamen 88.0 7.5 55.0 115.0 60.0
    3 30 300 280.0 Left-Caudate 92.0 9.0 65.0 125.0 60.0
""")


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

class TestColumnDefinitions:
    def test_cortical_columns_count(self):
        assert len(CORTICAL_COLUMNS) == 10

    def test_cortical_columns_includes_struct_name(self):
        assert "StructName" in CORTICAL_COLUMNS

    def test_cortical_measures_maps_all_expected(self):
        expected_raw = {"NumVert", "SurfArea", "GrayVol", "ThickAvg", "ThickStd",
                        "MeanCurv", "GausCurv", "FoldInd", "CurvInd"}
        assert set(CORTICAL_MEASURES.keys()) == expected_raw

    def test_cortical_measures_output_names_unique(self):
        values = list(CORTICAL_MEASURES.values())
        assert len(values) == len(set(values))

    def test_volumetric_columns_count(self):
        assert len(VOLUMETRIC_COLUMNS) == 10

    def test_volumetric_columns_includes_seg_id(self):
        assert "SegId" in VOLUMETRIC_COLUMNS

    def test_volumetric_measures_maps_all_expected(self):
        expected_raw = {"NVoxels", "Volume_mm3", "normMean", "normStdDev",
                        "normMin", "normMax", "normRange"}
        assert set(VOLUMETRIC_MEASURES.keys()) == expected_raw

    def test_volumetric_measures_output_names_unique(self):
        values = list(VOLUMETRIC_MEASURES.values())
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# _parse_etiv_from_header
# ---------------------------------------------------------------------------

class TestParseEtivFromHeader:
    def test_parses_etiv_cortical_stats(self, tmp_path):
        f = tmp_path / "test.stats"
        f.write_text(CORTICAL_STATS_CONTENT)
        tiv = _parse_etiv_from_header(f)
        assert tiv == pytest.approx(1500000.5)

    def test_parses_etiv_segstats(self, tmp_path):
        f = tmp_path / "test.stats"
        f.write_text(SEGSTATS_CONTENT)
        tiv = _parse_etiv_from_header(f)
        assert tiv == pytest.approx(1600000.0)

    def test_returns_none_when_no_etiv(self, tmp_path):
        f = tmp_path / "test.stats"
        f.write_text("# No eTIV here\n1 region 100 200.0 name 90.0 5.0 60 120 60\n")
        tiv = _parse_etiv_from_header(f)
        assert tiv is None

    def test_handles_integer_etiv(self, tmp_path):
        f = tmp_path / "test.stats"
        f.write_text("# Measure eTIV, eTIV, Estimated Total Intracranial Volume, 1500000, mm^3\n")
        tiv = _parse_etiv_from_header(f)
        assert tiv == pytest.approx(1500000.0)


# ---------------------------------------------------------------------------
# _parse_cortical_stats_file
# ---------------------------------------------------------------------------

class TestParseCorticalStatsFile:
    def test_basic_parsing(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text(CORTICAL_STATS_CONTENT)
        df = _parse_cortical_stats_file(f)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

    def test_column_names(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text(CORTICAL_STATS_CONTENT)
        df = _parse_cortical_stats_file(f)
        assert list(df.columns) == CORTICAL_COLUMNS

    def test_struct_name_values(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text(CORTICAL_STATS_CONTENT)
        df = _parse_cortical_stats_file(f)
        assert "lh_precentral" in df["StructName"].values
        assert "lh_postcentral" in df["StructName"].values

    def test_numeric_columns(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text(CORTICAL_STATS_CONTENT)
        df = _parse_cortical_stats_file(f)
        assert df["ThickAvg"].dtype == float
        assert df.loc[df["StructName"] == "lh_precentral", "ThickAvg"].iloc[0] == pytest.approx(2.5)

    def test_raises_if_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _parse_cortical_stats_file(tmp_path / "nonexistent.stats")

    def test_returns_empty_df_if_no_data_rows(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text("# Only comments\n# No data\n")
        df = _parse_cortical_stats_file(f)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == CORTICAL_COLUMNS

    def test_skips_comment_lines(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text(CORTICAL_STATS_CONTENT)
        df = _parse_cortical_stats_file(f)
        # No comment rows in data
        assert not df["StructName"].str.startswith("#").any()

    def test_single_data_row(self, tmp_path):
        f = tmp_path / "lh.atlas.stats"
        f.write_text(
            "# comment\n"
            "lh_frontal 3000 1500.0 5000.0 2.300 0.300 0.080 0.015 8 1.0\n"
        )
        df = _parse_cortical_stats_file(f)
        assert len(df) == 1


# ---------------------------------------------------------------------------
# _parse_segstats_file
# ---------------------------------------------------------------------------

class TestParseSegstatsFile:
    def test_basic_parsing(self, tmp_path):
        f = tmp_path / "atlas.subcortical.stats"
        f.write_text(SEGSTATS_CONTENT)
        df = _parse_segstats_file(f)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_column_names(self, tmp_path):
        f = tmp_path / "atlas.subcortical.stats"
        f.write_text(SEGSTATS_CONTENT)
        df = _parse_segstats_file(f)
        assert list(df.columns) == VOLUMETRIC_COLUMNS

    def test_seg_id_values(self, tmp_path):
        f = tmp_path / "atlas.subcortical.stats"
        f.write_text(SEGSTATS_CONTENT)
        df = _parse_segstats_file(f)
        assert set(df["SegId"].values) == {10, 20, 30}

    def test_struct_name_values(self, tmp_path):
        f = tmp_path / "atlas.subcortical.stats"
        f.write_text(SEGSTATS_CONTENT)
        df = _parse_segstats_file(f)
        assert "Left-Putamen" in df["StructName"].values

    def test_volume_numeric(self, tmp_path):
        f = tmp_path / "atlas.subcortical.stats"
        f.write_text(SEGSTATS_CONTENT)
        df = _parse_segstats_file(f)
        assert df["Volume_mm3"].dtype == float

    def test_raises_if_file_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _parse_segstats_file(tmp_path / "nonexistent.stats")

    def test_returns_empty_df_if_no_data(self, tmp_path):
        f = tmp_path / "atlas.subcortical.stats"
        f.write_text("# only comments\n")
        df = _parse_segstats_file(f)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert list(df.columns) == VOLUMETRIC_COLUMNS
