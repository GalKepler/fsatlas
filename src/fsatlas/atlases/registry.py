"""Atlas registry: catalog loading, downloading, and path resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import requests
import yaml
from platformdirs import user_cache_dir

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"
CACHE_DIR = Path(user_cache_dir("fsatlas")) / "atlases"


@dataclass
class AtlasSpec:
    """Specification for a single atlas."""

    name: str
    description: str
    type: Literal["surface", "volumetric"]
    space: str
    citation: str
    family: str = ""
    source_url: str = ""
    files: dict[str, str] = field(default_factory=dict)
    labels_tsv: str = ""
    builtin: bool = False
    annot_name: str = ""  # For FreeSurfer built-in atlases

    @property
    def cache_dir(self) -> Path:
        return CACHE_DIR / self.name

    def is_downloaded(self) -> bool:
        """Check if all atlas files are present in cache."""
        if self.builtin:
            return True
        return all((self.cache_dir / local_name).exists() for local_name in self.files)

    def get_file(self, key: str) -> Path:
        """Get the local path for a specific atlas file."""
        if key not in self.files:
            raise KeyError(f"Atlas '{self.name}' has no file '{key}'. Available: {list(self.files)}")
        return self.cache_dir / key


@dataclass
class CustomAtlasSpec:
    """Specification for a user-provided atlas file."""

    name: str
    type: Literal["surface", "volumetric"]
    paths: dict[str, Path]  # e.g., {"lh.annot": Path(...), "rh.annot": Path(...)} or {"atlas.nii.gz": Path(...)}
    labels_tsv: Path | None = None
    space: str = "fsaverage"  # assumed for surface; MNI for volumetric

    @property
    def description(self) -> str:
        return f"Custom {self.type} atlas: {self.name}"

    @property
    def citation(self) -> str:
        return "User-provided"

    @property
    def builtin(self) -> bool:
        return False

    def get_file(self, key: str) -> Path:
        if key not in self.paths:
            raise KeyError(f"Custom atlas '{self.name}' has no file '{key}'.")
        return self.paths[key]


class AtlasRegistry:
    """Registry of available atlases with download and resolution capabilities."""

    def __init__(self, catalog_path: Path | None = None) -> None:
        self._catalog_path = catalog_path or CATALOG_PATH
        self._atlases: dict[str, AtlasSpec] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        with open(self._catalog_path) as f:
            raw = yaml.safe_load(f)

        for key, entry in raw.items():
            self._atlases[key] = AtlasSpec(
                name=entry.get("name", key),
                family=entry.get("family", ""),
                description=entry.get("description", ""),
                type=entry["type"],
                space=entry.get("space", ""),
                source_url=entry.get("source_url", ""),
                files=entry.get("files", {}),
                labels_tsv=entry.get("labels_tsv", ""),
                builtin=entry.get("builtin", False),
                annot_name=entry.get("annot_name", ""),
                citation=entry.get("citation", ""),
            )

    def list_atlases(self) -> list[AtlasSpec]:
        """Return all registered atlases."""
        return list(self._atlases.values())

    def get(self, name: str) -> AtlasSpec:
        """Get an atlas by name."""
        if name not in self._atlases:
            available = ", ".join(sorted(self._atlases.keys()))
            raise KeyError(f"Atlas '{name}' not found. Available: {available}")
        return self._atlases[name]

    def download(self, name: str, force: bool = False) -> AtlasSpec:
        """Download atlas files to local cache. Returns the AtlasSpec."""
        atlas = self.get(name)
        if atlas.builtin:
            logger.info(f"Atlas '{name}' is a FreeSurfer built-in, no download needed.")
            return atlas

        if atlas.is_downloaded() and not force:
            logger.info(f"Atlas '{name}' already cached at {atlas.cache_dir}")
            return atlas

        atlas.cache_dir.mkdir(parents=True, exist_ok=True)

        for local_name, remote_filename in atlas.files.items():
            url = f"{atlas.source_url}/{remote_filename}"
            dest = atlas.cache_dir / local_name
            logger.info(f"Downloading {url} -> {dest}")
            _download_file(url, dest)

        # Download labels TSV if specified
        if atlas.labels_tsv:
            labels_url = f"{atlas.source_url}/{atlas.labels_tsv}"
            labels_dest = atlas.cache_dir / "labels.tsv"
            logger.info(f"Downloading labels {labels_url} -> {labels_dest}")
            _download_file(labels_url, labels_dest)

        logger.info(f"Atlas '{name}' downloaded to {atlas.cache_dir}")
        return atlas

    @staticmethod
    def from_custom_surface(
        lh_annot: Path,
        rh_annot: Path,
        name: str | None = None,
        space: str = "fsaverage",
    ) -> CustomAtlasSpec:
        """Create a CustomAtlasSpec from user-provided .annot files."""
        lh_annot = Path(lh_annot)
        rh_annot = Path(rh_annot)
        for p in (lh_annot, rh_annot):
            if not p.exists():
                raise FileNotFoundError(f"Annotation file not found: {p}")

        atlas_name = name or lh_annot.stem.replace("lh.", "").replace("rh.", "")
        return CustomAtlasSpec(
            name=atlas_name,
            type="surface",
            paths={"lh.annot": lh_annot, "rh.annot": rh_annot},
            space=space,
        )

    @staticmethod
    def from_custom_volumetric(
        nifti_path: Path,
        name: str | None = None,
        labels_tsv: Path | None = None,
        space: str = "MNI152NLin6Asym",
    ) -> CustomAtlasSpec:
        """Create a CustomAtlasSpec from a user-provided NIfTI atlas."""
        nifti_path = Path(nifti_path)
        if not nifti_path.exists():
            raise FileNotFoundError(f"NIfTI atlas not found: {nifti_path}")

        atlas_name = name or nifti_path.stem.replace(".nii", "")
        return CustomAtlasSpec(
            name=atlas_name,
            type="volumetric",
            paths={"atlas.nii.gz": nifti_path},
            labels_tsv=Path(labels_tsv) if labels_tsv else None,
            space=space,
        )


def _download_file(url: str, dest: Path) -> None:
    """Download a file with progress logging, respecting Content-Encoding decompression."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
