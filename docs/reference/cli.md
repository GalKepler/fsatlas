# CLI Reference

fsatlas is invoked as `fsatlas <command> [OPTIONS]`.

```
fsatlas --help
```

---

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show fsatlas version and exit |
| `--help` | Show help message and exit |

---

## `fsatlas extract`

The main command. Extracts morphometric measures from FreeSurfer subjects using the specified atlas.

```bash
fsatlas extract [OPTIONS]
```

### Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `--atlas`, `-a` | TEXT | **Yes** | Atlas ID (from catalog) or path to a `.annot` or `.nii.gz` file |
| `--output-dir`, `-o` | PATH | **Yes** | Directory where TSV results are written |
| `--subject`, `-s` | TEXT | No | Subject ID to process (repeatable; default: all subjects in `$SUBJECTS_DIR`) |
| `--subjects-file` | PATH | No | Text file with one subject ID per line |
| `--force`, `-f` | flag | No | Recalculate and overwrite existing transferred atlases and stats |
| `--subjects-dir` | PATH | No | Override `$SUBJECTS_DIR` for this run |
| `--verbose`, `-v` | flag | No | Increase logging verbosity |

### Examples

```bash
# All subjects, catalog atlas
fsatlas extract --atlas schaefer100-7 -o ./results

# Specific subjects
fsatlas extract --atlas schaefer100-7 -s sub-01 -s sub-02 -o ./results

# From subjects file
fsatlas extract --atlas tian-s2 --subjects-file cohort.txt -o ./results

# Custom surface atlas
fsatlas extract --atlas /data/atlases/lh.myatlas.annot -o ./results

# Custom volumetric atlas
fsatlas extract --atlas /data/atlases/my_atlas.nii.gz -o ./results

# Override SUBJECTS_DIR
fsatlas extract --atlas desikan --subjects-dir /data/fs_subjects -o ./results

# Force re-processing
fsatlas extract --atlas schaefer100-7 --force -o ./results
```

### Output

Written to `--output-dir`:

| File | Description |
|------|-------------|
| `{atlas}_cortical.tsv` | Long-format cortical morphometry (surface atlases) |
| `{atlas}_subcortical.tsv` | Long-format subcortical morphometry (volumetric atlases) |
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
| ID | Atlas identifier for use with `--atlas` |
| Family | Atlas family / publication |
| Type | `surface` or `volumetric` |
| Parcels | Number of regions |
| Space | Reference space |
| Downloaded | Whether the atlas is already in the local cache |
| Citation | Short citation key |

### Example output

```
┌─────────────────┬──────────────┬─────────────┬─────────┬────────────┬────────────┐
│ ID              │ Family       │ Type        │ Parcels │ Downloaded │ Space      │
├─────────────────┼──────────────┼─────────────┼─────────┼────────────┼────────────┤
│ schaefer100-7   │ Schaefer2018 │ surface     │ 100     │ ✓          │ fsaverage  │
│ schaefer200-7   │ Schaefer2018 │ surface     │ 200     │            │ fsaverage  │
│ tian-s1         │ Tian2020     │ volumetric  │ 16      │            │ MNI152     │
│ desikan         │ FreeSurfer   │ surface     │ 68      │ built-in   │ fsaverage  │
└─────────────────┴──────────────┴─────────────┴─────────┴────────────┴────────────┘
```

---

## `fsatlas download`

Pre-downloads one or more atlases to the local cache.

```bash
fsatlas download [OPTIONS] ATLAS_ID [ATLAS_ID ...]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `ATLAS_ID` | One or more atlas IDs to download (from the catalog) |

### Options

| Option | Description |
|--------|-------------|
| `--force` | Re-download even if already cached |

### Examples

```bash
# Download a single atlas
fsatlas download schaefer400-7

# Download multiple atlases
fsatlas download schaefer100-7 schaefer400-17 tian-s2 hcp-mmp

# Force re-download
fsatlas download --force schaefer100-7
```

### Cache location

```
~/.cache/fsatlas/atlases/{atlas_id}/
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `FREESURFER_HOME` | **Yes** | Path to FreeSurfer installation |
| `SUBJECTS_DIR` | **Yes** | Path to FreeSurfer subjects directory |

These are typically set by FreeSurfer's `SetUpFreeSurfer.sh` script. They can be overridden per-run with `--subjects-dir`.
