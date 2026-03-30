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
| `--atlas` | `-a` | TEXT | **Yes** | Atlas ID from catalog, or path to an atlas file |
| `--output-dir` | `-o` | PATH | No | Output directory (default: `fsatlas_output`) |
| `--format` | `-F` | CHOICE | No | Atlas file format: `annot`, `nifti`, `dlabel_gii`, `gca`, `auto` (default: `auto`) |
| `--lut` | `-l` | PATH | No | Path to a custom LUT TSV (`index`, `label`, `hemisphere`). Required for custom atlases without embedded labels. |
| `--subjects` | `-s` | TEXT | No | Subject IDs to process (repeatable; default: all in `$SUBJECTS_DIR`) |
| `--subjects-file` | | PATH | No | Text file with one subject ID per line |
| `--output-layout` | | CHOICE | No | Output directory layout: `flat` (default) or `bids` |
| `--force` | `-f` | flag | No | Recompute even if cached outputs exist |
| `--subjects-dir` | `-d` | PATH | No | Override `$SUBJECTS_DIR` for this run |
| `--verbose` | `-v` | flag | No | Increase logging verbosity |

`--atlas-type` is accepted for backward compatibility but is deprecated — use `--format` instead.

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
| Cached | Whether the atlas is already in the local cache (✓ or —) |

### Example output

```
┌─────────────────┬────────┬──────────────┬───────────────────────────┬────────┐
│ Name            │ Format │ Family       │ Description               │ Cached │
├─────────────────┼────────┼──────────────┼───────────────────────────┼────────┤
│ schaefer100-7   │ annot  │ schaefer2018 │ Schaefer 2018, 100 parcels│   ✓    │
│ schaefer200-7   │ annot  │ schaefer2018 │ Schaefer 2018, 200 parcels│   —    │
│ tian-s1         │ nifti  │ tian2020     │ Tian 2020 Scale I (16 reg)│   —    │
│ desikan         │ annot  │ freesurfer.. │ Desikan-Killiany (builtin)│   —    │
└─────────────────┴────────┴──────────────┴───────────────────────────┴────────┘
```

---

## `fsatlas download`

Pre-downloads an atlas to the local cache and generates its LUT.

```bash
fsatlas download [OPTIONS] ATLAS_NAME
```

### Arguments

| Argument | Description |
|----------|-------------|
| `ATLAS_NAME` | Atlas ID to download (from the catalog) |

### Options

| Option | Description |
|--------|-------------|
| `--force` | Re-download even if already cached |
| `--subjects-dir`, `-d` | FreeSurfer SUBJECTS_DIR (needed to generate LUTs for built-in surface atlases) |

### Examples

```bash
# Download and cache atlas + LUT
fsatlas download schaefer400-7

# Built-in atlas LUT generation (requires FREESURFER_HOME)
fsatlas download desikan

# Force re-download
fsatlas download --force schaefer100-7
```

### Cache location

```
~/.cache/fsatlas/atlases/{atlas_name}/
    lh.annot          # surface atlases
    rh.annot
    labels.tsv        # LUT (auto-generated or downloaded)
    atlas.nii.gz      # volumetric atlases
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

# From a downloaded catalog atlas
fsatlas download schaefer100-7
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

These are typically set by FreeSurfer's `SetUpFreeSurfer.sh` script. `SUBJECTS_DIR` can be overridden per-run with `--subjects-dir`.
