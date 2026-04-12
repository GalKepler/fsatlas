# Containers

fsatlas ships as a pre-built container image based on `freesurfer/freesurfer:8.0.0`. Use it to run fsatlas without installing FreeSurfer locally.

**Apptainer is recommended** for HPC and cluster environments. Docker works well on local workstations.

---

## Apptainer / Singularity

[Apptainer](https://apptainer.org/) (formerly Singularity) is the standard container runtime on most HPC clusters. It runs containers as an unprivileged user, mounts the host filesystem automatically, and integrates well with SLURM and PBS schedulers.

### Pull the image

```bash
apptainer pull fsatlas.sif docker://galkepler/fsatlas:latest
```

Or build from source (requires the repository):

```bash
apptainer build fsatlas.sif apptainer.def
```

### Basic usage

```bash
apptainer run \
    --bind /path/to/SUBJECTS_DIR:/subjects \
    --bind /path/to/license.txt:/license.txt:ro \
    --env SUBJECTS_DIR=/subjects \
    fsatlas.sif \
    --freesurfer-license-file /license.txt \
    extract --atlas schaefer100-7 -o /subjects/results
```

### License via environment variable

```bash
export FS_LICENSE=/path/to/license.txt

apptainer run \
    --bind /path/to/SUBJECTS_DIR:/subjects \
    --env SUBJECTS_DIR=/subjects \
    --env FS_LICENSE=/path/to/license.txt \
    fsatlas.sif \
    extract --atlas schaefer100-7 -o /subjects/results
```

### List available atlases

```bash
apptainer run \
    --bind /path/to/license.txt:/license.txt:ro \
    fsatlas.sif \
    --freesurfer-license-file /license.txt \
    list-atlases
```

### SLURM example

```bash
#!/bin/bash
#SBATCH --job-name=fsatlas
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=12:00:00

apptainer run \
    --bind $SUBJECTS_DIR:/subjects \
    --bind $FS_LICENSE:/license.txt:ro \
    --env SUBJECTS_DIR=/subjects \
    /path/to/fsatlas.sif \
    --freesurfer-license-file /license.txt \
    extract \
        --atlas schaefer400-17 \
        --subjects-file subjects.txt \
        --jobs 8 \
        -o /subjects/fsatlas_output
```

`--jobs` should match `--cpus-per-task`. Each worker thread runs an independent FreeSurfer subprocess; adjust `--mem` accordingly (roughly 4–8 GB per job for typical cohort sizes).

---

## Docker

### Pull the image

```bash
docker pull galkepler/fsatlas:latest
```

Or build from source:

```bash
docker build -t fsatlas .
```

### Basic usage

```bash
docker run --rm \
    -v /path/to/SUBJECTS_DIR:/subjects \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    -e SUBJECTS_DIR=/subjects \
    galkepler/fsatlas:latest \
    extract --atlas schaefer100-7 -o /subjects/results
```

### With a separate output directory

```bash
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    galkepler/fsatlas:latest \
    extract --atlas tian-s2 -o /results
```

### Examples

#### List available atlases

```bash
docker run --rm \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    galkepler/fsatlas:latest \
    list-atlases
```

#### Extract Schaefer 400 for specific subjects

```bash
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    galkepler/fsatlas:latest \
    extract \
        --atlas schaefer400-17 \
        -s sub-01 -s sub-02 -s sub-03 \
        -o /results
```

#### Custom atlas

```bash
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v /data/atlases:/atlases \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    galkepler/fsatlas:latest \
    extract \
        --atlas /atlases/lh.myatlas.annot \
        --lut /atlases/myatlas_lut.tsv \
        -o /results
```

---

## Key Mount Points

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `$SUBJECTS_DIR` | `/subjects` | FreeSurfer subjects directory |
| `/path/to/license.txt` | `/opt/freesurfer/license.txt` (Docker) or via `--freesurfer-license-file` | FreeSurfer license (required) |
| Output directory | `/results` | Results (optional separate mount) |

---

## Notes

!!! warning "FreeSurfer License Required"
    A valid FreeSurfer license (`license.txt`) must be provided. Licenses are free for academic use — register at the [FreeSurfer website](https://surfer.nmr.mgh.harvard.edu/registration.html).

    For Apptainer, pass it with `--freesurfer-license-file /path/to/license.txt` or set `FS_LICENSE`.
    For Docker, mount it at `/opt/freesurfer/license.txt`.

!!! tip "Atlases ship with the image"
    All built-in atlases are pre-populated inside the image at `/opt/fsatlas/atlases/`. No network access is needed at runtime and no cache directory needs to be mounted.

!!! tip "Memory"
    Processing large cohorts or high-resolution atlases may require significant memory. For Docker Desktop, increase the memory limit in settings. For SLURM, adjust `--mem`.
