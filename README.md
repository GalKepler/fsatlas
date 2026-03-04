# fsatlas

Extract morphometric measures from FreeSurfer-processed subjects using arbitrary atlases.

## The Problem

FreeSurfer's `recon-all` produces cortical stats for its built-in atlases (Desikan-Killiany, Destrieux, DKT), but if you want to use other atlases — Schaefer 2018, HCP-MMP1, Tian 2020 subcortical atlas, or your own custom parcellation — you need to manually chain together `mri_surf2surf`, `mris_anatomical_stats`, `mri_vol2vol`, `mri_segstats`, and parse the outputs yourself.

**fsatlas** automates this entire workflow into a single command.

## Features

- **Built-in atlas catalog**: Ships with Schaefer 2018 (100–400 parcels × 7/17 networks), Tian 2020 subcortical (Scales I–IV), HCP-MMP1, and all FreeSurfer built-ins. Auto-downloads on first use.
- **Custom atlas support**: Point at any `.annot` (surface) or `.nii.gz` (volumetric) file.
- **Surface atlases**: Transfers `.annot` from `fsaverage` → subject via `mri_surf2surf`, then extracts thickness, area, volume, curvature via `mris_anatomical_stats`.
- **Volumetric atlases**: Registers MNI-space NIfTI → subject native via `mri_vol2vol` + `talairach.xfm`, then extracts volume and intensity stats via `mri_segstats`.
- **Long-format TSV output**: Tidy output with columns `subject_id | atlas | hemisphere | region | measure | value`.
- **Batch processing**: Process all subjects in `$SUBJECTS_DIR` or pass a specific list.
- **Docker image**: Run without installing FreeSurfer locally.

## Requirements

- **FreeSurfer 8.x** (with `FREESURFER_HOME` and `SUBJECTS_DIR` set)
- **Python ≥ 3.10**
- Subjects must have completed `recon-all`

## Installation

```bash
pip install fsatlas
```

Or from source:

```bash
git clone https://github.com/SNBB/fsatlas.git
cd fsatlas
pip install -e ".[dev]"
```

## Quick Start

### List available atlases

```bash
fsatlas list-atlases
```

### Extract Schaefer 100-parcel stats for all subjects

```bash
fsatlas extract --atlas schaefer100-7 --output-dir ./results
```

### Extract for specific subjects

```bash
fsatlas extract --atlas schaefer100-7 -s sub-01 -s sub-02 -o ./results
```

### Extract subcortical stats with Tian atlas

```bash
fsatlas extract --atlas tian-s2 -o ./results
```

### Use subjects from a text file

```bash
fsatlas extract --atlas schaefer400-17 --subjects-file subjects.txt -o ./results
```

### Use a custom atlas

```bash
# Surface atlas (.annot) — provide one hemisphere, the other is auto-detected
fsatlas extract --atlas /path/to/lh.myatlas.annot -o ./results

# Volumetric atlas (NIfTI in MNI space)
fsatlas extract --atlas /path/to/subcortical_atlas.nii.gz -o ./results
```

### Pre-download an atlas

```bash
fsatlas download schaefer400-7
```

## Output Format

The tool produces separate TSV files for cortical and subcortical results:

**Cortical** (`{atlas}_cortical.tsv`):

| subject_id | atlas | hemisphere | region | measure | value |
|---|---|---|---|---|---|
| sub-01 | schaefer100-7 | lh | 7Networks_LH_Vis_1 | thickness_mean_mm | 2.341 |
| sub-01 | schaefer100-7 | lh | 7Networks_LH_Vis_1 | surface_area_mm2 | 843.0 |
| sub-01 | schaefer100-7 | lh | 7Networks_LH_Vis_1 | gray_matter_volume_mm3 | 2110.0 |

**Subcortical** (`{atlas}_subcortical.tsv`):

| subject_id | atlas | hemisphere | region | measure | value |
|---|---|---|---|---|---|
| sub-01 | tian-s2 | lh | CAU-lh | volume_mm3 | 1248.0 |
| sub-01 | tian-s2 | lh | CAU-lh | intensity_mean | 72.34 |

## Docker

```bash
docker build -t fsatlas -f docker/Dockerfile .

docker run --rm \
    -v /path/to/SUBJECTS_DIR:/subjects \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    -e SUBJECTS_DIR=/subjects \
    fsatlas extract --atlas schaefer100-7 -o /subjects/fsatlas_output
```

## Architecture

```
fsatlas/
├── src/fsatlas/
│   ├── atlases/
│   │   ├── catalog.yaml      # Built-in atlas definitions
│   │   └── registry.py       # Atlas loading, downloading, custom atlas support
│   ├── cli/
│   │   └── main.py           # Click-based CLI
│   ├── core/
│   │   ├── environment.py    # FreeSurfer detection, subject discovery
│   │   ├── extract.py        # mris_anatomical_stats / mri_segstats + parsing
│   │   ├── pipeline.py       # Orchestrator: transfer → extract → aggregate
│   │   └── transfer.py       # mri_surf2surf / mri_vol2vol wrappers
│   └── io/                   # (future: BIDS integration, parquet export)
├── tests/
├── docker/
│   └── Dockerfile
└── pyproject.toml
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/
```

## Citation

If you use fsatlas in your research, please cite the original atlas papers (shown via `fsatlas list-atlases`) and:

> fsatlas: Automated atlas-based morphometry extraction for FreeSurfer. https://github.com/SNBB/fsatlas

## License

MIT
