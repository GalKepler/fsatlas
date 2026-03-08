# Docker

fsatlas provides a Docker image based on `freesurfer/freesurfer:8.0.0`. Use it to run fsatlas without installing FreeSurfer locally.

---

## Build the Image

From the repository root:

```bash
docker build -t fsatlas .
```

The image uses a Python virtual environment at `/opt/fsatlas-venv`. The `fsatlas` command is the container entrypoint.

---

## Run the Container

### Basic Usage

```bash
docker run --rm \
    -v /path/to/SUBJECTS_DIR:/subjects \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    -e SUBJECTS_DIR=/subjects \
    fsatlas extract --atlas schaefer100-7 -o /subjects/results
```

### Key Mount Points

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `/path/to/SUBJECTS_DIR` | `/subjects` | FreeSurfer subjects directory |
| `/path/to/license.txt` | `/opt/freesurfer/license.txt` | FreeSurfer license (required) |
| `/path/to/results` | `/results` | Output directory (optional separate mount) |

### With a Separate Output Directory

```bash
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    fsatlas extract --atlas tian-s2 -o /results
```

---

## Examples

### List available atlases

```bash
docker run --rm \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    fsatlas list-atlases
```

### Extract Schaefer 400 for specific subjects

```bash
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    fsatlas extract \
        --atlas schaefer400-17 \
        -s sub-01 -s sub-02 -s sub-03 \
        -o /results
```

### Pre-download an atlas (then run without network)

```bash
# Download to host cache
docker run --rm \
    -v $HOME/.cache/fsatlas:/root/.cache/fsatlas \
    -v /path/to/license.txt:/opt/freesurfer/license.txt \
    fsatlas download schaefer400-17

# Run offline, reusing cache
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v $HOME/.cache/fsatlas:/root/.cache/fsatlas \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    --network none \
    fsatlas extract --atlas schaefer400-17 -o /results
```

### Custom Atlas

```bash
docker run --rm \
    -v /data/subjects:/subjects \
    -v /data/license.txt:/opt/freesurfer/license.txt \
    -v /data/atlases:/atlases \
    -v /data/results:/results \
    -e SUBJECTS_DIR=/subjects \
    fsatlas extract \
        --atlas /atlases/lh.myatlas.annot \
        -o /results
```

---

## Dockerfile Overview

```dockerfile
FROM freesurfer/freesurfer:8.0.0

# Install Python 3.12
RUN apt-get update && apt-get install -y python3.12 python3.12-pip

# Create isolated virtual environment
RUN python3.12 -m venv /opt/fsatlas-venv
ENV PATH="/opt/fsatlas-venv/bin:$PATH"

# Install fsatlas
COPY . /opt/fsatlas-src
RUN pip install /opt/fsatlas-src

ENTRYPOINT ["fsatlas"]
```

---

## Notes

!!! warning "FreeSurfer License Required"
    A valid FreeSurfer license (`license.txt`) must be mounted at `/opt/freesurfer/license.txt`. Licenses are free for academic use — register at the [FreeSurfer website](https://surfer.nmr.mgh.harvard.edu/registration.html).

!!! tip "Atlas Cache Persistence"
    To avoid re-downloading atlases on every container run, mount the host cache:
    ```bash
    -v $HOME/.cache/fsatlas:/root/.cache/fsatlas
    ```

!!! tip "Memory"
    Processing large cohorts or high-resolution atlases may require significant memory. If the container is killed unexpectedly, try increasing Docker's memory limit in Docker Desktop settings.
