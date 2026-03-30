"""Tests for fsatlas.core.environment — FreeSurferEnv and SubjectPaths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fsatlas.core.environment import FreeSurferEnv, SubjectPaths, _detect_version


# ---------------------------------------------------------------------------
# Helpers: create fake FS home and subjects dir
# ---------------------------------------------------------------------------

def _make_fs_home(tmp_path: Path) -> Path:
    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir()
    return fs_home


def _make_subjects_dir(tmp_path: Path) -> Path:
    sd = tmp_path / "subjects"
    sd.mkdir()
    return sd


def _make_valid_subject(subjects_dir: Path, name: str = "sub-01") -> Path:
    """Create a minimal valid FreeSurfer subject directory."""
    subj = subjects_dir / name
    (subj / "surf").mkdir(parents=True)
    (subj / "label").mkdir(parents=True)
    (subj / "mri" / "transforms").mkdir(parents=True)
    (subj / "stats").mkdir(parents=True)
    # Minimum for list_subjects
    (subj / "surf" / "lh.white").touch()
    (subj / "mri" / "aseg.mgz").touch()
    # Full validate() set
    for f in ["rh.white", "lh.pial", "rh.pial", "lh.sphere.reg", "rh.sphere.reg"]:
        (subj / "surf" / f).touch()
    (subj / "mri" / "norm.mgz").touch()
    return subj


# ---------------------------------------------------------------------------
# FreeSurferEnv.detect
# ---------------------------------------------------------------------------

class TestFreeSurferEnvDetect:
    def test_raises_if_freesurfer_home_not_set(self, tmp_path):
        sd = _make_subjects_dir(tmp_path)
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(OSError, match="FREESURFER_HOME"):
                FreeSurferEnv.detect(subjects_dir=sd)

    def test_raises_if_freesurfer_home_nonexistent(self, tmp_path):
        sd = _make_subjects_dir(tmp_path)
        env = {"FREESURFER_HOME": str(tmp_path / "nonexistent")}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(OSError, match="non-existent"):
                FreeSurferEnv.detect(subjects_dir=sd)

    def test_raises_if_no_subjects_dir_and_env_not_set(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        with patch.dict("os.environ", {"FREESURFER_HOME": str(fs_home)}, clear=True):
            with pytest.raises(OSError, match="SUBJECTS_DIR"):
                FreeSurferEnv.detect(subjects_dir=None)

    def test_raises_if_subjects_dir_nonexistent(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        env = {"FREESURFER_HOME": str(fs_home)}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(OSError, match="does not exist"):
                FreeSurferEnv.detect(subjects_dir=tmp_path / "nonexistent")

    def test_detects_from_explicit_subjects_dir(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        with patch.dict("os.environ", {"FREESURFER_HOME": str(fs_home)}, clear=True):
            env = FreeSurferEnv.detect(subjects_dir=sd)
        assert env.freesurfer_home == fs_home
        assert env.subjects_dir == sd

    def test_detects_from_subjects_dir_env_var(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        env_vars = {"FREESURFER_HOME": str(fs_home), "SUBJECTS_DIR": str(sd)}
        with patch.dict("os.environ", env_vars, clear=True):
            env = FreeSurferEnv.detect()
        assert env.subjects_dir == sd

    def test_version_detected(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        stamp = fs_home / "build-stamp.txt"
        stamp.write_text("freesurfer-linux-centos7_x86_64-8.0.0-20230908")
        with patch.dict("os.environ", {"FREESURFER_HOME": str(fs_home)}, clear=True):
            env = FreeSurferEnv.detect(subjects_dir=sd)
        assert env.version == "8.0.0"


# ---------------------------------------------------------------------------
# FreeSurferEnv.fsaverage_dir
# ---------------------------------------------------------------------------

class TestFsaverageDir:
    def test_prefers_subjects_dir_fsaverage(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        fsa = sd / "fsaverage"
        fsa.mkdir()
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        assert env.fsaverage_dir == fsa

    def test_falls_back_to_freesurfer_home(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        # no fsaverage in subjects_dir
        fsa_home = fs_home / "subjects" / "fsaverage"
        fsa_home.mkdir(parents=True)
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        assert env.fsaverage_dir == fsa_home


# ---------------------------------------------------------------------------
# FreeSurferEnv.find_subject / list_subjects
# ---------------------------------------------------------------------------

class TestFindAndListSubjects:
    def test_find_subject_success(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        _make_valid_subject(sd, "sub-01")
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        sp = env.find_subject("sub-01")
        assert sp.subject_id == "sub-01"

    def test_find_subject_not_found(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        with pytest.raises(FileNotFoundError):
            env.find_subject("nonexistent")

    def test_list_subjects_finds_valid(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        _make_valid_subject(sd, "sub-01")
        _make_valid_subject(sd, "sub-02")
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        subjects = env.list_subjects()
        assert "sub-01" in subjects
        assert "sub-02" in subjects

    def test_list_subjects_skips_invalid(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        # partial subject (missing aseg.mgz)
        partial = sd / "sub-bad"
        (partial / "surf").mkdir(parents=True)
        (partial / "surf" / "lh.white").touch()
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        subjects = env.list_subjects()
        assert "sub-bad" not in subjects

    def test_list_subjects_skips_fsaverage(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        _make_valid_subject(sd, "fsaverage")
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        subjects = env.list_subjects()
        assert "fsaverage" not in subjects

    def test_list_subjects_skips_dotfiles(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        _make_valid_subject(sd, ".hidden_subject")
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        subjects = env.list_subjects()
        assert ".hidden_subject" not in subjects

    def test_list_subjects_sorted(self, tmp_path):
        fs_home = _make_fs_home(tmp_path)
        sd = _make_subjects_dir(tmp_path)
        _make_valid_subject(sd, "sub-03")
        _make_valid_subject(sd, "sub-01")
        _make_valid_subject(sd, "sub-02")
        env = FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=sd, version="8.0.0")
        subjects = env.list_subjects()
        assert subjects == sorted(subjects)


# ---------------------------------------------------------------------------
# SubjectPaths
# ---------------------------------------------------------------------------

class TestSubjectPaths:
    def _make(self, tmp_path: Path, name: str = "sub-01") -> SubjectPaths:
        subj = _make_valid_subject(tmp_path, name)
        return SubjectPaths(subject_id=name, subject_dir=subj)

    def test_directory_properties(self, tmp_path):
        sp = self._make(tmp_path)
        assert sp.surf_dir == sp.subject_dir / "surf"
        assert sp.label_dir == sp.subject_dir / "label"
        assert sp.mri_dir == sp.subject_dir / "mri"
        assert sp.stats_dir == sp.subject_dir / "stats"

    def test_file_properties(self, tmp_path):
        sp = self._make(tmp_path)
        assert sp.orig_mgz == sp.mri_dir / "orig.mgz"
        assert sp.aseg_mgz == sp.mri_dir / "aseg.mgz"
        assert sp.norm_mgz == sp.mri_dir / "norm.mgz"
        assert sp.talairach_xfm == sp.mri_dir / "transforms" / "talairach.xfm"
        assert sp.talairach_m3z == sp.mri_dir / "transforms" / "talairach.m3z"

    def test_sphere_reg(self, tmp_path):
        sp = self._make(tmp_path)
        assert sp.sphere_reg["lh"] == sp.surf_dir / "lh.sphere.reg"
        assert sp.sphere_reg["rh"] == sp.surf_dir / "rh.sphere.reg"

    def test_annot_path(self, tmp_path):
        sp = self._make(tmp_path)
        p = sp.annot_path("lh", "aparc")
        assert p == sp.label_dir / "lh.aparc.annot"

    def test_has_annot_true(self, tmp_path):
        sp = self._make(tmp_path)
        (sp.label_dir / "lh.aparc.annot").touch()
        (sp.label_dir / "rh.aparc.annot").touch()
        assert sp.has_annot("aparc") is True

    def test_has_annot_false_missing_rh(self, tmp_path):
        sp = self._make(tmp_path)
        (sp.label_dir / "lh.aparc.annot").touch()
        assert sp.has_annot("aparc") is False

    def test_validate_no_missing(self, tmp_path):
        sp = self._make(tmp_path)
        missing = sp.validate()
        assert missing == []

    def test_validate_detects_missing_files(self, tmp_path):
        sp = self._make(tmp_path)
        # Remove one required file
        (sp.surf_dir / "lh.white").unlink()
        missing = sp.validate()
        assert any("lh.white" in m for m in missing)

    def test_validate_returns_all_missing(self, tmp_path):
        subj = tmp_path / "sub-empty"
        (subj / "surf").mkdir(parents=True)
        (subj / "mri").mkdir(parents=True)
        sp = SubjectPaths(subject_id="sub-empty", subject_dir=subj)
        missing = sp.validate()
        assert len(missing) == 8  # all 8 essential files missing


# ---------------------------------------------------------------------------
# _detect_version
# ---------------------------------------------------------------------------

class TestDetectVersion:
    def test_reads_build_stamp(self, tmp_path):
        fs_home = tmp_path / "fs"
        fs_home.mkdir()
        (fs_home / "build-stamp.txt").write_text("freesurfer-centos7-v8.0.0-20230101")
        assert _detect_version(fs_home) == "8.0.0"

    def test_returns_raw_stamp_if_no_semver(self, tmp_path):
        fs_home = tmp_path / "fs"
        fs_home.mkdir()
        (fs_home / "build-stamp.txt").write_text("custom-build-nightly")
        assert _detect_version(fs_home) == "custom-build-nightly"

    def test_falls_back_to_unknown_without_binary(self, tmp_path):
        fs_home = tmp_path / "fs"
        fs_home.mkdir()
        # no build-stamp.txt; binary also unavailable
        with patch("subprocess.run", side_effect=FileNotFoundError):
            version = _detect_version(fs_home)
        assert version == "unknown"
