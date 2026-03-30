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

This prints a table of all built-in atlases with their IDs, format, parcel counts, and citations. The **Name** column is the `--atlas` argument for subsequent commands.

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
├── schaefer100-7.tsv         # wide-format: one row per region per subject
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
```

```bash
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
├── tian-s2.tsv
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

## 8. Custom Surface Atlas (`.annot`)

Supply a FreeSurfer annotation file in `fsaverage` space. Provide either hemisphere; fsatlas auto-detects the other. A LUT (lookup table) is required.

```bash
# Generate a LUT from the .annot colour table
fsatlas generate-lut \
    --lh-annot /path/to/lh.myatlas.annot \
    --rh-annot /path/to/rh.myatlas.annot \
    --output myatlas_lut.tsv

# Extract
fsatlas extract \
    --atlas /path/to/lh.myatlas.annot \
    --lut myatlas_lut.tsv \
    -o ./results
```

The file naming convention must follow `{hemi}.{atlas_name}.annot`. fsatlas will look for `rh.myatlas.annot` in the same directory.

---

## 9. Custom Volumetric Atlas (`.nii.gz`)

Supply a NIfTI file in MNI152 space with a matching LUT:

```bash
fsatlas extract \
    --atlas /path/to/my_subcortical_atlas.nii.gz \
    --lut /path/to/lut.tsv \
    -o ./results
```

fsatlas registers this to each subject's native space via `mri_vol2vol` and the subject's `talairach.xfm`.

---

## 10. CIFTI Atlas (`.dlabel.gii`)

```bash
fsatlas extract \
    --atlas /path/to/lh.myatlas.dlabel.gii \
    --format dlabel_gii \
    --lut /path/to/lut.tsv \
    -o ./results
```

---

## 11. Generate a LUT for a Built-in Atlas

```bash
# Desikan atlas (FreeSurfer built-in)
fsatlas generate-lut --atlas desikan --output desikan_lut.tsv

# Schaefer 400-parcel (must be downloaded first)
fsatlas download schaefer400-7
fsatlas generate-lut --atlas schaefer400-7 --output schaefer400-7_lut.tsv
```

---

## 12. Reading the Output

The TSV output is in wide format — one row per region per subject, measures as columns:

=== "Python / pandas"

    ```python
    import pandas as pd

    df = pd.read_csv("results/schaefer100-7.tsv", sep="\t")

    # Select thickness only, left hemisphere
    lh_thickness = df[df["hemisphere"] == "lh"][
        ["subject_id", "label", "thickness_mean_mm"]
    ]

    # Subjects × regions matrix
    matrix = df.pivot_table(
        index="subject_id",
        columns="label",
        values="thickness_mean_mm",
    )

    # eTIV normalization
    df["surface_area_norm"] = df["surface_area_mm2"] / df["tiv_mm3"]
    ```

=== "R / tidyverse"

    ```r
    library(tidyverse)

    df <- read_tsv("results/schaefer100-7.tsv")

    # Filter to left hemisphere thickness
    lh_thickness <- df |>
      filter(hemisphere == "lh") |>
      select(subject_id, label, thickness_mean_mm)

    # Wide matrix (subjects × regions)
    matrix <- lh_thickness |>
      pivot_wider(names_from = label, values_from = thickness_mean_mm)

    # eTIV normalization
    df <- df |> mutate(surface_area_norm = surface_area_mm2 / tiv_mm3)
    ```

---

## Failure Handling

If a subject fails (missing files, FreeSurfer error), fsatlas logs the error and moves to the next subject. Review failures in:

```
results/{atlas}_failures.tsv
```

| subject_id | reason |
|---|---|
| sub-99 | Missing: ['.../mri/norm.mgz'] |
| sub-55 | Command failed (exit 1): mri_surf2surf ... |
