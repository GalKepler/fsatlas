"""FreeSurfer environment detection and subject discovery."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FreeSurferEnv:
    """Represents a validated FreeSurfer environment."""

    freesurfer_home: Path
    subjects_dir: Path
    version: str

    @classmethod
    def detect(cls, subjects_dir: Path | str | None = None) -> FreeSurferEnv:
        """Detect FreeSurfer installation and subjects directory.

        Args:
            subjects_dir: Explicit subjects directory. Falls back to $SUBJECTS_DIR.

        Raises:
            EnvironmentError: If FreeSurfer is not found or version is unsupported.
        """
        fs_home = os.environ.get("FREESURFER_HOME")
        if not fs_home:
            raise EnvironmentError(
                "FREESURFER_HOME is not set. Source FreeSurfer's setup script first."
            )
        fs_home_path = Path(fs_home)
        if not fs_home_path.is_dir():
            raise EnvironmentError(f"FREESURFER_HOME points to non-existent directory: {fs_home}")

        # Resolve subjects_dir
        if subjects_dir:
            sd = Path(subjects_dir)
        else:
            sd_env = os.environ.get("SUBJECTS_DIR")
            if not sd_env:
                raise EnvironmentError(
                    "No --subjects-dir provided and $SUBJECTS_DIR is not set."
                )
            sd = Path(sd_env)

        if not sd.is_dir():
            raise EnvironmentError(f"Subjects directory does not exist: {sd}")

        # Detect version
        version = _detect_version(fs_home_path)
        logger.info(f"FreeSurfer {version} at {fs_home_path}, subjects_dir={sd}")

        return cls(freesurfer_home=fs_home_path, subjects_dir=sd, version=version)

    @property
    def fsaverage_dir(self) -> Path:
        """Path to the fsaverage subject."""
        p = self.subjects_dir / "fsaverage"
        if not p.is_dir():
            # Fall back to FREESURFER_HOME/subjects/fsaverage
            p = self.freesurfer_home / "subjects" / "fsaverage"
        return p

    def find_subject(self, subject_id: str) -> SubjectPaths:
        """Locate a FreeSurfer subject and validate required files exist."""
        subj_dir = self.subjects_dir / subject_id
        if not subj_dir.is_dir():
            raise FileNotFoundError(f"Subject directory not found: {subj_dir}")
        return SubjectPaths(subject_id=subject_id, subject_dir=subj_dir)

    def list_subjects(self) -> list[str]:
        """List all valid FreeSurfer subjects in subjects_dir.

        A valid subject has at minimum: surf/lh.white, mri/aseg.mgz
        """
        subjects = []
        for d in sorted(self.subjects_dir.iterdir()):
            if not d.is_dir():
                continue
            if d.name.startswith(("fsaverage", ".")):
                continue
            if (d / "surf" / "lh.white").exists() and (d / "mri" / "aseg.mgz").exists():
                subjects.append(d.name)
        return subjects


@dataclass
class SubjectPaths:
    """Convenient access to a FreeSurfer subject's key files."""

    subject_id: str
    subject_dir: Path

    @property
    def surf_dir(self) -> Path:
        return self.subject_dir / "surf"

    @property
    def label_dir(self) -> Path:
        return self.subject_dir / "label"

    @property
    def mri_dir(self) -> Path:
        return self.subject_dir / "mri"

    @property
    def stats_dir(self) -> Path:
        return self.subject_dir / "stats"

    def annot_path(self, hemi: str, annot_name: str) -> Path:
        """Path to an annotation file, e.g. lh.aparc.annot"""
        return self.label_dir / f"{hemi}.{annot_name}.annot"

    def has_annot(self, annot_name: str) -> bool:
        """Check if both hemisphere annot files exist for this atlas."""
        return (
            self.annot_path("lh", annot_name).exists()
            and self.annot_path("rh", annot_name).exists()
        )

    @property
    def orig_mgz(self) -> Path:
        return self.mri_dir / "orig.mgz"

    @property
    def aseg_mgz(self) -> Path:
        return self.mri_dir / "aseg.mgz"

    @property
    def norm_mgz(self) -> Path:
        return self.mri_dir / "norm.mgz"

    @property
    def talairach_xfm(self) -> Path:
        """Path to talairach.xfm (MNI registration)."""
        return self.mri_dir / "transforms" / "talairach.xfm"

    @property
    def sphere_reg(self) -> dict[str, Path]:
        """Sphere registration files per hemisphere."""
        return {
            "lh": self.surf_dir / "lh.sphere.reg",
            "rh": self.surf_dir / "rh.sphere.reg",
        }

    def validate(self) -> list[str]:
        """Validate that essential files exist. Returns list of missing files."""
        essential = [
            self.surf_dir / "lh.white",
            self.surf_dir / "rh.white",
            self.surf_dir / "lh.pial",
            self.surf_dir / "rh.pial",
            self.surf_dir / "lh.sphere.reg",
            self.surf_dir / "rh.sphere.reg",
            self.mri_dir / "aseg.mgz",
            self.mri_dir / "norm.mgz",
        ]
        return [str(p) for p in essential if not p.exists()]


def _detect_version(fs_home: Path) -> str:
    """Detect FreeSurfer version from build-stamp or binary."""
    # Try build-stamp.txt first (FS 7+)
    stamp = fs_home / "build-stamp.txt"
    if stamp.exists():
        text = stamp.read_text().strip()
        match = re.search(r"v?(\d+\.\d+\.\d+)", text)
        if match:
            return match.group(1)
        return text

    # Fallback: run freesurfer binary
    try:
        result = subprocess.run(
            ["recon-all", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown"
