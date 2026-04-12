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

- **main.py** — Click CLI with 5 commands: `extract`, `aggregate`, `list-atlases`, `populate`, `generate-lut` (root group `cli`). Resolves atlases and subjects, sets up logging. Global `--atlas-dir` option (envvar `FSATLAS_ATLAS_DIR`).
- **pipeline.py** — Orchestrator: loops subjects → validate → transfer atlas → extract stats. Uses Rich progress bars. Outputs per-atlas TSVs and a failures log.
- **environment.py** — `FreeSurferEnv` (detects FS installation/version) and `SubjectPaths` (validates subject directory structure, surfaces, transforms).
- **registry.py** — `AtlasRegistry` loads `catalog.yaml`. `AtlasSpec` resolves atlas files from a BIDS atlas directory (env var `FSATLAS_ATLAS_DIR` → `/opt/fsatlas/atlases/` → package fallback). `CustomAtlasSpec` for user-provided files. Type union: `AnyAtlasSpec = AtlasSpec | CustomAtlasSpec`. No download logic — atlases are pre-populated at build time.
- **populate.py** (`atlases/`) — `populate_atlas()`, `populate_all()`: populates a BIDS atlas directory from source files/URLs and generates LUT TSVs. Used by `fsatlas populate` CLI and `scripts/build_bids_atlases.py` (Docker build).
- **transfer.py** — Wraps `mri_surf2surf` (surface) and `mri_vol2vol` (volumetric, MNI→native via talairach.xfm). Subprocess calls with 600s timeout.
- **extract.py** — Runs `mris_anatomical_stats` / `mri_segstats`, parses whitespace-delimited output, converts to long-format (tidy) DataFrames. Cortical: 9 measures. Volumetric: 7 measures.
- **aggregate.py** — `discover_atlases`, `discover_csv_files`, `_parse_entities_from_path`, `_standardize_dataframe`, `aggregate`. Scans a BIDS output directory and concatenates per-subject CSVs into a single wide-format DataFrame. Drops atlas-specific extra columns; renames `gray_matter_volume_mm3` → `volume_mm3` for consistency with subcortical naming. No FreeSurfer dependency.
- **catalog.yaml** — Built-in atlas definitions (31 atlases across 8 families). Fields `source_url`, `files`, `labels_tsv`, `local_source_dir` are build-time-only metadata used by `populate.py`.

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
