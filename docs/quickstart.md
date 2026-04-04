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

## 13. BIDS Output Layout

By default, fsatlas writes a single `{atlas}.tsv` file (flat layout). To write per-subject files in a BIDS derivative structure:

```bash
fsatlas extract --atlas schaefer400-17 --output-layout bids -o ./derivatives/fsatlas
```

Output structure:

```
derivatives/fsatlas/
└── sub-01/
    └── anat/
        └── atlas-Schaefer2018N400n7/
            ├── sub-01_atlas-Schaefer2018N400n7_structure-cortex.csv
            └── sub-01_atlas-Schaefer2018N400n7_structure-cortex.json
└── sub-02/
    └── anat/
        └── atlas-Schaefer2018N400n7/
            ├── sub-02_atlas-Schaefer2018N400n7_structure-cortex.csv
            └── sub-02_atlas-Schaefer2018N400n7_structure-cortex.json
```

Sessions are automatically detected if your subject IDs follow BIDS format (`sub-{label}_ses-{label}`).

---

## 14. Aggregate BIDS Outputs

After extracting with BIDS layout, use `fsatlas aggregate` to combine all per-subject CSVs into a single wide-format table:

```bash
# List atlases available in the output directory
fsatlas aggregate --bids-dir ./derivatives/fsatlas

# Combine all subjects and structures for one atlas
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas Brainnetome246Ext

# Cortex only, specific subjects
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas Brainnetome246Ext \
    --structure cortex -s sub-01 -s sub-02 -o bn246_cortex.csv
```

The output is a single CSV with one row per subject × region. Cortical and subcortical rows are stacked:

```
subject_id,session,atlas,structure,index,label,hemisphere,...,volume_mm3,...,tiv_mm3
sub-01,,Brainnetome246Ext,cortex,1,A8dl_L,lh,...,3247.0,...,1458203.0
sub-01,,Brainnetome246Ext,subcortex,211,mAmyg_L,L,...,1411.0,...,1458203.0
sub-02,,Brainnetome246Ext,cortex,1,A8dl_L,lh,...,3109.0,...,1501044.0
```

---

## 15. Running with Apptainer

On HPC clusters, use the Apptainer image instead of a local installation:

```bash
# Pull the image
apptainer pull fsatlas.sif docker://galkepler/fsatlas:latest

# List atlases
apptainer run \
    --bind /path/to/license.txt:/license.txt:ro \
    fsatlas.sif \
    --freesurfer-license-file /license.txt \
    list-atlases

# Extract
apptainer run \
    --bind /data/subjects:/subjects \
    --bind /path/to/license.txt:/license.txt:ro \
    --env SUBJECTS_DIR=/subjects \
    fsatlas.sif \
    --freesurfer-license-file /license.txt \
    extract --atlas schaefer100-7 -o /subjects/results
```

See the [Containers guide](../docker.md) for SLURM examples and advanced usage.

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
