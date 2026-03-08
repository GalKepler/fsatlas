# Atlas Catalog

fsatlas ships with 22 built-in atlases across 5 families. All atlases are downloaded automatically on first use and cached to `~/.cache/fsatlas/atlases/`.

Use `fsatlas list-atlases` to view the catalog in your terminal.

---

## Cortical Atlases (Surface)

Surface atlases are stored as FreeSurfer annotation files (`.annot`) in `fsaverage` space. fsatlas transfers them to each subject's native surface via `mri_surf2surf`.

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

| Atlas ID | Name | Parcels | Notes |
|----------|------|---------|-------|
| `desikan` | Desikan-Killiany | 68 | Default FreeSurfer atlas |
| `destrieux` | Destrieux 2010 | 148 | High-resolution sulco-gyral |
| `dkt` | DKT | 62 | Mindboggle compatible |

> **Citation (Desikan):** Desikan RS et al. (2006). *An automated labeling system for subdividing the human cerebral cortex on MRI scans into gyral based regions of interest*. NeuroImage, 31(3):968–980.

> **Citation (Destrieux):** Destrieux C et al. (2010). *Automatic parcellation of human cortical gyri and sulci using standard anatomical nomenclature*. NeuroImage, 53(1):1–15.

---

## Subcortical Atlases (Volumetric)

Volumetric atlases are NIfTI files in MNI152NLin6Asym space. fsatlas registers them to each subject's native space using `mri_vol2vol` and the `talairach.xfm` transform.

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
