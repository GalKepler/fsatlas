"""Tests for _run_anatomical_stats and _run_segstats in fsatlas.core.extract."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fsatlas.core.environment import FreeSurferEnv, SubjectPaths
from fsatlas.core.extract import _run_anatomical_stats, _run_segstats


def _make_env(tmp_path: Path) -> FreeSurferEnv:
    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir()
    subjects_dir = tmp_path / "subjects"
    subjects_dir.mkdir()
    return FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=subjects_dir, version="8.0.0")


def _make_subject(tmp_path: Path, name: str = "sub-01") -> SubjectPaths:
    subj = tmp_path / "subjects" / name
    (subj / "stats").mkdir(parents=True)
    (subj / "mri").mkdir(parents=True)
    (subj / "mri" / "norm.mgz").touch()
    return SubjectPaths(subject_id=name, subject_dir=subj)


# ---------------------------------------------------------------------------
# _run_anatomical_stats
# ---------------------------------------------------------------------------

class TestRunAnatomicalStats:
    def test_returns_stats_path(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        annot_path = tmp_path / "lh.atlas.annot"
        annot_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            stats_path = _run_anatomical_stats(
                subject=subject,
                env=env,
                hemi="lh",
                annot_path=annot_path,
                atlas_name="myatlas",
            )

        mock_cmd.assert_called_once()
        assert stats_path.name == "lh.myatlas.stats"

    def test_skips_if_exists_and_no_force(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        annot_path = tmp_path / "lh.atlas.annot"
        annot_path.touch()

        # Pre-create the stats file
        stats_path = subject.stats_dir / "lh.myatlas.stats"
        stats_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            result = _run_anatomical_stats(
                subject=subject, env=env, hemi="lh",
                annot_path=annot_path, atlas_name="myatlas", force=False,
            )

        mock_cmd.assert_not_called()
        assert result == stats_path

    def test_runs_if_exists_and_force(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        annot_path = tmp_path / "lh.atlas.annot"
        annot_path.touch()

        # Pre-create the stats file
        (subject.stats_dir / "lh.myatlas.stats").touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_anatomical_stats(
                subject=subject, env=env, hemi="lh",
                annot_path=annot_path, atlas_name="myatlas", force=True,
            )

        mock_cmd.assert_called_once()

    def test_command_includes_expected_args(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        annot_path = tmp_path / "lh.atlas.annot"
        annot_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_anatomical_stats(
                subject=subject, env=env, hemi="lh",
                annot_path=annot_path, atlas_name="myatlas",
            )

        cmd = mock_cmd.call_args[0][0]
        assert "mris_anatomical_stats" in cmd
        assert "-a" in cmd
        assert str(annot_path) in cmd
        assert "lh" in cmd

    def test_creates_stats_dir_if_missing(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        # Remove stats dir
        subject.stats_dir.rmdir()
        annot_path = tmp_path / "lh.atlas.annot"
        annot_path.touch()

        with patch("fsatlas.core.extract.run_command"):
            _run_anatomical_stats(
                subject=subject, env=env, hemi="lh",
                annot_path=annot_path, atlas_name="myatlas",
            )

        assert subject.stats_dir.exists()


# ---------------------------------------------------------------------------
# _run_segstats
# ---------------------------------------------------------------------------

class TestRunSegstats:
    def test_returns_stats_path(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            stats_path = _run_segstats(
                subject=subject, env=env,
                seg_path=seg_path, atlas_name="myatlas",
            )

        mock_cmd.assert_called_once()
        assert "myatlas" in stats_path.name

    def test_skips_if_exists_and_no_force(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()

        # Pre-create stats file
        stats_path = subject.stats_dir / "myatlas.subcortical.stats"
        stats_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_segstats(
                subject=subject, env=env, seg_path=seg_path,
                atlas_name="myatlas", force=False,
            )

        mock_cmd.assert_not_called()

    def test_runs_if_force(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()
        (subject.stats_dir / "myatlas.subcortical.stats").touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_segstats(
                subject=subject, env=env, seg_path=seg_path,
                atlas_name="myatlas", force=True,
            )

        mock_cmd.assert_called_once()

    def test_command_includes_ctab_when_provided(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        seg_path = tmp_path / "seg.mgz"
        ctab_path = tmp_path / "labels.ctab"
        seg_path.touch()
        ctab_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_segstats(
                subject=subject, env=env, seg_path=seg_path,
                atlas_name="myatlas", ctab_path=ctab_path,
            )

        cmd = mock_cmd.call_args[0][0]
        assert "--ctab" in cmd
        assert str(ctab_path) in cmd

    def test_command_no_ctab_when_not_provided(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_segstats(
                subject=subject, env=env, seg_path=seg_path,
                atlas_name="myatlas", ctab_path=None,
            )

        cmd = mock_cmd.call_args[0][0]
        assert "--ctab" not in cmd

    def test_command_includes_etiv(self, tmp_path):
        env = _make_env(tmp_path)
        subject = _make_subject(tmp_path)
        seg_path = tmp_path / "seg.mgz"
        seg_path.touch()

        with patch("fsatlas.core.extract.run_command") as mock_cmd:
            _run_segstats(
                subject=subject, env=env, seg_path=seg_path,
                atlas_name="myatlas",
            )

        cmd = mock_cmd.call_args[0][0]
        assert "--etiv" in cmd
