# CLI Reference

fsatlas is invoked as `fsatlas <command> [OPTIONS]`.

```
fsatlas --help
```

---

## Global Options

| Option | Description |
|--------|-------------|
| `--freesurfer-license-file` | Path to FreeSurfer `license.txt`. Overrides the `FS_LICENSE` environment variable. |
| `--atlas-dir` | Path to the BIDS atlas directory. Overrides the `FSATLAS_ATLAS_DIR` environment variable. |
| `--version` | Show fsatlas version and exit |
| `--help` | Show help message and exit |

---

## `fsatlas extract`

The main command. Extracts morphometric measures from FreeSurfer subjects using the specified atlas.

```bash
fsatlas extract [OPTIONS]
```

### Options

| Option | Short | Type | Required | Description |
|--------|-------|------|----------|-------------|
| `--atlas` | `-a` | TEXT | **Yes** | Atlas ID from catalog, or path to an atlas file. **Repeatable** — pass multiple times to process several atlases in one run. |
| `--output-dir` | `-o` | PATH | No | Output directory (default: `fsatlas_output`) |
| `--format` | `-F` | CHOICE | No | Atlas file format: `annot`, `nifti`, `dlabel_gii`, `gca`, `auto` (default: `auto`) |
| `--lut` | `-l` | PATH | No | Path to a custom LUT TSV (`index`, `label`, `hemisphere`). Required for custom atlases without embedded labels. |
| `--subjects` | `-s` | TEXT | No | Subject IDs to process (repeatable; default: all in `$SUBJECTS_DIR`) |
| `--subjects-file` | | PATH | No | Text file with one subject ID per line |
| `--output-layout` | | CHOICE | No | Output directory layout: `flat` (default) or `bids` |
| `--jobs` | `-j` | INT | No | Number of parallel worker threads for subject processing (default: `1`) |
| `--registration` | `-R` | CHOICE | No | Nonlinear registration backend for MNI152-space volumetric atlases: `easyreg` (default) or `ants`. Ignored for surface and MNI305 atlases. |
| `--force` | `-f` | flag | No | Recompute even if cached outputs exist |
| `--subjects-dir` | `-d` | PATH | No | Override `$SUBJECTS_DIR` for this run |
| `--verbose` | `-v` | flag | No | Increase logging verbosity |

`--atlas-type` is accepted for backward compatibility but is deprecated — use `--format` instead.

#### `--jobs` details

`--jobs` / `-j` controls the number of parallel worker threads used to process subjects. The default is `1` (serial). Set it to the number of available CPU cores to speed up large cohorts:

```bash
fsatlas extract --atlas schaefer400-17 --jobs 8 -o ./results
```

Each thread runs an independent FreeSurfer subprocess, so memory usage scales with `--jobs`. On a cluster node with 16 cores and 64 GB RAM, `--jobs 8` is a reasonable starting point.

#### `--registration` details

`--registration` / `-R` selects the nonlinear registration backend used to warp MNI152-space volumetric atlases (`.nii`/`.nii.gz`) into each subject's native space. It has no effect on surface (`.annot`, `.dlabel.gii`) or MNI305 (`.gca`) atlases.

| Value | Backend | Speed | Dependencies |
|-------|---------|-------|--------------|
| `easyreg` (default) | FreeSurfer `mri_easyreg` | Fast | None (bundled with FreeSurfer 8) |
| `ants` | ANTs `antsRegistration` SyN via nipype | Slower, higher accuracy | ANTs + nipype must be installed |

Use `--registration ants` when you need higher registration accuracy for fine-grained subcortical atlases at the cost of longer runtimes and the ANTs dependency.

#### `--output-layout` details

| Layout | Output structure |
|--------|-----------------|
| `flat` (default) | `{output-dir}/{atlas}.tsv` — one file per atlas, all subjects |
| `bids` | `{output-dir}/sub-{id}/[ses-{ses}/]anat/atlas-{name}/sub-{id}_atlas-{name}_structure-{structure}.csv` |

BIDS layout is useful when integrating fsatlas output into an existing BIDS derivative dataset.

### Examples

```bash
# All subjects, catalog atlas
fsatlas extract --atlas schaefer100-7 -o ./results

# Multiple atlases in a single run
fsatlas extract --atlas schaefer100-7 --atlas tian-s2 -o ./results

# Parallel processing (8 threads)
fsatlas extract --atlas schaefer400-17 --jobs 8 -o ./results

# Specific subjects
fsatlas extract --atlas schaefer100-7 -s sub-01 -s sub-02 -o ./results

# From subjects file
fsatlas extract --atlas tian-s2 --subjects-file cohort.txt -o ./results

# Custom surface atlas with LUT
fsatlas extract \
    --atlas /data/atlases/lh.myatlas.annot \
    --lut /data/atlases/myatlas_lut.tsv \
    -o ./results

# Custom volumetric atlas with LUT
fsatlas extract \
    --atlas /data/atlases/my_atlas.nii.gz \
    --lut /data/atlases/my_atlas_lut.tsv \
    -o ./results

# Use ANTs registration for higher-accuracy subcortical alignment
fsatlas extract --atlas tian-s4 --registration ants -o ./results

# CIFTI atlas
fsatlas extract \
    --atlas /data/atlases/lh.myatlas.dlabel.gii \
    --format dlabel_gii \
    --lut /data/atlases/lut.tsv \
    -o ./results

# Override SUBJECTS_DIR
fsatlas extract --atlas desikan --subjects-dir /data/fs_subjects -o ./results

# Force re-processing
fsatlas extract --atlas schaefer100-7 --force -o ./results
```

### Output

Written to `--output-dir`:

| File | Description |
|------|-------------|
| `{atlas}.tsv` | Wide-format morphometry (one row per region per subject) |
| `{atlas}_failures.tsv` | Per-subject error log |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (even if some subjects failed — check failures TSV) |
| `1` | Fatal error (environment misconfiguration, atlas not found, etc.) |

---

## `fsatlas aggregate`

Scans a BIDS-layout output directory and combines per-subject CSVs into a single wide-format table for a given atlas.

```bash
fsatlas aggregate [OPTIONS]
```

No FreeSurfer installation required — works entirely from previously extracted CSV files.

### Options

| Option | Short | Type | Required | Description |
|--------|-------|------|----------|-------------|
| `--bids-dir` | `-d` | PATH | **Yes** | BIDS output directory from `fsatlas extract --output-layout bids` |
| `--atlas` | `-a` | TEXT | No | Atlas name to aggregate (e.g. `Brainnetome246Ext`). If omitted, lists available atlases and exits. |
| `--structure` | | CHOICE | No | Structures to include: `cortex`, `subcortex`, or `both` (default: `both`) |
| `--subjects` | `-s` | TEXT | No | Subject labels to include, without `sub-` prefix (repeatable; default: all) |
| `--subjects-file` | | PATH | No | Text file with one subject label per line |
| `--output` | `-o` | PATH | No | Output file path (default: `{bids-dir}/atlas-{name}_aggregated.csv`) |
| `--format` | `-F` | CHOICE | No | Output file format: `csv` or `tsv` (default: `csv`) |
| `--verbose` | `-v` | flag | No | Increase logging verbosity |

### Examples

```bash
# List available atlases in a BIDS output directory
fsatlas aggregate --bids-dir ./derivatives/fsatlas

# Aggregate all subjects and structures for one atlas
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas Brainnetome246Ext

# Cortex only, TSV output
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas HCPex \
    --structure cortex --format tsv -o hcpex_cortex.tsv

# Specific subjects
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas Brainnetome246Ext \
    -s S001 -s S002

# From a subjects file
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas Brainnetome246Ext \
    --subjects-file cohort.txt
```

### Output

A single wide-format file with one row per subject × region. Cortical and subcortical rows are stacked; columns not applicable to a structure type are `NaN`.

| Column | Description |
|--------|-------------|
| `subject_id` | Subject ID (e.g. `sub-S001`) |
| `session` | Session label, or empty for cross-sectional data |
| `atlas` | Atlas name |
| `structure` | `cortex` or `subcortex` |
| `index` | Integer region index from the atlas LUT |
| `label` | Region name |
| `hemisphere` | `lh`, `rh`, or `bilateral` |
| *(cortical measures)* | `num_vertices`, `surface_area_mm2`, `volume_mm3`, `thickness_mean_mm`, `thickness_std_mm`, `mean_curvature`, `gaussian_curvature`, `folding_index`, `curvature_index` |
| *(subcortical measures)* | `num_voxels`, `volume_mm3`, `intensity_mean`, `intensity_std`, `intensity_min`, `intensity_max`, `intensity_range` |
| `tiv_mm3` | Total intracranial volume |

!!! note
    The cortical `gray_matter_volume_mm3` column is renamed to `volume_mm3` in the aggregated output so that cortical and subcortical rows share the same column name for region volume.

---

## `fsatlas list-atlases`

Prints the built-in atlas catalog as a formatted table.

```bash
fsatlas list-atlases
```

### Output columns

| Column | Description |
|--------|-------------|
| Name | Atlas identifier for use with `--atlas` |
| Format | File format: `annot`, `nifti`, `dlabel_gii`, or `gca` |
| Family | Atlas family / publication |
| Description | Short description |
| Available | Whether the atlas is present in the resolved atlas directory (✓ or —) |

### Example output

```
┌─────────────────┬────────┬──────────────┬───────────────────────────┬───────────┐
│ Name            │ Format │ Family       │ Description               │ Available │
├─────────────────┼────────┼──────────────┼───────────────────────────┼───────────┤
│ schaefer100-7   │ annot  │ schaefer2018 │ Schaefer 2018, 100 parcels│     ✓     │
│ schaefer200-7   │ annot  │ schaefer2018 │ Schaefer 2018, 200 parcels│     —     │
│ tian-s1         │ nifti  │ tian2020     │ Tian 2020 Scale I (16 reg)│     —     │
│ desikan         │ annot  │ freesurfer.. │ Desikan-Killiany (builtin)│     —     │
└─────────────────┴────────┴──────────────┴───────────────────────────┴───────────┘
```

---

## `fsatlas populate`

Populate a BIDS atlas directory with atlas files and LUT TSVs. Use this when running fsatlas outside the Docker/Apptainer container.

```bash
fsatlas populate [OPTIONS] [ATLAS_NAMES]...
```

### Arguments

| Argument | Description |
|----------|-------------|
| `ATLAS_NAME` | A single atlas ID from the catalog. If omitted, all atlases are populated. Run the command once per atlas to populate multiple atlases individually. |

### Options

| Option | Description |
|--------|-------------|
| `--output-dir` | Directory to populate (default: `FSATLAS_ATLAS_DIR` or `./atlases`) |
| `--force` | Re-populate even if already present |
| `--freesurfer-home` | Path to FreeSurfer installation (needed for built-in surface atlases such as `desikan`, `dkt`, `destrieux`) |

### Examples

```bash
# Populate all atlases
fsatlas populate --output-dir /path/to/atlases

# Populate a specific atlas (one at a time)
fsatlas populate schaefer400-7 --output-dir /path/to/atlases
fsatlas populate tian-s2 --output-dir /path/to/atlases

# Force re-population
fsatlas populate schaefer100-7 --force --output-dir /path/to/atlases

# Built-in atlas (reads from fsaverage; requires FREESURFER_HOME)
fsatlas populate desikan --output-dir /path/to/atlases
```

### Output layout

```
/path/to/atlases/
  dataset_description.json
  atlas-Schaefer2018N400n7/
    atlas-Schaefer2018N400n7_space-fsaverage_hemi-L_dseg.annot
    atlas-Schaefer2018N400n7_space-fsaverage_hemi-R_dseg.annot
    atlas-schaefer400_7net_dseg.tsv
  atlas-Tian2020S2/
    atlas-Tian2020S2_space-MNI152NLin6Asym_dseg.nii.gz
    atlas-tian_s2_dseg.tsv
```

---

## `fsatlas generate-lut`

Generate a LUT TSV from a `.annot` file pair or a catalog atlas.

```bash
fsatlas generate-lut [OPTIONS]
```

### Options

| Option | Short | Type | Required | Description |
|--------|-------|------|----------|-------------|
| `--atlas` | `-a` | TEXT | * | Catalog atlas name (e.g. `desikan`) |
| `--lh-annot` | | PATH | * | Left-hemisphere `.annot` file |
| `--rh-annot` | | PATH | * | Right-hemisphere `.annot` file |
| `--output` | `-o` | PATH | **Yes** | Output TSV path |
| `--subjects-dir` | `-d` | PATH | No | FreeSurfer SUBJECTS_DIR (required for built-in atlases) |

\* Provide either `--atlas` OR both `--lh-annot` and `--rh-annot`.

### Examples

```bash
# From .annot files
fsatlas generate-lut \
    --lh-annot /data/lh.myatlas.annot \
    --rh-annot /data/rh.myatlas.annot \
    --output myatlas_lut.tsv

# From a catalog atlas (must be populated first)
fsatlas populate schaefer100-7 --output-dir /path/to/atlases
fsatlas generate-lut --atlas schaefer100-7 --output schaefer100-7_lut.tsv

# From a FreeSurfer built-in (reads from fsaverage)
fsatlas generate-lut --atlas desikan --output desikan_lut.tsv
```

### Output format

```
index   label                   hemisphere
1       7Networks_LH_Vis_1      lh
2       7Networks_LH_Vis_2      lh
...
51      7Networks_RH_Vis_1      rh
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FREESURFER_HOME` | **Yes** | Path to FreeSurfer installation |
| `SUBJECTS_DIR` | **Yes** | Path to FreeSurfer subjects directory |
| `FS_LICENSE` | No | Path to FreeSurfer `license.txt` (alternative to `--freesurfer-license-file`) |
| `FSATLAS_ATLAS_DIR` | No | Path to a BIDS atlas directory (alternative to `--atlas-dir`). Pre-set to `/opt/fsatlas/atlases/` inside the container image. |

`FREESURFER_HOME` and `SUBJECTS_DIR` are typically set by FreeSurfer's `SetUpFreeSurfer.sh` script. `SUBJECTS_DIR` can be overridden per-run with `--subjects-dir`.
