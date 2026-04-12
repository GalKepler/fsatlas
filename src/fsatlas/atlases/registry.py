"""Atlas registry: catalog loading and path resolution.

Atlas files are resolved from a pre-populated BIDS-atlas directory rather than
downloaded at runtime.  Set ``FSATLAS_ATLAS_DIR`` to point to your atlas
directory, or run ``fsatlas populate`` to populate one.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent / "catalog.yaml"

# Package-bundled fallback atlas data (source files used by the build script).
_BUNDLED_DATA_DIR = Path(__file__).parent / "data"


def _resolve_atlas_dir() -> Path | None:
    """Locate the BIDS-atlas directory.

    Resolution order:
    1. ``FSATLAS_ATLAS_DIR`` environment variable (if set and is a directory).
    2. ``/opt/fsatlas/atlases/`` — container default (Docker / Apptainer).
    3. Package data fallback: ``src/fsatlas/atlases/bids_atlases/``.
    """
    env_dir = os.environ.get("FSATLAS_ATLAS_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
        logger.warning(
            f"FSATLAS_ATLAS_DIR='{env_dir}' is set but does not exist as a directory."
        )

    container_default = Path("/opt/fsatlas/atlases")
    if container_default.is_dir():
        return container_default

    pkg_dir = Path(__file__).parent / "bids_atlases"
    if pkg_dir.is_dir():
        return pkg_dir

    return None


def _infer_format(atlas_type: str, files: dict[str, str]) -> str:
    """Derive a format id from the legacy ``type`` field and file extensions."""
    for key in files:
        if key.endswith(".dlabel.gii") or key.endswith(".gii"):
            return "dlabel_gii"
        if key.endswith(".gca"):
            return "gca"
        if key.endswith(".annot"):
            return "annot"
        if key.endswith(".nii.gz") or key.endswith(".nii"):
            return "nifti"
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
    source_url: str = ""                 # build-time: used by populate script
    files: dict[str, str] = field(default_factory=dict)  # build-time: source filenames
    labels_tsv: str = ""                 # build-time: source labels filename
    dseg_tsv: str = ""                   # build-time: rich BIDS dseg.tsv source
    builtin: bool = False
    annot_name: str = ""                 # for FreeSurfer built-in surface atlases
    local_source_dir: str = ""           # build-time: local dir to copy from
    bids_name: str = ""                  # BIDS atlas entity value

    @property
    def structure(self) -> str:
        """BIDS structure entity: 'cortex' for surface, 'subcortex' for volumetric."""
        return "cortex" if self.type == "surface" else "subcortex"

    @property
    def bids_atlas_name(self) -> str:
        """BIDS-compatible atlas entity value. Returns bids_name if set, else sanitized name."""
        if self.bids_name:
            return self.bids_name
        return re.sub(r"[^a-zA-Z0-9]", "", self.name)

    @property
    def _safe_name(self) -> str:
        """Sanitized atlas name for use in filenames (no special chars)."""
        return re.sub(r"[^a-zA-Z0-9]", "", self.name)

    @property
    def atlas_dir(self) -> Path:
        """Path to this atlas's sub-directory within the BIDS atlas directory."""
        atlas_root = _resolve_atlas_dir()
        if atlas_root is None:
            # Return a placeholder path — callers check is_available() before using
            return Path("/opt/fsatlas/atlases") / f"atlas-{self.bids_atlas_name}"
        return atlas_root / f"atlas-{self.bids_atlas_name}"

    @property
    def labels_tsv_path(self) -> Path | None:
        """Return the LUT path in the BIDS atlas directory, or None if not present."""
        p = self.atlas_dir / f"atlas-{self._safe_name}_dseg.tsv"
        return p if p.exists() else None

    def is_available(self) -> bool:
        """Check if all atlas files (and the LUT) are present in the BIDS atlas directory."""
        if self.labels_tsv_path is None:
            return False
        if self.builtin:
            # Builtins only need the LUT (annot/nifti files come from FreeSurfer itself)
            return True
        # Verify expected data files exist
        for key in self.files:
            try:
                p = self.get_file(key)
                if not p.exists():
                    return False
            except KeyError:
                return False
        return True

    # Keep backward-compatible alias
    def is_downloaded(self) -> bool:
        return self.is_available()

    def get_file(self, key: str) -> Path:
        """Resolve a logical file key to its BIDS path in the atlas directory."""
        base = f"atlas-{self.bids_atlas_name}_space-{self.space}"

        if key == "lh.annot":
            return self.atlas_dir / f"{base}_hemi-L_dseg.annot"
        if key == "rh.annot":
            return self.atlas_dir / f"{base}_hemi-R_dseg.annot"
        if key in ("atlas.nii.gz", "atlas.nii") or (
            key.endswith(".nii.gz") or (key.endswith(".nii") and not key.endswith(".annot"))
        ):
            return self.atlas_dir / f"{base}_dseg.nii.gz"
        if key.endswith(".gca"):
            return self.atlas_dir / f"atlas-{self.bids_atlas_name}_dseg.gca"
        if key.endswith(".dlabel.gii"):
            hemi = "L" if key.startswith("lh.") else "R"
            return self.atlas_dir / f"{base}_hemi-{hemi}_dseg.dlabel.gii"

        raise KeyError(
            f"Atlas '{self.name}' has no BIDS mapping for key '{key}'. "
            f"Available keys: {list(self.files)}"
        )


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
    """Registry of available atlases, resolved from the BIDS-atlas directory."""

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

            self._atlases[key] = AtlasSpec(
                name=entry.get("name", key),
                family=entry.get("family", ""),
                description=entry.get("description", ""),
                type=atlas_type,
                format=fmt,
                space=entry.get("space", ""),
                source_url=entry.get("source_url", "") or "",
                files=files,
                labels_tsv=entry.get("labels_tsv", "") or "",
                dseg_tsv=entry.get("dseg_tsv", "") or "",
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
        space: str = "MNI152NLin2009cAsym",
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


def _add_annot_labels_to_lut(lut_path: Path, lh_annot: Path, rh_annot: Path) -> None:
    """Enrich a dseg.tsv-based LUT with an 'annot_label' column.

    Surface atlas annot files encode region names in their colour table (e.g.
    ``L_V1_ROI``).  These are the StructName values that appear in
    ``mris_anatomical_stats`` output.  But BIDS dseg.tsv files use a different
    convention (e.g. ``V1_L``).  This function reads both annot colour tables,
    builds a case-insensitive label→annot_label mapping, and writes the result
    back into the LUT TSV.
    """
    import nibabel.freesurfer as nfs
    import pandas as pd

    def _norm(label: str) -> str:
        s = label.replace("_ROI", "").replace("-ROI", "")
        parts = s.split("_", 1)
        if len(parts) == 2 and parts[0].upper() in ("L", "R"):
            hemi, name = parts
            return f"{name}_{hemi}".lower()
        return s.lower()

    annot_map: dict[str, str] = {}
    for annot_path in (lh_annot, rh_annot):
        _, _, names = nfs.read_annot(str(annot_path))
        for raw in names:
            label = raw.decode() if isinstance(raw, bytes) else raw
            if label in ("???", "", "unknown"):
                continue
            annot_map[_norm(label)] = label

    lut_df = pd.read_csv(lut_path, sep="\t")
    lut_df["annot_label"] = lut_df["label"].map(
        lambda lbl: annot_map.get(lbl.lower(), lbl)
    )
    n_matched = (lut_df["annot_label"] != lut_df["label"]).sum()
    logger.info(f"annot_label cross-reference: {n_matched}/{len(lut_df)} dseg labels matched")
    lut_df.to_csv(lut_path, sep="\t", index=False)


def _copy_file_from_source(
    local_name: str,
    remote_filename: str,
    dest: Path,
    local_source_dir: str,
    source_url: str,
) -> None:
    """Copy or download a single atlas file to *dest*.

    Used by the populate script.  Kept here so it can be imported without
    requiring the ``requests`` library at the module level.
    """
    import requests

    if local_source_dir:
        local_dir: Path | None = Path(local_source_dir)
        if not local_dir.is_absolute():
            local_dir = CATALOG_PATH.parent / local_dir
    else:
        local_dir = None

    if local_dir and (local_dir / remote_filename).exists():
        logger.info(f"Copying {local_dir / remote_filename} -> {dest}")
        shutil.copy2(local_dir / remote_filename, dest)
    elif source_url:
        url = f"{source_url}/{remote_filename}"
        logger.info(f"Downloading {url} -> {dest}")
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
    else:
        raise RuntimeError(
            f"Cannot fetch '{local_name}': no local_source_dir and no source_url."
        )
