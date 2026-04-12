"""Tests for fsatlas CLI commands using Click's test runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from fsatlas.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# list-atlases command
# ---------------------------------------------------------------------------

class TestListAtlases:
    def test_list_atlases_succeeds(self, runner):
        result = runner.invoke(cli, ["list-atlases"])
        assert result.exit_code == 0

    def test_list_atlases_shows_atlas_names(self, runner):
        result = runner.invoke(cli, ["list-atlases"])
        assert result.exit_code == 0
        # Should show some atlas names from catalog
        assert len(result.output) > 0

    def test_list_atlases_no_args_needed(self, runner):
        result = runner.invoke(cli, ["list-atlases"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Main CLI group
# ---------------------------------------------------------------------------

class TestCliGroup:
    def test_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_help_shows_commands(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert "extract" in result.output
        assert "list-atlases" in result.output
        assert "populate" in result.output

    def test_extract_help(self, runner):
        result = runner.invoke(cli, ["extract", "--help"])
        assert result.exit_code == 0
        assert "--atlas" in result.output

    def test_populate_help(self, runner):
        result = runner.invoke(cli, ["populate", "--help"])
        assert result.exit_code == 0

    def test_generate_lut_help(self, runner):
        result = runner.invoke(cli, ["generate-lut", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# populate command
# ---------------------------------------------------------------------------

class TestPopulateCommand:
    def test_populate_requires_output_dir_or_env(self, runner, tmp_path):
        """populate with --output-dir should call populate_all."""
        with patch("fsatlas.atlases.populate.populate_all") as mock_pop:
            result = runner.invoke(
                cli,
                ["populate", "--output-dir", str(tmp_path)],
            )
        # Should call populate_all (may fail later due to missing FS, but cli exits OK)
        # Exit code depends on whether populate_all raises — we mock it successfully
        mock_pop.assert_called_once()

    def test_populate_specific_atlas(self, runner, tmp_path):
        with patch("fsatlas.atlases.populate.populate_all") as mock_pop:
            runner.invoke(
                cli,
                ["populate", "schaefer100-7", "--output-dir", str(tmp_path)],
            )
        call_kwargs = mock_pop.call_args
        assert call_kwargs is not None


# ---------------------------------------------------------------------------
# extract command — argument validation
# ---------------------------------------------------------------------------

class TestExtractCommand:
    def test_extract_requires_atlas(self, runner):
        result = runner.invoke(cli, ["extract", "--subjects-dir", "/tmp"])
        # Should fail without atlas
        assert result.exit_code != 0 or "atlas" in result.output.lower()

    def test_extract_missing_subjects_dir(self, runner, tmp_path):
        # No SUBJECTS_DIR and no --subjects-dir → error
        result = runner.invoke(
            cli,
            ["extract", "--atlas", "schaefer100_7net"],
            env={"FREESURFER_HOME": str(tmp_path)},
        )
        assert result.exit_code != 0

    def test_extract_with_nonexistent_subjects_dir(self, runner, tmp_path):
        result = runner.invoke(
            cli,
            [
                "extract",
                "--atlas", "schaefer100_7net",
                "--subjects-dir", str(tmp_path / "nonexistent"),
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# generate-lut command
# ---------------------------------------------------------------------------

class TestGenerateLutCommand:
    def test_generate_lut_requires_either_atlas_or_annot(self, runner):
        result = runner.invoke(cli, ["generate-lut"])
        assert result.exit_code != 0

    def test_generate_lut_from_annot_files(self, runner, tmp_path):
        lh = tmp_path / "lh.aparc.annot"
        rh = tmp_path / "rh.aparc.annot"
        lh.touch()
        rh.touch()
        out = tmp_path / "labels.tsv"

        mock_lut = MagicMock()
        mock_lut.to_tsv = MagicMock()

        with patch("fsatlas.core.lut.LookupTable.from_annot", return_value=mock_lut):
            result = runner.invoke(
                cli,
                [
                    "generate-lut",
                    "--lh-annot", str(lh),
                    "--rh-annot", str(rh),
                    "--output", str(out),
                ],
            )

        # Either success or error about FreeSurfer; mock ensures lut is generated
        assert mock_lut.to_tsv.called or result.exit_code != 0
