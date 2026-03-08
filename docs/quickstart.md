# Quick Start

This guide walks through the most common fsatlas workflows.

## Assumptions

- FreeSurfer 8.x is installed and `FREESURFER_HOME` / `SUBJECTS_DIR` are set.
- `recon-all` has completed for your subjects.
- fsatlas is installed (`pip install fsatlas`).

---

## 1. Explore Available Atlases

```bash
fsatlas list-atlases
```

This prints a table of all built-in atlases with their IDs, type (surface/volumetric), parcel counts, and citations. Use the **ID** column as the `--atlas` argument in subsequent commands.

---

## 2. Extract Cortical Morphometry (All Subjects)

Run on all subjects discovered in `$SUBJECTS_DIR`:

```bash
fsatlas extract --atlas schaefer100-7 --output-dir ./results
```

On first run, fsatlas downloads the Schaefer 100-parcel atlas to `~/.cache/fsatlas/atlases/`. Subsequent runs use the cached copy.

**Output files:**

```
results/
├── schaefer100-7_cortical.tsv
└── schaefer100-7_failures.tsv
```

---

## 3. Target Specific Subjects

Pass subject IDs with `-s` (repeatable):

```bash
fsatlas extract --atlas schaefer100-7 \
    -s sub-01 -s sub-02 -s sub-03 \
    -o ./results
```

Or load a list from a text file (one subject ID per line):

```bash
# subjects.txt
sub-01
sub-02
sub-03

fsatlas extract --atlas schaefer100-7 \
    --subjects-file subjects.txt \
    -o ./results
```

---

## 4. Extract Subcortical Morphometry

The Tian 2020 atlas provides multi-scale subcortical parcellations:

```bash
# Scale 2 — 32 bilateral subcortical regions
fsatlas extract --atlas tian-s2 -o ./results
```

Output:

```
results/
├── tian-s2_subcortical.tsv
└── tian-s2_failures.tsv
```

---

## 5. Higher-Resolution Cortical Atlas

```bash
# Schaefer 400-parcel with 17-network assignment
fsatlas extract --atlas schaefer400-17 -o ./results

# HCP-MMP1 — 360 cortical areas (Glasser et al. 2016)
fsatlas extract --atlas hcp-mmp -o ./results
```

---

## 6. Pre-Download Before a Batch Job

To avoid download latency during a long batch run, pre-download atlases:

```bash
fsatlas download schaefer400-7
fsatlas download tian-s2
```

---

## 7. Force Re-Processing

By default, fsatlas skips subjects where transferred atlas files and stats already exist. To force re-processing:

```bash
fsatlas extract --atlas schaefer100-7 --force -o ./results
```

---

## 8. Custom Surface Atlas

Supply a FreeSurfer annotation file (`.annot`) in `fsaverage` space. Provide either hemisphere; fsatlas auto-detects the other:

```bash
# Using lh annotation
fsatlas extract \
    --atlas /path/to/lh.myatlas.annot \
    -o ./results
```

The file naming convention must follow `{hemi}.{atlas_name}.annot`. fsatlas will look for `rh.myatlas.annot` in the same directory.

---

## 9. Custom Volumetric Atlas

Supply a NIfTI file (`.nii` or `.nii.gz`) in MNI152 space:

```bash
fsatlas extract \
    --atlas /path/to/my_subcortical_atlas.nii.gz \
    -o ./results
```

fsatlas registers this to each subject's native space via `mri_vol2vol` and the subject's `talairach.xfm`.

---

## 10. Reading the Output

The TSV output is in long (tidy) format — one row per measure per region per subject:

=== "Python / pandas"

    ```python
    import pandas as pd

    df = pd.read_csv("results/schaefer100-7_cortical.tsv", sep="\t")

    # Filter to thickness only
    thickness = df[df["measure"] == "thickness_mean_mm"]

    # Pivot to wide format (regions as columns)
    wide = thickness.pivot_table(
        index="subject_id",
        columns="region",
        values="value"
    )
    ```

=== "R / tidyverse"

    ```r
    library(tidyverse)

    df <- read_tsv("results/schaefer100-7_cortical.tsv")

    # Filter to left hemisphere thickness
    thickness_lh <- df |>
      filter(measure == "thickness_mean_mm", hemisphere == "lh")

    # Wide format
    wide <- thickness_lh |>
      pivot_wider(
        id_cols = subject_id,
        names_from = region,
        values_from = value
      )
    ```

---

## Failure Handling

If a subject fails (missing files, FreeSurfer error), fsatlas logs the error and moves to the next subject. Review failures in:

```
results/{atlas}_failures.tsv
```

| subject_id | atlas | stage | error |
|---|---|---|---|
| sub-99 | schaefer100-7 | transfer | Missing transform: talairach.xfm |
