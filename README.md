<div align="center">
  <img src="fsatlas.png" alt="fsatlas logo" width="200"/>
  <h1>fsatlas</h1>
  <p><strong>Automated atlas-based morphometry extraction for FreeSurfer-processed brain MRI</strong></p>

  [![PyPI version](https://img.shields.io/pypi/v/fsatlas.svg)](https://pypi.org/project/fsatlas/)
  [![Python](https://img.shields.io/pypi/pyversions/fsatlas.svg)](https://pypi.org/project/fsatlas/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![FreeSurfer](https://img.shields.io/badge/FreeSurfer-8.x-blue.svg)](https://surfer.nmr.mgh.harvard.edu/)
</div>

---

## The Problem

FreeSurfer's `recon-all` produces cortical statistics for its built-in atlases (Desikan-Killiany, Destrieux, DKT), but extracting measures with any other atlas requires manually chaining together multiple commands:

```
mri_surf2surf → mris_anatomical_stats → parse output
mri_vol2vol   → mri_segstats         → parse output
```

**fsatlas** automates this entire workflow into a single command — for any atlas, for any number of subjects.

---

## Features

- **22 built-in atlases** — Schaefer 2018 (100–1000 parcels × 7/17 networks), Tian 2020 subcortical (Scales I–IV), HCP-MMP1, DKT, Desikan, Destrieux. Auto-downloads on first use.
- **Custom atlas support** — Point at any `.annot` (surface) or `.nii.gz` (volumetric, MNI space) file.
- **Surface pipeline** — Transfers annotations from `fsaverage` → subject via `mri_surf2surf`, extracts 9 cortical measures via `mris_anatomical_stats`.
- **Volumetric pipeline** — Registers MNI-space NIfTI → native space via `mri_vol2vol` + `talairach.xfm`, extracts 7 subcortical measures via `mri_segstats`.
- **Tidy TSV output** — Long-format output: `subject_id | atlas | hemisphere | region | measure | value`.
- **Batch processing** — Process all subjects in `$SUBJECTS_DIR` or a specified list.
- **Failure resilience** — Pipeline continues on per-subject errors; all failures logged to a separate TSV.
- **Docker image** — Run without a local FreeSurfer installation.

---

## Requirements

| Requirement | Version |
|-------------|---------|
| Python | ≥ 3.10 |
| FreeSurfer | 8.x |
| `FREESURFER_HOME` | must be set |
| `SUBJECTS_DIR` | must be set |

Subjects must have completed `recon-all`.

---

## Installation

```bash
pip install fsatlas
```

**From source:**

```bash
git clone https://github.com/GalKepler/fsatlas.git
cd fsatlas
pip install -e ".[dev]"
```

---

## Quick Start

### List available atlases

```bash
fsatlas list-atlases
```

### Extract Schaefer 100-parcel cortical stats for all subjects

```bash
fsatlas extract --atlas schaefer100-7 --output-dir ./results
```

### Target specific subjects

```bash
fsatlas extract --atlas schaefer100-7 -s sub-01 -s sub-02 -o ./results
```

### Load subjects from a file

```bash
fsatlas extract --atlas schaefer400-17 --subjects-file subjects.txt -o ./results
```

### Extract subcortical stats with the Tian atlas

```bash
fsatlas extract --atlas tian-s2 -o ./results
```

### Use a custom surface atlas

```bash
# Provide one hemisphere; the other is auto-detected
fsatlas extract --atlas /path/to/lh.myatlas.annot -o ./results
```

### Use a custom volumetric atlas (MNI space)

```bash
fsatlas extract --atlas /path/to/subcortical_atlas.nii.gz -o ./results
```

### Pre-download an atlas

```bash
fsatlas download schaefer400-7
```

---

## Built-in Atlas Catalog

| ID | Family | Type | Parcels | Space |
|----|--------|------|---------|-------|
| `schaefer100-7` | Schaefer 2018 | Surface | 100 | fsaverage |
| `schaefer200-7` | Schaefer 2018 | Surface | 200 | fsaverage |
| `schaefer300-7` | Schaefer 2018 | Surface | 300 | fsaverage |
| `schaefer400-7` | Schaefer 2018 | Surface | 400 | fsaverage |
| `schaefer500-7` | Schaefer 2018 | Surface | 500 | fsaverage |
| `schaefer600-7` | Schaefer 2018 | Surface | 600 | fsaverage |
| `schaefer700-7` | Schaefer 2018 | Surface | 700 | fsaverage |
| `schaefer800-7` | Schaefer 2018 | Surface | 800 | fsaverage |
| `schaefer900-7` | Schaefer 2018 | Surface | 900 | fsaverage |
| `schaefer1000-7` | Schaefer 2018 | Surface | 1000 | fsaverage |
| `schaefer100-17` | Schaefer 2018 | Surface | 100 | fsaverage |
| `schaefer200-17` | Schaefer 2018 | Surface | 200 | fsaverage |
| `schaefer300-17` | Schaefer 2018 | Surface | 300 | fsaverage |
| `schaefer400-17` | Schaefer 2018 | Surface | 400 | fsaverage |
| `tian-s1` | Tian 2020 | Volumetric | 16 | MNI152NLin6Asym |
| `tian-s2` | Tian 2020 | Volumetric | 32 | MNI152NLin6Asym |
| `tian-s3` | Tian 2020 | Volumetric | 50 | MNI152NLin6Asym |
| `tian-s4` | Tian 2020 | Volumetric | 54 | MNI152NLin6Asym |
| `hcp-mmp` | HCP-MMP 1.0 | Surface | 360 | fsaverage |
| `desikan` | FreeSurfer | Surface | 68 | built-in |
| `destrieux` | FreeSurfer | Surface | 148 | built-in |
| `dkt` | FreeSurfer | Surface | 62 | built-in |

---

## Output Format

Results are written as long-format (tidy) TSV files to the specified output directory.

**Cortical** (`{atlas}_cortical.tsv`):

| subject_id | atlas | hemisphere | region | measure | value |
|---|---|---|---|---|---|
| sub-01 | schaefer100-7 | lh | 7Networks_LH_Vis_1 | thickness_mean_mm | 2.341 |
| sub-01 | schaefer100-7 | lh | 7Networks_LH_Vis_1 | surface_area_mm2 | 843.0 |
| sub-01 | schaefer100-7 | lh | 7Networks_LH_Vis_1 | gray_matter_volume_mm3 | 2110.0 |

**Cortical measures:** `thickness_mean_mm`, `surface_area_mm2`, `gray_matter_volume_mm3`, `mean_curvature`, `gauss_curvature`, `fold_index`, `curvature_index`, `integrated_rect_curvature`, `eTIV`

**Subcortical** (`{atlas}_subcortical.tsv`):

| subject_id | atlas | hemisphere | region | measure | value |
|---|---|---|---|---|---|
| sub-01 | tian-s2 | lh | CAU-lh | volume_mm3 | 1248.0 |
| sub-01 | tian-s2 | lh | CAU-lh | intensity_mean | 72.34 |

**Subcortical measures:** `volume_mm3`, `intensity_mean`, `intensity_std`, `intensity_min`, `intensity_max`, `intensity_range`, `voxel_count`

**Failures** (`{atlas}_failures.tsv`) — subjects that could not be processed, with error messages.

---

## Docker

```bash
docker build -t fsatlas .

docker run --rm \
    -v /path/to/SUBJECTS_DIR:/subjects \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    -e SUBJECTS_DIR=/subjects \
    fsatlas extract --atlas schaefer100-7 -o /subjects/results
```

The Docker image is based on `freesurfer/freesurfer:8.0.0` and includes a self-contained Python environment at `/opt/fsatlas-venv`.

---

## Architecture

```
src/fsatlas/
├── cli/
│   └── main.py           # Click CLI: extract, list-atlases, download
├── atlases/
│   ├── catalog.yaml      # Built-in atlas definitions (13 atlases)
│   └── registry.py       # Atlas loading, downloading, custom atlas support
└── core/
    ├── environment.py    # FreeSurfer detection, subject discovery, path resolution
    ├── pipeline.py       # Orchestrator: validate → transfer → extract → aggregate
    ├── transfer.py       # mri_surf2surf / mri_vol2vol wrappers (600s timeout)
    └── extract.py        # mris_anatomical_stats / mri_segstats + long-format parsing
```

**Data flow:**

```
CLI
 └─ resolve atlas + discover subjects
     └─ Pipeline (per subject)
         ├─ validate subject directory structure
         ├─ transfer atlas → subject space (cached)
         │   ├─ surface: mri_surf2surf (fsaverage → subject)
         │   └─ volumetric: mri_vol2vol (MNI → native via talairach.xfm)
         └─ extract stats
             ├─ cortical: mris_anatomical_stats → 9 measures (long format)
             └─ subcortical: mri_segstats → 7 measures (long format)
 └─ concatenate → {atlas}_cortical.tsv / {atlas}_subcortical.tsv
```

---

## Development

```bash
pip install -e ".[dev]"
pytest                 # run tests
ruff check src/        # lint
ruff format src/       # format
mypy                   # type check
```

---

## Citation

If you use fsatlas in your research, please cite the relevant atlas papers (shown via `fsatlas list-atlases`) and:

> fsatlas: Automated atlas-based morphometry extraction for FreeSurfer.
> https://github.com/GalKepler/fsatlas

---

## License

MIT © [Gal Kepler](https://github.com/GalKepler)
