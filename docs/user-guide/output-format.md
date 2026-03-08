# Output Format

fsatlas produces long-format (tidy) TSV files — one row per measure, per region, per subject. This format is directly compatible with pandas, R tidyverse, and statistical analysis software.

---

## Files Written

For each extraction run, fsatlas writes up to three files to `--output-dir`:

| File | Contents | When written |
|------|----------|--------------|
| `{atlas}_cortical.tsv` | Cortical morphometry | Surface atlases |
| `{atlas}_subcortical.tsv` | Subcortical morphometry | Volumetric atlases |
| `{atlas}_failures.tsv` | Per-subject errors | Always (if any failures) |

---

## Cortical Output Schema

**File:** `{atlas}_cortical.tsv`

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | string | Subject directory name (from `$SUBJECTS_DIR`) |
| `atlas` | string | Atlas ID or custom atlas name |
| `hemisphere` | string | `lh` or `rh` |
| `region` | string | Parcel/region label from the annotation |
| `measure` | string | Morphometric measure name (see below) |
| `value` | float | Numeric measurement value |

### Cortical Measures

| Measure | Unit | Description |
|---------|------|-------------|
| `thickness_mean_mm` | mm | Mean cortical thickness across the parcel |
| `surface_area_mm2` | mm² | Total pial surface area of the parcel |
| `gray_matter_volume_mm3` | mm³ | Gray matter volume (thickness × area) |
| `mean_curvature` | 1/mm | Mean curvature (mean of principal curvatures) |
| `gauss_curvature` | 1/mm² | Gaussian curvature |
| `fold_index` | — | Folding index (measure of sulcal depth) |
| `curvature_index` | — | Intrinsic curvature index |
| `integrated_rect_curvature` | — | Integrated rectified curvature |
| `eTIV` | mm³ | Estimated total intracranial volume (for normalization) |

!!! note "eTIV is parcel-level"
    The `eTIV` value is the same for all regions within a subject and hemisphere — it is a subject-level measure replicated per row for convenience in normalization.

### Example

```
subject_id  atlas          hemisphere  region               measure           value
----------  -------------  ----------  -------------------  ----------------  ---------
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   thickness_mean_mm  2.341
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   surface_area_mm2   843.0
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   gray_matter_volume_mm3  2110.0
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   mean_curvature     0.128
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   eTIV               1458203.0
sub-01      schaefer100-7  rh          7Networks_RH_Vis_1   thickness_mean_mm  2.289
```

---

## Subcortical Output Schema

**File:** `{atlas}_subcortical.tsv`

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | string | Subject directory name |
| `atlas` | string | Atlas ID or custom atlas name |
| `hemisphere` | string | `lh`, `rh`, or `bilateral` (inferred from region name) |
| `region` | string | Segmentation label from the atlas |
| `measure` | string | Morphometric measure name (see below) |
| `value` | float | Numeric measurement value |

### Subcortical Measures

| Measure | Unit | Description |
|---------|------|-------------|
| `volume_mm3` | mm³ | Segmentation volume |
| `intensity_mean` | — | Mean MRI intensity within the region |
| `intensity_std` | — | Standard deviation of MRI intensity |
| `intensity_min` | — | Minimum MRI intensity |
| `intensity_max` | — | Maximum MRI intensity |
| `intensity_range` | — | `intensity_max - intensity_min` |
| `voxel_count` | voxels | Number of voxels in the segmentation |

### Example

```
subject_id  atlas    hemisphere  region   measure       value
----------  -------  ----------  -------  ------------  --------
sub-01      tian-s2  lh          CAU-lh   volume_mm3    1248.0
sub-01      tian-s2  lh          CAU-lh   intensity_mean  72.34
sub-01      tian-s2  lh          CAU-lh   intensity_std   8.21
sub-01      tian-s2  rh          CAU-rh   volume_mm3    1301.0
```

---

## Failures Output Schema

**File:** `{atlas}_failures.tsv`

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | string | Subject that failed |
| `atlas` | string | Atlas being processed |
| `stage` | string | Pipeline stage where failure occurred (`validation`, `transfer`, `extract`) |
| `error` | string | Error message |

### Example

```
subject_id  atlas          stage       error
----------  -------------  ----------  ------------------------------------
sub-99      schaefer100-7  validation  Missing file: mri/orig.mgz
sub-55      schaefer100-7  transfer    mri_surf2surf returned exit code 1
```

---

## Working with the Output

=== "Python / pandas"

    ```python
    import pandas as pd

    # Load cortical output
    df = pd.read_csv("results/schaefer100-7_cortical.tsv", sep="\t")

    # All thickness values, left hemisphere
    thickness = df[
        (df["measure"] == "thickness_mean_mm") &
        (df["hemisphere"] == "lh")
    ]

    # Pivot to wide format: rows = subjects, columns = regions
    wide = thickness.pivot_table(
        index="subject_id",
        columns="region",
        values="value"
    )

    # Normalize by eTIV
    etiv = df[df["measure"] == "eTIV"].set_index("subject_id")["value"]
    area = df[df["measure"] == "surface_area_mm2"].copy()
    area["value_norm"] = area.apply(
        lambda row: row["value"] / etiv[row["subject_id"]], axis=1
    )
    ```

=== "R / tidyverse"

    ```r
    library(tidyverse)

    df <- read_tsv("results/schaefer100-7_cortical.tsv")

    # Wide format: subjects × regions for thickness
    thickness_wide <- df |>
      filter(measure == "thickness_mean_mm", hemisphere == "lh") |>
      pivot_wider(
        id_cols = subject_id,
        names_from = region,
        values_from = value
      )

    # eTIV-normalized surface area
    etiv <- df |>
      filter(measure == "eTIV") |>
      select(subject_id, hemisphere, etiv = value) |>
      distinct()

    area_norm <- df |>
      filter(measure == "surface_area_mm2") |>
      left_join(etiv, by = c("subject_id", "hemisphere")) |>
      mutate(value_norm = value / etiv)
    ```

=== "Checking failures"

    ```python
    import pandas as pd

    failures = pd.read_csv("results/schaefer100-7_failures.tsv", sep="\t")
    print(f"{len(failures)} subjects failed")
    print(failures[["subject_id", "stage", "error"]])
    ```
