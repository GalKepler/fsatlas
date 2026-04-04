# Output Format

fsatlas produces a single **wide-format** TSV file per extraction run — one row per region per subject, with every measure as a separate column. The schema is driven by the atlas's lookup table (LUT), so every region defined in the LUT appears as a row, even if the FreeSurfer stats command produced no data for it (the measure columns will be `NaN`).

---

## Files Written

For each extraction run, fsatlas writes up to two files to `--output-dir`:

| File | Contents | When written |
|------|----------|--------------|
| `{atlas}.tsv` | Wide-format morphometry | Always (if any subject succeeded) |
| `{atlas}_failures.tsv` | Per-subject errors | When any subject failed |

---

## Output Schema

**File:** `{atlas}.tsv`

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | string | Subject directory name (from `$SUBJECTS_DIR`) |
| `index` | int | Integer label index from the atlas LUT |
| `label` | string | Region name from the atlas LUT |
| `hemisphere` | string | `lh`, `rh`, or `bilateral` |
| *(extra LUT columns)* | varies | Any additional columns present in the LUT TSV (e.g. `network`, `color_r`) |
| *(measure columns)* | float | One column per morphometric measure (see below) |
| `tiv_mm3` | float | Estimated total intracranial volume in mm³ |

The exact measure columns depend on the atlas format:

### Cortical measures (`.annot`, `.dlabel.gii` atlases)

| Column | Unit | Description |
|--------|------|-------------|
| `num_vertices` | vertices | Number of surface vertices in the parcel |
| `surface_area_mm2` | mm² | Total pial surface area |
| `gray_matter_volume_mm3` | mm³ | Gray matter volume (thickness × area) |
| `thickness_mean_mm` | mm | Mean cortical thickness |
| `thickness_std_mm` | mm | Standard deviation of cortical thickness |
| `mean_curvature` | 1/mm | Mean curvature |
| `gaussian_curvature` | 1/mm² | Gaussian curvature |
| `folding_index` | — | Folding index |
| `curvature_index` | — | Intrinsic curvature index |

### Volumetric measures (`.nii`, `.gca` atlases)

| Column | Unit | Description |
|--------|------|-------------|
| `num_voxels` | voxels | Number of voxels in the region |
| `volume_mm3` | mm³ | Region volume |
| `intensity_mean` | — | Mean MRI intensity within the region |
| `intensity_std` | — | Standard deviation of MRI intensity |
| `intensity_min` | — | Minimum MRI intensity |
| `intensity_max` | — | Maximum MRI intensity |
| `intensity_range` | — | `intensity_max − intensity_min` |

---

## Example Output

### Cortical (Schaefer 100-parcel)

```
subject_id  index  label                  hemisphere  num_vertices  surface_area_mm2  thickness_mean_mm  ...  tiv_mm3
sub-01      1      7Networks_LH_Vis_1     lh          843           843.0             2.341              ...  1458203.0
sub-01      2      7Networks_LH_Vis_2     lh          701           700.5             2.289              ...  1458203.0
sub-01      3      7Networks_LH_Vis_3     lh          NaN           NaN               NaN                ...  1458203.0
sub-02      1      7Networks_LH_Vis_1     lh          857           857.2             2.311              ...  1501044.0
```

Regions present in the LUT but absent from the stats file (e.g. parcels with zero vertices for a subject) appear as `NaN` rows — so every subject has the same number of rows.

### Volumetric (Tian S2)

```
subject_id  index  label   hemisphere  num_voxels  volume_mm3  intensity_mean  ...  tiv_mm3
sub-01      1      HIP-lh  lh          1574        1573.6      74.12           ...  1458203.0
sub-01      2      HIP-rh  rh          1622        1621.7      73.98           ...  1458203.0
sub-02      1      HIP-lh  lh          1487        1487.1      75.33           ...  1501044.0
```

---

## Failures Output Schema

**File:** `{atlas}_failures.tsv`

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | string | Subject that failed |
| `reason` | string | Error message |

### Example

```
subject_id  reason
sub-99      Missing: ['.../surf/lh.white', '.../mri/norm.mgz']
sub-55      Command failed (exit 1): mri_surf2surf ...
```

---

## Aggregated Output (BIDS layout)

When using `--output-layout bids`, per-subject CSVs are written to a BIDS directory tree. The `fsatlas aggregate` command combines these into a single file.

```bash
fsatlas aggregate --bids-dir ./derivatives/fsatlas --atlas HCPex
```

**File:** `{bids-dir}/atlas-{name}_aggregated.csv` (default)

Cortical and subcortical rows are stacked. Columns not applicable to a structure type are `NaN`.

| Column | Description |
|--------|-------------|
| `subject_id` | Subject ID (e.g. `sub-01`) |
| `session` | Session label, or empty for cross-sectional data |
| `atlas` | Atlas name |
| `structure` | `cortex` or `subcortex` |
| `index` | Integer region index |
| `label` | Region name |
| `hemisphere` | `lh`, `rh`, or `bilateral` |
| *(cortical measures)* | `num_vertices`, `surface_area_mm2`, `volume_mm3`, `thickness_mean_mm`, `thickness_std_mm`, `mean_curvature`, `gaussian_curvature`, `folding_index`, `curvature_index` |
| *(subcortical measures)* | `num_voxels`, `volume_mm3`, `intensity_mean`, `intensity_std`, `intensity_min`, `intensity_max`, `intensity_range` |
| `tiv_mm3` | Total intracranial volume |

!!! note
    `gray_matter_volume_mm3` (cortical) is renamed to `volume_mm3` in the aggregated output so both structure types share the same column name for region volume.

### Example

```
subject_id,session,atlas,structure,index,label,hemisphere,num_vertices,...,volume_mm3,...,tiv_mm3
sub-01,,HCPex,cortex,1,V1_ROI_L,lh,843,...,2341.0,...,1458203.0
sub-01,,HCPex,cortex,2,V1_ROI_R,rh,901,...,2487.0,...,1458203.0
sub-01,,HCPex,subcortex,361,Thal_L,lh,,,,...,463.0,...,1458203.0
sub-02,,HCPex,cortex,1,V1_ROI_L,lh,857,...,2301.0,...,1501044.0
```

---

## Working with the Output

=== "Python / pandas"

    ```python
    import pandas as pd

    # Load output
    df = pd.read_csv("results/schaefer100-7.tsv", sep="\t")

    # All rows are already wide — just select the columns you need
    thickness = df[["subject_id", "label", "hemisphere", "thickness_mean_mm"]]

    # Filter to left hemisphere
    lh = df[df["hemisphere"] == "lh"]

    # Pivot to subjects × regions matrix
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

    # Subjects × regions matrix (already wide, just reshape if needed)
    matrix <- lh_thickness |>
      pivot_wider(names_from = label, values_from = thickness_mean_mm)

    # eTIV normalization
    df <- df |> mutate(surface_area_norm = surface_area_mm2 / tiv_mm3)
    ```

=== "Multi-atlas merge"

    ```python
    import pandas as pd
    from pathlib import Path

    results_dir = Path("results")
    frames = []
    for tsv in results_dir.glob("*.tsv"):
        if "_failures" in tsv.name:
            continue
        atlas_name = tsv.stem
        df = pd.read_csv(tsv, sep="\t")
        df["atlas"] = atlas_name
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    ```

=== "Checking failures"

    ```python
    import pandas as pd

    failures = pd.read_csv("results/schaefer100-7_failures.tsv", sep="\t")
    print(f"{len(failures)} subjects failed:")
    print(failures)
    ```
