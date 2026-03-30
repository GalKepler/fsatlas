# Contributing

Contributions to fsatlas are welcome — bug reports, feature requests, documentation improvements, and code contributions.

---

## Development Setup

```bash
git clone https://github.com/GalKepler/fsatlas.git
cd fsatlas
pip install -e ".[dev]"
```

This installs fsatlas in editable mode along with testing and linting tools.

---

## Code Quality

fsatlas uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, and [mypy](https://mypy-lang.org/) for type checking.

| Tool | Command | Configuration |
|------|---------|--------------|
| Lint | `ruff check src/` | line-length=100, rules: E, F, I, W, UP |
| Format | `ruff format src/` | |
| Type check | `mypy` | python_version=3.10, warn_return_any=true |
| Tests | `pytest` | testpaths=["tests"] |

Run all checks:

```bash
ruff check src/
ruff format src/
mypy
pytest
```

---

## Project Structure

```
src/fsatlas/
├── cli/main.py           # CLI commands (Click): extract, list-atlases, download, generate-lut
├── atlases/
│   ├── catalog.yaml      # Built-in atlas definitions (31 atlases)
│   ├── *_labels.tsv      # Bundled LUT files for volumetric atlases
│   └── registry.py       # AtlasRegistry, AtlasSpec, CustomAtlasSpec
└── core/
    ├── bids.py           # BIDS output path construction
    ├── command.py        # run_command() subprocess wrapper
    ├── environment.py    # FreeSurfer detection, subject paths
    ├── extract.py        # FreeSurfer command runners + .stats parsers
    ├── formats.py        # Format handlers: annot, nifti, dlabel_gii, gca
    ├── lut.py            # LookupTable: from_tsv, from_annot, merge_measures
    └── pipeline.py       # run_extraction() + FlatWriter/BidsWriter
tests/
```

---

## Adding a New Atlas to the Catalog

1. Open `src/fsatlas/atlases/catalog.yaml`.
2. Add a new entry following the existing format:

```yaml
- name: my-atlas-id
  family: MyAtlas
  description: "A short description of the atlas"
  format: annot          # annot | nifti | dlabel_gii | gca
  space: fsaverage       # or MNI152NLin6Asym / MNI152NLin2009cAsym
  source_url: "https://..."
  files:
    lh_annot: lh.myatlas.annot
    rh_annot: rh.myatlas.annot
  labels_tsv: labels.tsv
  citation: "Author et al. Year, Journal"
  bids_name: myatlas     # used for --output-layout bids
```

For volumetric atlases:

```yaml
- name: my-subcortical
  family: MyAtlas
  description: "Subcortical parcellation"
  format: nifti
  space: MNI152NLin6Asym
  source_url: "https://..."
  files:
    nifti: my_subcortical_atlas.nii.gz
  labels_tsv: labels.tsv
  citation: "Author et al. Year, Journal"
  bids_name: mysubcortical
```

For atlases not available via HTTP, use `local_source_dir` instead of `source_url`:

```yaml
  local_source_dir: /path/to/local/atlas/directory
```

3. Test with:

```bash
fsatlas list-atlases          # verify it appears
fsatlas download my-atlas-id  # verify download works
fsatlas extract --atlas my-atlas-id -s sub-01 -o /tmp/test
```

---

## Reporting Bugs

Open an issue on GitHub: [https://github.com/GalKepler/fsatlas/issues](https://github.com/GalKepler/fsatlas/issues)

Please include:

- fsatlas version (`fsatlas --version`)
- FreeSurfer version (`freesurfer --version`)
- Python version (`python --version`)
- The full command you ran
- The error message / traceback
- The contents of `{atlas}_failures.tsv` if applicable

---

## Pull Request Checklist

Before submitting a pull request:

- [ ] Code passes `ruff check src/` with no errors
- [ ] Code is formatted with `ruff format src/`
- [ ] Type annotations added for new functions; `mypy` passes
- [ ] Tests added or updated for new behavior
- [ ] `pytest` passes
- [ ] Documentation updated if the CLI or output format changed

---

## Documentation

The documentation site uses [MkDocs Material](https://squidfunk.github.io/mkdocs-material/).

Install docs dependencies:

```bash
pip install mkdocs-material mkdocstrings[python]
```

Serve locally:

```bash
mkdocs serve
# → http://127.0.0.1:8000
```

Build static site:

```bash
mkdocs build
# → site/
```

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
