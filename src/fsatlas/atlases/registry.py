"""Atlas registry: catalog loading, downloading, and path resolution."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import requests
import yaml
from platformdirs import user_cache_dir

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"
CACHE_DIR = Path(user_cache_dir("fsatlas")) / "atlases"


def _infer_format(atlas_type: str, files: dict[str, str]) -> str:
    """Derive a format id from the legacy ``type`` field and file extensions."""
    # Scan files for unambiguous extensions
    for key in files:
        if key.endswith(".dlabel.gii") or key.endswith(".gii"):
            return "dlabel_gii"
        if key.endswith(".gca"):
            return "gca"
        if key.endswith(".annot"):
            return "annot"
        if key.endswith(".nii.gz") or key.endswith(".nii"):
            return "nifti"
    # Fall back to type field
    return "annot" if atlas_type == "surface" else "nifti"


@dataclass
class AtlasSpec:
    """Specification for a single atlas from the built-in catalog."""

    name: str
    description: str
    type: Literal["surface", "volumetric"]
    format: str                          # "annot", "nifti", "dlabel_gii", "gca"
    space: str
    citation: str
    family: str = ""
    source_url: str = ""
    files: dict[str, str] = field(default_factory=dict)
    labels_tsv: str = ""                 # source filename; cached as labels.tsv
    builtin: bool = False
    annot_name: str = ""                 # For FreeSurfer built-in surface atlases
    local_source_dir: str = ""           # Local dir to copy from (priority over URL)
    bids_name: str = ""                  # BIDS atlas entity value (e.g. "Glasser2016")

    @property
    def structure(self) -> str:
        """BIDS structure entity: 'cortex' for surface atlases, 'subcortex' for volumetric."""
        return "cortex" if self.type == "surface" else "subcortex"

    @property
    def bids_atlas_name(self) -> str:
        """BIDS-compatible atlas entity value. Returns bids_name if set, else sanitized name."""
        if self.bids_name:
            return self.bids_name
        return re.sub(r"[^a-zA-Z0-9]", "", self.name)

    @property
    def cache_dir(self) -> Path:
        return CACHE_DIR / self.name

    @property
    def labels_tsv_path(self) -> Path | None:
        """Return the cached LUT path, or None if not yet generated/downloaded."""
        p = self.cache_dir / "labels.tsv"
        return p if p.exists() else None

    def is_downloaded(self) -> bool:
        """Check if all atlas files (and the LUT) are present in cache."""
        if self.builtin:
            # Builtins only need the LUT in cache (annot files come from FS itself)
            return self.labels_tsv_path is not None
        has_files = all((self.cache_dir / local_name).exists() for local_name in self.files)
        has_lut = self.labels_tsv_path is not None
        return has_files and has_lut

    def get_file(self, key: str) -> Path:
        """Get the local path for a specific atlas file."""
        if key not in self.files:
            raise KeyError(
                f"Atlas '{self.name}' has no file '{key}'. Available: {list(self.files)}"
            )
        return self.cache_dir / key


@dataclass
class CustomAtlasSpec:
    """Specification for a user-provided atlas file."""

    name: str
    type: Literal["surface", "volumetric"]
    format: str                          # "annot", "nifti", "dlabel_gii", "gca"
    paths: dict[str, Path]
    labels_tsv: Path | None = None
    space: str = "fsaverage"

    @property
    def description(self) -> str:
        return f"Custom {self.format} atlas: {self.name}"

    @property
    def citation(self) -> str:
        return "User-provided"

    @property
    def builtin(self) -> bool:
        return False

    @property
    def annot_name(self) -> str:
        return self.name

    @property
    def structure(self) -> str:
        """BIDS structure entity: 'cortex' for surface atlases, 'subcortex' for volumetric."""
        return "cortex" if self.type == "surface" else "subcortex"

    @property
    def bids_atlas_name(self) -> str:
        """BIDS-compatible atlas entity value (sanitized name)."""
        return re.sub(r"[^a-zA-Z0-9]", "", self.name)

    @property
    def labels_tsv_path(self) -> Path | None:
        return self.labels_tsv

    def get_file(self, key: str) -> Path:
        if key not in self.paths:
            raise KeyError(f"Custom atlas '{self.name}' has no file '{key}'.")
        return self.paths[key]


AnyAtlasSpec = AtlasSpec | CustomAtlasSpec


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
            atlas_type: Literal["surface", "volumetric"] = entry["type"]
            files: dict[str, str] = entry.get("files", {})
            fmt: str = entry.get("format", "") or _infer_format(atlas_type, files)

            labels_tsv = entry.get("labels_tsv", "")
            if not labels_tsv:
                logger.warning(
                    f"Catalog atlas '{key}' has no labels_tsv defined. "
                    "A LUT is required for extraction."
                )

            self._atlases[key] = AtlasSpec(
                name=entry.get("name", key),
                family=entry.get("family", ""),
                description=entry.get("description", ""),
                type=atlas_type,
                format=fmt,
                space=entry.get("space", ""),
                source_url=entry.get("source_url", "") or "",
                files=files,
                labels_tsv=labels_tsv,
                builtin=entry.get("builtin", False),
                annot_name=entry.get("annot_name", ""),
                citation=entry.get("citation", ""),
                local_source_dir=entry.get("local_source_dir", "") or "",
                bids_name=entry.get("bids_name", "") or "",
            )

    def list_atlases(self) -> list[AtlasSpec]:
        return list(self._atlases.values())

    def get(self, name: str) -> AtlasSpec:
        if name not in self._atlases:
            available = ", ".join(sorted(self._atlases.keys()))
            raise KeyError(f"Atlas '{name}' not found. Available: {available}")
        return self._atlases[name]

    def download(self, name: str, force: bool = False, env=None) -> AtlasSpec:
        """Download (or copy) atlas files to local cache and generate the LUT.

        For surface atlases the LUT is auto-generated from the .annot colour
        table using ``LookupTable.from_annot`` after the annot files are
        fetched.  For volumetric atlases the labels file is copied/downloaded
        as before.

        Parameters
        ----------
        env:
            Optional ``FreeSurferEnv`` instance.  Required for FreeSurfer
            built-in atlases so that fsaverage annot files can be located.
        """
        from ..core.lut import LookupTable

        atlas = self.get(name)

        if atlas.builtin:
            return self._download_builtin(atlas, env, force)

        if atlas.is_downloaded() and not force:
            logger.info(f"Atlas '{name}' already cached at {atlas.cache_dir}")
            return atlas

        atlas.cache_dir.mkdir(parents=True, exist_ok=True)

        # Download/copy atlas files
        for local_name, remote_filename in atlas.files.items():
            dest = atlas.cache_dir / local_name
            if atlas.local_source_dir:
                local_dir: Path | None = Path(atlas.local_source_dir)
                if not local_dir.is_absolute():
                    local_dir = CATALOG_PATH.parent / local_dir
            else:
                local_dir = None
            if local_dir and (local_dir / remote_filename).exists():
                logger.info(f"Copying {local_dir / remote_filename} -> {dest}")
                shutil.copy2(local_dir / remote_filename, dest)
            else:
                url = f"{atlas.source_url}/{remote_filename}"
                logger.info(f"Downloading {url} -> {dest}")
                _download_file(url, dest)

        # Generate / download the LUT
        lut_dest = atlas.cache_dir / "labels.tsv"
        if not lut_dest.exists() or force:
            if atlas.format == "annot":
                # Auto-generate from the .annot colour table
                lh_annot = atlas.cache_dir / "lh.annot"
                rh_annot = atlas.cache_dir / "rh.annot"
                if lh_annot.exists() and rh_annot.exists():
                    logger.info(f"Generating LUT from .annot files for '{name}'")
                    lut = LookupTable.from_annot(lh_annot, rh_annot)
                    lut.to_tsv(lut_dest)
                else:
                    logger.warning(
                        f"Cannot generate LUT for '{name}': annot files not found in cache."
                    )
            else:
                # Volumetric: download or copy the labels file
                self._fetch_labels_tsv(atlas, lut_dest)

        logger.info(f"Atlas '{name}' ready at {atlas.cache_dir}")
        return atlas

    def _download_builtin(
        self, atlas: AtlasSpec, env, force: bool
    ) -> AtlasSpec:
        """Ensure a built-in atlas has its LUT cached."""
        from ..core.lut import LookupTable

        lut_dest = atlas.cache_dir / "labels.tsv"
        if lut_dest.exists() and not force:
            return atlas

        atlas.cache_dir.mkdir(parents=True, exist_ok=True)

        if atlas.format == "annot":
            # Try bundled package file first (e.g. aseg_labels.tsv)
            bundled = CATALOG_PATH.parent / atlas.labels_tsv
            if bundled.exists() and bundled != lut_dest:
                shutil.copy2(bundled, lut_dest)
                return atlas

            # Generate from fsaverage annot files
            if env is None:
                logger.warning(
                    f"Cannot generate LUT for built-in '{atlas.name}' without FreeSurferEnv."
                )
                return atlas
            fsavg_label = env.freesurfer_home / "subjects" / "fsaverage" / "label"
            lh = fsavg_label / f"lh.{atlas.annot_name}.annot"
            rh = fsavg_label / f"rh.{atlas.annot_name}.annot"
            if lh.exists() and rh.exists():
                logger.info(f"Generating LUT for built-in '{atlas.name}' from fsaverage")
                lut = LookupTable.from_annot(lh, rh)
                lut.to_tsv(lut_dest)
            else:
                logger.warning(
                    f"fsaverage annot files not found for '{atlas.name}' at {fsavg_label}."
                )
        elif atlas.format == "nifti":
            # For aseg: copy the bundled labels TSV
            bundled = CATALOG_PATH.parent / atlas.labels_tsv
            if bundled.exists():
                shutil.copy2(bundled, lut_dest)
            else:
                logger.warning(f"Bundled labels file not found for '{atlas.name}': {bundled}")

        return atlas

    def _fetch_labels_tsv(self, atlas: AtlasSpec, dest: Path) -> None:
        """Download or copy the raw labels file and normalise it as labels.tsv."""
        if not atlas.labels_tsv:
            return
        catalog_labels = CATALOG_PATH.parent / atlas.labels_tsv
        if catalog_labels.exists():
            logger.info(f"Copying catalog labels {catalog_labels} -> {dest}")
            shutil.copy2(catalog_labels, dest)
        elif atlas.source_url:
            url = f"{atlas.source_url}/{atlas.labels_tsv}"
            logger.info(f"Downloading labels {url} -> {dest}")
            _download_file(url, dest)
        else:
            logger.warning(f"No labels_tsv source for '{atlas.name}'.")

    # ------------------------------------------------------------------
    # Custom atlas factories
    # ------------------------------------------------------------------

    @staticmethod
    def from_custom_surface(
        lh_annot: Path,
        rh_annot: Path,
        name: str | None = None,
        space: str = "fsaverage",
        labels_tsv: Path | None = None,
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
            format="annot",
            paths={"lh.annot": lh_annot, "rh.annot": rh_annot},
            labels_tsv=Path(labels_tsv) if labels_tsv else None,
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
            format="nifti",
            paths={"atlas.nii.gz": nifti_path},
            labels_tsv=Path(labels_tsv) if labels_tsv else None,
            space=space,
        )

    @staticmethod
    def from_custom_dlabel_gii(
        lh_dlabel: Path,
        rh_dlabel: Path,
        name: str | None = None,
        labels_tsv: Path | None = None,
        space: str = "fsaverage",
    ) -> CustomAtlasSpec:
        """Create a CustomAtlasSpec from user-provided .dlabel.gii files."""
        lh_dlabel = Path(lh_dlabel)
        rh_dlabel = Path(rh_dlabel)
        for p in (lh_dlabel, rh_dlabel):
            if not p.exists():
                raise FileNotFoundError(f"dlabel.gii file not found: {p}")
        atlas_name = name or lh_dlabel.stem.split(".")[0]
        return CustomAtlasSpec(
            name=atlas_name,
            type="surface",
            format="dlabel_gii",
            paths={"lh.dlabel.gii": lh_dlabel, "rh.dlabel.gii": rh_dlabel},
            labels_tsv=Path(labels_tsv) if labels_tsv else None,
            space=space,
        )

    @staticmethod
    def from_custom_gca(
        gca_path: Path,
        name: str | None = None,
        labels_tsv: Path | None = None,
    ) -> CustomAtlasSpec:
        """Create a CustomAtlasSpec from a user-provided .gca atlas."""
        gca_path = Path(gca_path)
        if not gca_path.exists():
            raise FileNotFoundError(f"GCA atlas not found: {gca_path}")
        atlas_name = name or gca_path.stem
        return CustomAtlasSpec(
            name=atlas_name,
            type="volumetric",
            format="gca",
            paths={f"{atlas_name}.gca": gca_path},
            labels_tsv=Path(labels_tsv) if labels_tsv else None,
            space="subject",
        )


def _download_file(url: str, dest: Path) -> None:
    """Download a file with progress logging, respecting Content-Encoding decompression."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
