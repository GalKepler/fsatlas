<div class="hero" markdown>
  ![fsatlas logo](assets/logo.png)

  # fsatlas

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
**22 Built-in Atlases**

Ships with Schaefer 2018 (100–1000 parcels), Tian 2020 subcortical (Scales I–IV), HCP-MMP1, and all FreeSurfer built-ins. Auto-downloaded on first use.
</div>

<div class="feature-card" markdown>
**Custom Atlas Support**

Point at any `.annot` (surface) or `.nii.gz` (volumetric, MNI space) file. fsatlas handles the rest.
</div>

<div class="feature-card" markdown>
**Surface Pipeline**

Transfers `.annot` from `fsaverage` → subject via `mri_surf2surf`, then extracts 9 cortical measures via `mris_anatomical_stats`.
</div>

<div class="feature-card" markdown>
**Volumetric Pipeline**

Registers MNI-space NIfTI → subject native space via `mri_vol2vol` + `talairach.xfm`, extracts 7 measures via `mri_segstats`.
</div>

<div class="feature-card" markdown>
**Tidy TSV Output**

Long-format output — one row per measure — compatible with pandas, R tidyverse, and any statistical analysis tool.
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
# ./results/schaefer100-7_cortical.tsv
# ./results/schaefer100-7_failures.tsv
```

---

## Output at a Glance

```
subject_id  atlas          hemisphere  region               measure           value
----------  -------------  ----------  -------------------  ----------------  ------
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   thickness_mean_mm  2.341
sub-01      schaefer100-7  lh          7Networks_LH_Vis_1   surface_area_mm2   843.0
sub-01      schaefer100-7  rh          7Networks_RH_Vis_1   thickness_mean_mm  2.289
sub-02      schaefer100-7  lh          7Networks_LH_Vis_1   thickness_mean_mm  2.501
```

Long-format (tidy) data — easy to filter, pivot, or merge in any analysis environment.

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

Browse all 22 built-in atlases with descriptions, citations, and parcel counts.
</div>

<div class="feature-card" markdown>
**[CLI Reference](reference/cli.md)**

Full reference for all CLI commands and options.
</div>

</div>
