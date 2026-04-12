"""Tests for src/fsatlas/core/easyreg_registration.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fsatlas.core.easyreg_registration import (
    EasyRegWarpPaths,
    _resolve_cache_dir,
    apply_template_to_subject,
    ensure_subject_synthseg,
    ensure_subject_to_template_warp,
    ensure_template_synthseg,
)
from fsatlas.core.environment import FreeSurferEnv, SubjectPaths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path):
    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir()
    subjects_dir = tmp_path / "subjects"
    subjects_dir.mkdir(exist_ok=True)
    return FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=subjects_dir, version="8.0.0")


@pytest.fixture()
def subject(tmp_path):
    sub_dir = tmp_path / "subjects" / "sub-001"
    mri = sub_dir / "mri"
    (mri / "transforms").mkdir(parents=True)
    # Create norm.mgz placeholder
    (mri / "norm.mgz").touch()
    return SubjectPaths(subject_id="sub-001", subject_dir=sub_dir)


# ---------------------------------------------------------------------------
# _resolve_cache_dir
# ---------------------------------------------------------------------------


def test_resolve_cache_dir_uses_fsatlas_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("FSATLAS_CACHE_DIR", str(tmp_path / "mycache"))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    result = _resolve_cache_dir()
    assert result == tmp_path / "mycache"


def test_resolve_cache_dir_falls_back_to_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("FSATLAS_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    result = _resolve_cache_dir()
    assert result == tmp_path / "xdg" / "fsatlas"


def test_resolve_cache_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("FSATLAS_CACHE_DIR", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    result = _resolve_cache_dir()
    assert result == Path.home() / ".cache" / "fsatlas"


# ---------------------------------------------------------------------------
# ensure_template_synthseg
# ---------------------------------------------------------------------------


def test_ensure_template_synthseg_runs_once(tmp_path, env, monkeypatch):
    """mri_synthseg is called only the first time; second call hits the cache."""
    monkeypatch.setenv("FSATLAS_CACHE_DIR", str(tmp_path / "cache"))

    fake_t1w = tmp_path / "tpl_T1w.nii.gz"
    fake_t1w.touch()

    with patch(
        "fsatlas.core.easyreg_registration._get_template_t1w", return_value=fake_t1w
    ):
        with patch("fsatlas.core.easyreg_registration.run_command") as mock_run:
            # Simulate mri_synthseg writing the .tmp output
            def _fake_synthseg(cmd, *args, **kwargs):
                # The command writes to the --o argument with a .tmp suffix
                o_idx = cmd.index("--o") + 1
                Path(cmd[o_idx]).touch()

            mock_run.side_effect = _fake_synthseg

            out1 = ensure_template_synthseg("MNI152NLin2009cAsym", env)
            out2 = ensure_template_synthseg("MNI152NLin2009cAsym", env)

    assert out1 == out2
    assert out1.exists()
    assert mock_run.call_count == 1  # only called once


def test_ensure_template_synthseg_rejects_unsupported_space(env):
    with pytest.raises(ValueError, match="unsupported space"):
        ensure_template_synthseg("fsaverage", env)


# ---------------------------------------------------------------------------
# ensure_subject_synthseg
# ---------------------------------------------------------------------------


def test_ensure_subject_synthseg_reuses_reconall_output(subject, env):
    """When recon-all already wrote subject_synthseg.nii.gz, mri_synthseg is not called."""
    # Simulate recon-all having produced the file
    subject.subject_synthseg.touch()

    with patch("fsatlas.core.easyreg_registration.run_command") as mock_run:
        out = ensure_subject_synthseg(subject, env)

    assert out == subject.subject_synthseg
    mock_run.assert_not_called()


def test_ensure_subject_synthseg_fallback_runs_mri_synthseg(subject, env):
    """When synthseg.rca.mgz is absent, mri_synthseg --parc is invoked."""
    assert not subject.subject_synthseg.exists()

    with patch("fsatlas.core.easyreg_registration.run_command") as mock_run:
        def _fake_synthseg(cmd, *args, **kwargs):
            o_idx = cmd.index("--o") + 1
            Path(cmd[o_idx]).touch()

        mock_run.side_effect = _fake_synthseg
        out = ensure_subject_synthseg(subject, env)

    assert out == subject.subject_synthseg
    assert out.exists()
    called_cmd = mock_run.call_args[0][0]
    assert "mri_synthseg" in called_cmd[0]
    assert "--parc" in called_cmd


# ---------------------------------------------------------------------------
# ensure_subject_to_template_warp
# ---------------------------------------------------------------------------


def test_ensure_subject_to_template_warp_reuses_cache(subject, env, tmp_path):
    """When both warp fields already exist, mri_easyreg is not called."""
    tpl_dir = subject.easyreg_dir / "tpl-MNI152NLin2009cAsym"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "native_to_mni.nii.gz").touch()
    (tpl_dir / "mni_to_native.nii.gz").touch()

    with patch("fsatlas.core.easyreg_registration.run_command") as mock_run:
        warp = ensure_subject_to_template_warp(subject, "MNI152NLin2009cAsym", env)

    mock_run.assert_not_called()
    assert warp.fwd_field.exists()
    assert warp.bak_field.exists()


def test_ensure_subject_to_template_warp_runs_easyreg(subject, env, tmp_path, monkeypatch):
    """mri_easyreg is called when no cache exists; output is atomically promoted."""
    monkeypatch.setenv("FSATLAS_CACHE_DIR", str(tmp_path / "cache"))

    fake_t1w = tmp_path / "tpl_T1w.nii.gz"
    fake_t1w.touch()
    fake_tpl_synthseg = tmp_path / "tpl_synthseg.nii.gz"
    fake_tpl_synthseg.touch()
    subject.subject_synthseg.touch()  # pretend recon-all wrote it

    with patch(
        "fsatlas.core.easyreg_registration._get_template_t1w", return_value=fake_t1w
    ):
        with patch(
            "fsatlas.core.easyreg_registration.ensure_template_synthseg",
            return_value=fake_tpl_synthseg,
        ):
            with patch("fsatlas.core.easyreg_registration.run_command") as mock_run:
                def _fake_easyreg(cmd, *args, **kwargs):
                    fwd_idx = cmd.index("--fwd_field") + 1
                    bak_idx = cmd.index("--bak_field") + 1
                    Path(cmd[fwd_idx]).touch()
                    Path(cmd[bak_idx]).touch()

                mock_run.side_effect = _fake_easyreg
                warp = ensure_subject_to_template_warp(subject, "MNI152NLin2009cAsym", env)

    called_cmd = mock_run.call_args[0][0]
    assert "mri_easyreg" in called_cmd[0]
    assert warp.fwd_field.exists()
    assert warp.bak_field.exists()
    # No staging dir left behind
    tmp_dir = subject.easyreg_dir / "tpl-MNI152NLin2009cAsym.tmp"
    assert not tmp_dir.exists()


def test_ensure_subject_to_template_warp_atomic_on_failure(subject, env, tmp_path, monkeypatch):
    """A failing easyreg run must not leave a partial final cache dir."""
    monkeypatch.setenv("FSATLAS_CACHE_DIR", str(tmp_path / "cache"))

    fake_t1w = tmp_path / "tpl_T1w.nii.gz"
    fake_t1w.touch()
    subject.subject_synthseg.touch()

    with patch(
        "fsatlas.core.easyreg_registration._get_template_t1w", return_value=fake_t1w
    ):
        with patch(
            "fsatlas.core.easyreg_registration.ensure_template_synthseg",
            return_value=tmp_path / "tpl_synthseg.nii.gz",
        ):
            with patch(
                "fsatlas.core.easyreg_registration.run_command",
                side_effect=RuntimeError("mri_easyreg crashed"),
            ):
                with pytest.raises(RuntimeError):
                    ensure_subject_to_template_warp(subject, "MNI152NLin2009cAsym", env)

    tpl_dir = subject.easyreg_dir / "tpl-MNI152NLin2009cAsym"
    assert not tpl_dir.exists()


def test_ensure_subject_to_template_warp_rejects_unsupported_space(subject, env):
    with pytest.raises(ValueError, match="unsupported space"):
        ensure_subject_to_template_warp(subject, "MNI305", env)


# ---------------------------------------------------------------------------
# apply_template_to_subject
# ---------------------------------------------------------------------------


def test_apply_template_to_subject_calls_easywarp(tmp_path, env):
    atlas_nii = tmp_path / "atlas.nii.gz"
    atlas_nii.touch()
    bak_field = tmp_path / "mni_to_native.nii.gz"
    bak_field.touch()
    out_path = tmp_path / "atlas_native.nii.gz"

    warp = EasyRegWarpPaths(
        fwd_field=tmp_path / "native_to_mni.nii.gz",
        bak_field=bak_field,
        reference=tmp_path / "norm.mgz",
    )

    with patch("fsatlas.core.easyreg_registration.run_command") as mock_run:
        cmd = apply_template_to_subject(atlas_nii, warp, out_path, env=env)

    mock_run.assert_called_once()
    assert "mri_easywarp" in cmd[0]
    assert "--nearest" in cmd
    assert str(bak_field) in cmd
    assert str(out_path) in cmd
