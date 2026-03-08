# Custom Atlases

fsatlas supports user-provided atlases in addition to its built-in catalog. Pass a file path to `--atlas` instead of an atlas ID.

---

## Surface Atlases (`.annot`)

Custom surface atlases must be FreeSurfer annotation files in **`fsaverage` space**.

### File Requirements

- Format: `.annot` (FreeSurfer annotation)
- Space: `fsaverage` (or compatible surface)
- Naming convention: `{hemi}.{atlas_name}.annot`
  - e.g., `lh.myatlas.annot` and `rh.myatlas.annot`
- Both hemispheres must be in the **same directory**

### Usage

Provide either hemisphere; fsatlas auto-detects the other:

```bash
fsatlas extract \
    --atlas /path/to/atlases/lh.myatlas.annot \
    -o ./results
```

fsatlas will look for `rh.myatlas.annot` in `/path/to/atlases/`.

### What happens internally

1. fsatlas detects the atlas type from the file extension.
2. For each subject and hemisphere, `mri_surf2surf` is called:
   ```
   mri_surf2surf \
       --srcsubject fsaverage \
       --trgsubject {subject} \
       --hemi {lh|rh} \
       --sval-annot /path/to/{hemi}.myatlas.annot \
       --tval {subject}/label/{hemi}.myatlas.annot
   ```
3. The transferred annotation is stored in the subject's `label/` directory.
4. `mris_anatomical_stats` extracts morphometry for each parcel.

### Output

```
results/
├── myatlas_cortical.tsv
└── myatlas_failures.tsv
```

The atlas name in the output is derived from the filename (`myatlas`).

---

## Volumetric Atlases (`.nii` / `.nii.gz`)

Custom volumetric atlases must be integer-labeled NIfTI files in **MNI152 space**.

### File Requirements

- Format: `.nii` or `.nii.gz`
- Space: MNI152NLin6Asym (FSL standard space)
- Values: integer labels (0 = background)
- Each non-zero integer = one region

### Usage

```bash
fsatlas extract \
    --atlas /path/to/my_subcortical_atlas.nii.gz \
    -o ./results
```

### What happens internally

1. fsatlas detects the atlas type from the file extension.
2. For each subject, `mri_vol2vol` is called with the **inverse** talairach transform:
   ```
   mri_vol2vol \
       --mov /path/to/my_subcortical_atlas.nii.gz \
       --targ {subject}/mri/norm.mgz \
       --xfm {subject}/mri/transforms/talairach.xfm \
       --inv \
       --nearest \
       --o {subject}/mri/atlas/my_subcortical_atlas.mgz
   ```
   - `--inv`: applies the inverse transform (MNI → subject native)
   - `--nearest`: nearest-neighbor interpolation (preserves integer labels)
3. `mri_segstats` extracts volumetric and intensity statistics for each label.

### Output

```
results/
├── my_subcortical_atlas_subcortical.tsv
└── my_subcortical_atlas_failures.tsv
```

---

## Hemisphere Inference for Volumetric Atlases

Since volumetric atlases are not explicitly split by hemisphere, fsatlas **infers hemisphere** from region names using common naming conventions:

| Pattern | Inferred hemisphere |
|---------|---------------------|
| `lh-*`, `*-lh`, `*_lh`, `L_*`, `*-L` | Left (`lh`) |
| `rh-*`, `*-rh`, `*_rh`, `R_*`, `*-R` | Right (`rh`) |
| No match | `bilateral` |

If your atlas uses non-standard naming, the `hemisphere` column will be `bilateral` for unmatched regions.

---

## Tips and Best Practices

!!! tip "Verify fsaverage space"
    Before using a custom surface atlas, confirm it was created in `fsaverage` space. Many atlas repositories provide both fsaverage and other surface spaces — download the correct version.

!!! tip "Check MNI registration"
    For volumetric atlases, confirm the NIfTI header reports MNI space. You can check with `fslhd` or `nibabel`:
    ```python
    import nibabel as nib
    img = nib.load("my_atlas.nii.gz")
    print(img.header.get_sform())   # should match MNI152 affine
    ```

!!! tip "Label 0 is background"
    `mri_segstats` ignores label 0. Ensure all background voxels are labeled 0 in your NIfTI file.

!!! tip "Atlas caching"
    The transferred atlas (in subject space) is cached in each subject's `mri/atlas/` or `label/` directory. Re-runs skip the transfer step unless `--overwrite` is passed.

!!! warning "Deformable registration not supported"
    fsatlas uses affine registration (`talairach.xfm`). For atlases that require deformable (non-linear) registration, you will need to perform the registration manually and pass the result as a volumetric atlas in native space.
