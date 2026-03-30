<p align="center">
  <img src="assets/logo.png" alt="fsatlas logo" width="400">
</p>

<div class="hero" markdown>

  **Automated atlas-based morphometry extraction for FreeSurfer-processed brain MRI**

  <div class="badges" markdown>
  [![PyPI](https://img.shields.io/pypi/v/fsatlas.svg)](https://pypi.org/project/fsatlas/)
  [![Python](https://img.shields.io/pypi/pyversions/fsatlas.svg)](https://pypi.org/project/fsatlas/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![FreeSurfer](https://img.shields.io/badge/FreeSurfer-8.x-blue.svg)](https://surfer.nmr.mgh.harvard.edu/)
  </div>
</div>

---

## Why fsatlas?

FreeSurfer's `recon-all` pipeline produces cortical and subcortical statistics for its **built-in atlases** (Desikan-Killiany, Destrieux, DKT). But modern neuroimaging studies increasingly require other parcellations — higher-resolution cortical atlases like **Schaefer 2018** or **HCP-MMP**, or multi-scale subcortical atlases like **Tian 2020**.

Extracting these requires manually chaining several FreeSurfer commands:

```
mri_surf2surf  →  mris_anatomical_stats  →  parse output
mri_vol2vol    →  mri_segstats           →  parse output
```

**fsatlas wraps this entire pipeline into a single command.**

---

## Features

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
**31 Built-in Atlases**

Ships with Schaefer 2018 (100–1000 parcels), Tian 2020 subcortical (Scales I–IV), HCP-MMP1, Brainnetome, Gordon333, AICHA384, AAL116, 4S-156, and all FreeSurfer built-ins. Auto-downloaded on first use.
</div>

<div class="feature-card" markdown>
**Custom Atlas Support**

Point at any `.annot`, `.nii.gz`, `.dlabel.gii`, or `.gca` file. fsatlas auto-detects the format and handles the rest.
</div>

<div class="feature-card" markdown>
**Surface Pipeline**

Transfers `.annot` / `.dlabel.gii` from `fsaverage` → subject via `mri_surf2surf`, then extracts 9 cortical measures via `mris_anatomical_stats`.
</div>

<div class="feature-card" markdown>
**Volumetric Pipeline**

Registers MNI-space NIfTI → subject native space via `mri_vol2vol` + `talairach.xfm`, or applies a GCA via `mri_ca_label`. Extracts 7 measures via `mri_segstats`.
</div>

<div class="feature-card" markdown>
**Wide-Format TSV Output**

One row per region per subject — measures as columns, driven by the atlas LUT. Compatible with pandas, R tidyverse, and any statistical analysis tool.
</div>

<div class="feature-card" markdown>
**Failure Resilience**

Pipeline continues across subjects on errors. All failures are logged to a separate TSV for review.
</div>

</div>

---

## Thirty-Second Demo

```bash
# Install
pip install fsatlas

# See what atlases are available
fsatlas list-atlases

# Extract Schaefer 100-parcel cortical morphometry for all subjects
fsatlas extract --atlas schaefer100-7 --output-dir ./results

# Results:
# ./results/schaefer100-7.tsv
# ./results/schaefer100-7_failures.tsv
```

---

## Output at a Glance

```
subject_id  index  label                hemisphere  thickness_mean_mm  surface_area_mm2  ...  tiv_mm3
----------  -----  -------------------  ----------  -----------------  ----------------  ---  --------
sub-01      1      7Networks_LH_Vis_1   lh          2.341              843.0             ...  1458203.0
sub-01      2      7Networks_LH_Vis_2   lh          2.289              700.5             ...  1458203.0
sub-02      1      7Networks_LH_Vis_1   lh          2.501              857.2             ...  1501044.0
```

Wide-format data — one row per region per subject, every measure as a column. Easy to filter, pivot, or merge in any analysis environment.

---

## Next Steps

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
**[Installation](installation.md)**

Install fsatlas from PyPI or from source. Set up FreeSurfer environment variables.
</div>

<div class="feature-card" markdown>
**[Quick Start](quickstart.md)**

Walk through common extraction workflows with real command examples.
</div>

<div class="feature-card" markdown>
**[Atlas Catalog](user-guide/atlases.md)**

Browse all 31 built-in atlases with descriptions, citations, and parcel counts.
</div>

<div class="feature-card" markdown>
**[CLI Reference](reference/cli.md)**

Full reference for all CLI commands and options.
</div>

</div>
