# Atlas Catalog

fsatlas ships with **31 built-in atlases** across 8 families. All atlases are downloaded automatically on first use (including LUT generation) and cached to `~/.cache/fsatlas/atlases/`.

Use `fsatlas list-atlases` to view the catalog in your terminal.

---

## Cortical Atlases (Surface)

Surface atlases are stored as FreeSurfer annotation files (`.annot`) in `fsaverage` space. fsatlas transfers them to each subject's native surface via `mri_surf2surf`. A LUT TSV (`index`, `label`, `hemisphere`) is auto-generated from the `.annot` colour table at download time.

### Schaefer 2018

A popular functional parcellation of the cerebral cortex derived from resting-state fMRI functional connectivity. Available in multiple resolutions and two network assignment schemes (7 or 17 Yeo networks).

> **Citation:** Schaefer A, Kong R, Gordon EM, et al. (2018). *Local-Global Parcellation of the Human Cerebral Cortex from Intrinsic Functional Connectivity MRI*. Cerebral Cortex, 28(9):3095–3114.

**7-network parcellations:**

| Atlas ID | Parcels | Networks | Hemispheres |
|----------|---------|----------|-------------|
| `schaefer100-7` | 100 | 7 | bilateral |
| `schaefer200-7` | 200 | 7 | bilateral |
| `schaefer300-7` | 300 | 7 | bilateral |
| `schaefer400-7` | 400 | 7 | bilateral |
| `schaefer500-7` | 500 | 7 | bilateral |
| `schaefer600-7` | 600 | 7 | bilateral |
| `schaefer700-7` | 700 | 7 | bilateral |
| `schaefer800-7` | 800 | 7 | bilateral |
| `schaefer900-7` | 900 | 7 | bilateral |
| `schaefer1000-7` | 1000 | 7 | bilateral |

**17-network parcellations:**

| Atlas ID | Parcels | Networks | Hemispheres |
|----------|---------|----------|-------------|
| `schaefer100-17` | 100 | 17 | bilateral |
| `schaefer200-17` | 200 | 17 | bilateral |
| `schaefer300-17` | 300 | 17 | bilateral |
| `schaefer400-17` | 400 | 17 | bilateral |

**Network labels (7-network):** Vis, SomMot, DorsAttn, SalVentAttn, Limbic, Cont, Default

**Network labels (17-network):** VisCent, VisPeri, SomMotA, SomMotB, DorsAttnA, DorsAttnB, SalVentAttnA, SalVentAttnB, LimbicB, LimbicA, ContA, ContB, ContC, DefaultA, DefaultB, DefaultC, TempPar

**Region naming example:** `7Networks_LH_Vis_1`

---

### HCP-MMP 1.0

The Human Connectome Project Multi-Modal Parcellation — 360 cortical areas defined by combining architecture, function, connectivity, and topography from HCP data.

> **Citation:** Glasser MF, Coalson TS, Robinson EC, et al. (2016). *A multi-modal parcellation of human cerebral cortex*. Nature, 536:171–178.

| Atlas ID | Parcels | Notes |
|----------|---------|-------|
| `hcp-mmp` | 360 | 180 per hemisphere |

**Region naming example:** `L_V1_ROI`

---

### FreeSurfer Built-ins

These atlases are already present in every `recon-all` output and require no download. fsatlas uses them directly from the subject's `label/` directory.

| Atlas ID | Name | Format | Parcels | Notes |
|----------|------|--------|---------|-------|
| `desikan` | Desikan-Killiany | annot | 68 | Default FreeSurfer atlas |
| `destrieux` | Destrieux 2010 | annot | 148 | High-resolution sulco-gyral |
| `dkt` | DKT | annot | 62 | Mindboggle compatible |
| `aseg` | FreeSurfer aseg | nifti | 49 | Automatic subcortical segmentation |

> **Citation (Desikan):** Desikan RS et al. (2006). *An automated labeling system for subdividing the human cerebral cortex on MRI scans into gyral based regions of interest*. NeuroImage, 31(3):968–980.

> **Citation (Destrieux):** Destrieux C et al. (2010). *Automatic parcellation of human cortical gyri and sulci using standard anatomical nomenclature*. NeuroImage, 53(1):1–15.

---

### Brainnetome Atlas

A connectivity-based parcellation of the human cerebral cortex.

> **Citation:** Fan L et al. (2016). *The Human Brainnetome Atlas: A New Brain Atlas Based on Connectional Architecture*. Cerebral Cortex, 26(8):3508–3526.

| Atlas ID | Format | Parcels | Notes |
|----------|--------|---------|-------|
| `BN_Atlas` | annot | 246 | 123 per hemisphere, cortical |
| `BN_Atlas_subcotex` | nifti | 36 | Subcortical component |

!!! note "Local files required"
    The Brainnetome atlas is not available for public download via URL. Set `local_source_dir` in your environment or use the atlas after manual placement.

---

### Gordon 2016

A resting-state parcellation of the cerebral cortex.

> **Citation:** Gordon EM et al. (2016). *Generation and Evaluation of a Cortical Area Parcellation from Resting-State Correlations*. Cerebral Cortex, 26(1):288–303.

| Atlas ID | Format | Parcels | Notes |
|----------|--------|---------|-------|
| `gordon333` | annot | 333 | Cortical |
| `gordon333_subcortical` | nifti | 52 | CIT168 + Cerebellum extension |

---

## Subcortical Atlases (Volumetric)

Volumetric atlases are NIfTI files in MNI152 space. fsatlas registers them to each subject's native space using `mri_vol2vol` and the `talairach.xfm` transform. A LUT TSV is required (either bundled in the package or downloaded alongside the atlas).

### Tian 2020 — Melbourne Subcortex Atlas

A multi-scale subcortical atlas derived from resting-state fMRI, with parcellations ranging from coarse (Scale I) to fine-grained (Scale IV).

> **Citation:** Tian Y, Margulies DS, Breakspear M, Zalesky A. (2020). *Topographic organization of the human subcortex unveiled with functional connectivity gradients*. Nature Neuroscience, 23:1421–1432.

| Atlas ID | Scale | Regions | Coverage |
|----------|-------|---------|----------|
| `tian-s1` | I | 16 | 8 bilateral structures |
| `tian-s2` | II | 32 | 16 bilateral structures |
| `tian-s3` | III | 50 | 25 bilateral structures |
| `tian-s4` | IV | 54 | 27 bilateral structures |

**Structures covered:** Caudate, Putamen, Pallidum, Hippocampus, Amygdala, Accumbens, Thalamus (and more at finer scales).

**Region naming example:** `CAU-lh`, `PUT-rh`, `HIP-lh`

---

### HCPex Subcortical

Subcortical extension of the HCP-MMP atlas covering thalamus, amygdala, hippocampus, and related structures.

> **Citation:** Huang CC et al. (2022). *Subcortical brain atlas using the Human Connectome Project parcellation*. Cerebral Cortex.

| Atlas ID | Format | Parcels | Space |
|----------|--------|---------|-------|
| `hcpex_subcortical` | nifti | 66 | MNI152NLin2009cAsym |

---

### AICHA 2015

Atlas of Intrinsic Connectivity of Homotopic Areas — 384 bilateral cortical regions derived from resting-state fMRI.

> **Citation:** Joliot M et al. (2015). *AICHA: An atlas of intrinsic connectivity of homotopic areas*. Journal of Neuroscience Methods, 254:46–59.

| Atlas ID | Format | Parcels | Notes |
|----------|--------|---------|-------|
| `aicha384` | nifti | 384 | Full cortical atlas |
| `aicha384_subcortical` | nifti | 50 | Subcortical subset |

---

### AAL 2002

The classic Automated Anatomical Labeling atlas.

> **Citation:** Tzourio-Mazoyer N et al. (2002). *Automated Anatomical Labeling of Activations in SPM Using a Macroscopic Anatomical Parcellation of the MNI MRI Single-Subject Brain*. NeuroImage, 15(1):273–289.

| Atlas ID | Format | Parcels | Space |
|----------|--------|---------|-------|
| `aal116` | nifti | 116 | MNI152NLin2009cAsym |

**Region naming example:** `Precentral_L`, `Hippocampus_R`

---

### 4S-156 Subcortical

A subcortical atlas with 56 regions derived from the 4S parcellation framework.

| Atlas ID | Format | Parcels | Space |
|----------|--------|---------|-------|
| `4s156_subcortical` | nifti | 56 | MNI152NLin2009cAsym |

---

## Choosing the Right Atlas

| Use case | Recommended atlas |
|----------|------------------|
| Functional connectivity alignment | `schaefer100-7`, `schaefer400-17` |
| Fine-grained cortical parcellation | `hcp-mmp` |
| Compatibility with HCP pipelines | `hcp-mmp` |
| Subcortical segmentation | `tian-s2` or `tian-s3` |
| Legacy / broad compatibility | `desikan` |
| High-resolution sulcal | `destrieux` |
| Mindboggle / label fusion | `dkt` |

---

## Pre-downloading Atlases

Before running a batch job, pre-download all needed atlases:

```bash
fsatlas download schaefer400-17
fsatlas download tian-s2
fsatlas download hcp-mmp
```

The cache directory is:

```
~/.cache/fsatlas/atlases/{atlas_id}/
```

To force re-download of a cached atlas:

```bash
fsatlas download --force schaefer400-7
```
