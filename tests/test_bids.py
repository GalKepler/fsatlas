"""Tests for fsatlas.core.bids — BIDS entity parsing and path construction."""

from __future__ import annotations

from pathlib import Path

import pytest

from fsatlas.core.bids import BidsEntities, build_bids_path, parse_bids_entities


# ---------------------------------------------------------------------------
# parse_bids_entities
# ---------------------------------------------------------------------------

class TestParseBidsEntities:
    def test_sub_only(self):
        e = parse_bids_entities("sub-01")
        assert e.sub == "01"
        assert e.ses is None

    def test_sub_and_ses(self):
        e = parse_bids_entities("sub-01_ses-baseline")
        assert e.sub == "01"
        # ses should contain "baseline" (may have ".cross" appended)
        assert e.ses is not None
        assert "baseline" in e.ses

    def test_sub_alphanumeric(self):
        e = parse_bids_entities("sub-patient01")
        assert e.sub == "patient01"
        assert e.ses is None

    def test_non_bids_id_returns_sanitized(self):
        e = parse_bids_entities("patient123")
        assert e.sub == "patient123"
        assert e.ses is None

    def test_non_bids_with_special_chars_sanitized(self):
        e = parse_bids_entities("patient_123")
        # non-alphanumeric stripped
        assert e.sub == "patient123"
        assert e.ses is None

    def test_non_bids_empty_sanitized_to_unknown(self):
        e = parse_bids_entities("---")
        assert e.sub == "unknown"

    def test_non_bids_emits_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="fsatlas.core.bids"):
            parse_bids_entities("patient123")
        assert any("does not follow BIDS" in r.message for r in caplog.records)

    def test_bids_id_no_warning(self, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="fsatlas.core.bids"):
            parse_bids_entities("sub-01")
        assert not any("does not follow BIDS" in r.message for r in caplog.records)

    def test_sub_with_multiple_underscores(self):
        e = parse_bids_entities("sub-01_ses-tp1_task-rest")
        assert e.sub == "01"
        assert e.ses is not None
        assert "tp1" in e.ses


# ---------------------------------------------------------------------------
# build_bids_path
# ---------------------------------------------------------------------------

class TestBuildBidsPath:
    def test_without_session(self):
        entities = BidsEntities(sub="01", ses=None)
        p = build_bids_path(
            output_dir=Path("/output"),
            entities=entities,
            atlas_bids_name="Schaefer2018",
            structure="cortex",
        )
        assert str(p).startswith("/output/sub-01/anat/atlas-Schaefer2018/")
        assert p.name == "sub-01_atlas-Schaefer2018_structure-cortex.csv"

    def test_with_session(self):
        entities = BidsEntities(sub="01", ses="baseline")
        p = build_bids_path(
            output_dir=Path("/output"),
            entities=entities,
            atlas_bids_name="Tian2020",
            structure="subcortex",
        )
        assert "ses-baseline" in str(p)
        assert "sub-01_ses-baseline_atlas-Tian2020_structure-subcortex.csv" in str(p)

    def test_without_session_directory_structure(self):
        entities = BidsEntities(sub="42", ses=None)
        p = build_bids_path(Path("/out"), entities, "TestAtlas", "cortex")
        # path should be: /out/sub-42/anat/atlas-TestAtlas/sub-42_atlas-TestAtlas_structure-cortex.csv
        parts = p.parts
        assert "sub-42" in parts
        assert "anat" in parts
        assert "atlas-TestAtlas" in parts

    def test_with_session_directory_structure(self):
        entities = BidsEntities(sub="99", ses="tp2")
        p = build_bids_path(Path("/out"), entities, "HCP", "cortex")
        parts = p.parts
        assert "sub-99" in parts
        assert "ses-tp2" in parts
        assert "anat" in parts

    def test_output_dir_is_parent(self):
        output_dir = Path("/my/output/dir")
        entities = BidsEntities(sub="01", ses=None)
        p = build_bids_path(output_dir, entities, "Atlas", "cortex")
        assert str(p).startswith(str(output_dir))

    def test_returns_path_object(self):
        entities = BidsEntities(sub="01", ses=None)
        p = build_bids_path(Path("/out"), entities, "Atlas", "cortex")
        assert isinstance(p, Path)

    def test_filename_ends_with_csv(self):
        entities = BidsEntities(sub="01", ses=None)
        p = build_bids_path(Path("/out"), entities, "Atlas", "cortex")
        assert p.suffix == ".csv"
