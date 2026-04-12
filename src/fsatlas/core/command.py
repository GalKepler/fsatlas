"""Shared utility for running FreeSurfer (and related) commands as subprocesses."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path  # noqa: F401  (re-exported for convenience)

from .environment import FreeSurferEnv

logger = logging.getLogger(__name__)


def run_command(
    cmd: list[str], env: FreeSurferEnv, timeout: int = 600
) -> subprocess.CompletedProcess:
    """Run a FreeSurfer command with the proper environment variables set.

    Sets FREESURFER_HOME and SUBJECTS_DIR, captures stdout/stderr, and raises
    RuntimeError on non-zero exit.
    """
    import os

    fs_env = {
        **dict(os.environ),
        "FREESURFER_HOME": str(env.freesurfer_home),
        "SUBJECTS_DIR": str(env.subjects_dir),
    }

    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=fs_env,
        timeout=timeout,
    )

    if result.returncode != 0:
        logger.error(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")
        logger.error(f"stderr: {result.stderr}")
        raise RuntimeError(
            f"Command failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr: {result.stderr[:500]}"
        )

    return result
