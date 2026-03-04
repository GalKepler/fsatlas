# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**fsatlas** is a Python CLI tool that automates extraction of morphometric measures from FreeSurfer-processed brain MRI subjects using arbitrary cortical and subcortical atlases. It wraps FreeSurfer tools (`mri_surf2surf`, `mris_anatomical_stats`, `mri_vol2vol`, `mri_segstats`) into a single pipeline.

- **Python**: ≥ 3.10
- **Build backend**: Hatchling
- **CLI framework**: Click
- **External dependency**: FreeSurfer 8.x must be installed and configured (`FREESURFER_HOME`, `SUBJECTS_DIR`)

## Development Commands

```bash
pip install -e ".[dev]"    # Install with dev dependencies
pytest                      # Run tests
ruff check src/             # Lint
ruff format src/            # Format
mypy                        # Type check
```

## Code Quality Settings

- **Ruff**: line-length=100, target py310, rules: E, F, I, W, UP
- **mypy**: python 3.10, warn_return_any=true

## Architecture

The project is currently a flat layout (all modules at root level), though `pyproject.toml` references `src/fsatlas` as the wheel package path with entry point `fsatlas.cli.main:cli`.

### Module Responsibilities

- **main.py** — Click CLI with 4 commands: `extract`, `list-atlases`, `download`, `cli` (root group). Resolves atlases and subjects, sets up logging.
- **pipeline.py** — Orchestrator: loops subjects → validate → transfer atlas → extract stats. Uses Rich progress bars. Outputs per-atlas TSVs and a failures log.
- **environment.py** — `FreeSurferEnv` (detects FS installation/version) and `SubjectPaths` (validates subject directory structure, surfaces, transforms).
- **registry.py** — `AtlasRegistry` loads `catalog.yaml`, manages downloads to `~/.cache/fsatlas/atlases/` (via `platformdirs`). `AtlasSpec` for catalog atlases, `CustomAtlasSpec` for user-provided files. Type union: `AnyAtlasSpec = AtlasSpec | CustomAtlasSpec`.
- **transfer.py** — Wraps `mri_surf2surf` (surface) and `mri_vol2vol` (volumetric, MNI→native via talairach.xfm). Subprocess calls with 600s timeout.
- **extract.py** — Runs `mris_anatomical_stats` / `mri_segstats`, parses whitespace-delimited output, converts to long-format (tidy) DataFrames. Cortical: 9 measures. Volumetric: 7 measures.
- **catalog.yaml** — Built-in atlas definitions (13 atlases across 6 families: Schaefer, Tian Melbourne, HCP-MMP, FreeSurfer builtins DKT/Desikan/Destrieux).

### Data Flow

1. CLI resolves atlas (catalog or custom) and discovers subjects in `SUBJECTS_DIR`
2. Pipeline validates each subject's directory structure
3. Atlas is transferred to subject space (surface annotation or volumetric resampling)
4. Stats are extracted and parsed into long-format DataFrames
5. Results concatenated into `{atlas}_cortical.tsv`, `{atlas}_subcortical.tsv`, and `{atlas}_failures.tsv`

### Output Schema (long-format TSV)

- **Cortical**: subject_id | atlas | hemisphere | region | measure | value
- **Subcortical**: subject_id | atlas | hemisphere (inferred) | region | measure | value

## Docker

```bash
docker build -t fsatlas .
docker run -v /path/to/license.txt:/opt/freesurfer/license.txt fsatlas --help
```

Base image: `freesurfer/freesurfer:8.0.0`, uses Python 3.12 in `/opt/fsatlas-venv`.
