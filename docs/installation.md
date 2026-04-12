# Installation

## Prerequisites

Before installing fsatlas, ensure you have:

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | ≥ 3.10 | 3.11 and 3.12 also supported |
| FreeSurfer | 8.x | Must be installed and sourced |
| `FREESURFER_HOME` | — | Must be set in your environment |
| `SUBJECTS_DIR` | — | Must point to your subjects directory |

### FreeSurfer Setup

If FreeSurfer is installed but not yet configured, add these lines to your shell profile (`~/.bashrc` or `~/.zshrc`):

```bash
export FREESURFER_HOME=/path/to/freesurfer
source $FREESURFER_HOME/SetUpFreeSurfer.sh
export SUBJECTS_DIR=/path/to/your/subjects
```

Verify your setup:

```bash
freesurfer --version   # should print FreeSurfer 8.x
echo $SUBJECTS_DIR     # should print your subjects directory path
```

---

## Install from PyPI

```bash
pip install fsatlas
```

Verify the installation:

```bash
fsatlas --version
fsatlas list-atlases
```

---

## Install from Source

```bash
git clone https://github.com/GalKepler/fsatlas.git
cd fsatlas
pip install -e ".[dev]"
```

The `[dev]` extras install testing and linting tools (`pytest`, `ruff`, `mypy`).

---

## Install with uv

[uv](https://github.com/astral-sh/uv) is a fast Python package manager:

```bash
uv pip install fsatlas
```

Or add to your project:

```bash
uv add fsatlas
```

---

## Atlas Directory

Built-in atlases are pre-populated inside the Docker and Apptainer images at `/opt/fsatlas/atlases/`. No network access is required at runtime.

The atlas directory is resolved in this order:

1. `FSATLAS_ATLAS_DIR` environment variable (if set)
2. `/opt/fsatlas/atlases/` — baked into the container image
3. `src/fsatlas/atlases/bids_atlases/` — package data fallback (pip install)

If you are running fsatlas **outside a container** (bare pip install), populate the atlas directory before your first run:

```bash
# Populate all built-in atlases into a directory of your choice
fsatlas populate --output-dir /path/to/atlases

# Or populate individual atlases
fsatlas populate schaefer400-7 --output-dir /path/to/atlases
fsatlas populate tian-s2 --output-dir /path/to/atlases

# Tell fsatlas where to find the atlases
export FSATLAS_ATLAS_DIR=/path/to/atlases
```

Alternatively, pass `--atlas-dir` per invocation:

```bash
fsatlas --atlas-dir /path/to/atlases extract --atlas schaefer400-7 -o ./results
```

---

## Containers (No Local FreeSurfer Required)

If you don't have FreeSurfer installed locally, use a pre-built container image. **Apptainer is recommended** for HPC/cluster environments; Docker is convenient for local workstations.

### Apptainer / Singularity (recommended for HPC)

```bash
apptainer pull fsatlas.sif docker://galkepler/fsatlas:latest
```

Or build from the definition file in the repository:

```bash
apptainer build fsatlas.sif apptainer.def
```

### Docker

```bash
docker pull galkepler/fsatlas:latest
```

See the [Containers guide](docker.md) for full usage instructions and examples.

---

## Development Setup

```bash
git clone https://github.com/GalKepler/fsatlas.git
cd fsatlas
pip install -e ".[dev]"

# Verify code quality tools
pytest --version
ruff --version
mypy --version
```

Run the test suite:

```bash
pytest
```

Lint and format:

```bash
ruff check src/
ruff format src/
mypy
```
