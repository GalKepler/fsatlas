# Custom Atlases

fsatlas supports user-provided atlases in addition to its built-in catalog. Pass a file path to `--atlas` instead of an atlas ID. Four file formats are supported.

---

## LUT Requirement

Every atlas — built-in or custom — requires a **lookup table (LUT)**: a TSV file mapping integer indices to region labels. The LUT drives the output schema (each row in the output corresponds to one LUT entry).

**Minimum required columns:**

| Column | Description |
|--------|-------------|
| `index` | Integer label value in the atlas file |
| `label` | Human-readable region name |
| `hemisphere` | `lh`, `rh`, or `bilateral` (inferred from name if omitted) |

Additional columns (e.g. `network`, `color_r`, `color_g`, `color_b`) are preserved in the output.

Pass a LUT with `--lut`:

```bash
fsatlas extract --atlas /path/to/lh.myatlas.annot --lut /path/to/lut.tsv -o ./results
```

### Generating a LUT from .annot files

Use the `generate-lut` command to extract the embedded colour table from a `.annot` file pair:

```bash
fsatlas generate-lut \
    --lh-annot /path/to/lh.myatlas.annot \
    --rh-annot /path/to/rh.myatlas.annot \
    --output myatlas_lut.tsv
```

For catalog atlases (including FreeSurfer builtins):

```bash
fsatlas generate-lut --atlas desikan --output desikan_lut.tsv
fsatlas generate-lut --atlas schaefer400-7 --output schaefer400-7_lut.tsv
```

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
    --lut /path/to/myatlas_lut.tsv \
    -o ./results
```

Or generate the LUT on-the-fly first:

```bash
fsatlas generate-lut \
    --lh-annot /path/to/lh.myatlas.annot \
    --rh-annot /path/to/rh.myatlas.annot \
    --output myatlas_lut.tsv

fsatlas extract \
    --atlas /path/to/lh.myatlas.annot \
    --lut myatlas_lut.tsv \
    -o ./results
```

### What happens internally

1. fsatlas detects the format from the `.annot` extension.
2. For each subject and hemisphere, `mri_surf2surf` transfers the annotation to subject space:
   ```
   mri_surf2surf \
       --srcsubject fsaverage \
       --trgsubject {subject} \
       --hemi {lh|rh} \
       --sval-annot /path/to/{hemi}.myatlas.annot \
       --tval {subject}/label/{hemi}.myatlas.annot
   ```
3. `mris_anatomical_stats` extracts 9 cortical measures per parcel.
4. Measures are merged onto the LUT → wide-format output.

---

## Volumetric Atlases (`.nii` / `.nii.gz`)

Custom volumetric atlases must be integer-labeled NIfTI files in **MNI152 space**.

### File Requirements

- Format: `.nii` or `.nii.gz`
- Space: MNI152NLin6Asym (FSL standard) or MNI152NLin2009cAsym
- Values: integer labels (0 = background)

### Usage

```bash
fsatlas extract \
    --atlas /path/to/my_subcortical_atlas.nii.gz \
    --lut /path/to/lut.tsv \
    -o ./results
```

### What happens internally

1. `mri_vol2vol` registers the atlas to each subject's native space via the `talairach.xfm`:
   ```
   mri_vol2vol \
       --mov /path/to/my_atlas.nii.gz \
       --targ {subject}/mri/norm.mgz \
       --xfm {subject}/mri/transforms/talairach.xfm \
       --interp nearest \
       --o {subject}/mri/atlas/my_atlas_native.nii.gz
   ```
2. `mri_segstats` extracts 7 volumetric/intensity measures per label.
3. Measures are merged onto the LUT → wide-format output.

---

## CIFTI Dense Label Atlases (`.dlabel.gii`)

CIFTI `.dlabel.gii` files contain per-vertex surface parcellations (HCP-style).

### File Requirements

- Format: `.dlabel.gii`
- Space: `fsaverage` (or another surface space)
- Naming: `{hemi}.{atlas_name}.dlabel.gii`

### Usage

```bash
fsatlas extract \
    --atlas /path/to/lh.myatlas.dlabel.gii \
    --format dlabel_gii \
    --lut /path/to/lut.tsv \
    -o ./results
```

### What happens internally

1. `mris_convert --dlabel-to-annot` converts the `.dlabel.gii` to a `.annot` file.
2. The rest of the pipeline is identical to the `.annot` surface path.

!!! note "FreeSurfer 7.4+ required"
    `mris_convert --dlabel-to-annot` is available in FreeSurfer ≥ 7.4. FreeSurfer 8.x is recommended.

---

## GCA Atlases (`.gca`)

FreeSurfer `.gca` (Gaussian Classifier Atlas) files define probabilistic subcortical segmentations.

### File Requirements

- Format: `.gca` (FreeSurfer Gaussian Classifier Atlas)
- Requires `mri/transforms/talairach.m3z` in each subject directory

### Usage

```bash
fsatlas extract \
    --atlas /path/to/myatlas.gca \
    --format gca \
    --lut /path/to/lut.tsv \
    -o ./results
```

### What happens internally

1. `mri_ca_label` applies the GCA to each subject's `norm.mgz` using `talairach.m3z`:
   ```
   mri_ca_label \
       {subject}/mri/norm.mgz \
       {subject}/mri/transforms/talairach.m3z \
       /path/to/myatlas.gca \
       {subject}/mri/atlas/myatlas_native.mgz
   ```
2. `mri_segstats` extracts volumetric/intensity measures from the resulting segmentation.
3. Measures are merged onto the LUT → wide-format output.

---

## Format Detection

fsatlas auto-detects the format from the file extension:

| Extension | Detected format |
|-----------|----------------|
| `.annot` | `annot` |
| `.nii`, `.nii.gz` | `nifti` |
| `.dlabel.gii`, `.label.gii` | `dlabel_gii` |
| `.gca` | `gca` |

Override with `--format` when auto-detection is ambiguous:

```bash
fsatlas extract --atlas /path/to/atlas.gii --format dlabel_gii --lut lut.tsv -o ./results
```

---

## Tips and Best Practices

!!! tip "Verify fsaverage space"
    Before using a custom surface atlas, confirm it was created in `fsaverage` space. Many atlas repositories provide both fsaverage and other surface spaces — download the correct version.

!!! tip "Check MNI registration"
    For volumetric atlases, confirm the NIfTI header reports MNI space. You can check with `nibabel`:
    ```python
    import nibabel as nib
    img = nib.load("my_atlas.nii.gz")
    print(img.header.get_sform())   # should match MNI152 affine
    ```

!!! tip "Label 0 is background"
    `mri_segstats` ignores label 0. Ensure all background voxels are labeled 0 in your NIfTI or GCA-produced volume.

!!! tip "Hemisphere in the LUT"
    For volumetric atlases, adding a `hemisphere` column to your LUT TSV avoids relying on name-based inference. This is especially useful for atlases with non-standard region naming.

!!! tip "Atlas caching"
    Transferred atlas files are cached in each subject's `mri/atlas/` or `label/` directory. Re-runs skip the transfer step unless `--force` is passed.

!!! warning "Affine registration only (nifti)"
    The NIfTI handler uses the affine `talairach.xfm`. For atlases that require non-linear (deformable) registration, register manually and pass the native-space result as a volumetric atlas. The GCA handler uses the non-linear `talairach.m3z`.
