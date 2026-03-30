"""Tests for fsatlas.core.command — run_command subprocess wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fsatlas.core.command import run_command
from fsatlas.core.environment import FreeSurferEnv


def _make_env(tmp_path: Path) -> FreeSurferEnv:
    fs_home = tmp_path / "freesurfer"
    fs_home.mkdir()
    subjects_dir = tmp_path / "subjects"
    subjects_dir.mkdir()
    return FreeSurferEnv(freesurfer_home=fs_home, subjects_dir=subjects_dir, version="8.0.0")


class TestRunCommand:
    def test_success_returns_completed_process(self, tmp_path):
        env = _make_env(tmp_path)
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = run_command(["echo", "hello"], env)
        assert result is mock_result
        mock_run.assert_called_once()

    def test_sets_freesurfer_home_in_env(self, tmp_path):
        env = _make_env(tmp_path)
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            run_command(["some_command"], env)
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["env"]["FREESURFER_HOME"] == str(env.freesurfer_home)
        assert call_kwargs["env"]["SUBJECTS_DIR"] == str(env.subjects_dir)

    def test_raises_runtime_error_on_nonzero_exit(self, tmp_path):
        env = _make_env(tmp_path)
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stderr = "some error output"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Command failed"):
                run_command(["failing_command"], env)

    def test_error_message_includes_exit_code(self, tmp_path):
        env = _make_env(tmp_path)
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 127
        mock_result.stderr = "command not found"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="127"):
                run_command(["nonexistent_binary"], env)

    def test_timeout_set_to_600(self, tmp_path):
        env = _make_env(tmp_path)
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            run_command(["cmd"], env)
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["timeout"] == 600

    def test_captures_stdout_and_stderr(self, tmp_path):
        env = _make_env(tmp_path)
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            run_command(["cmd"], env)
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True
