"""Pipeline orchestrator: ties together atlas download, transfer, and extraction."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from ..atlases.registry import AnyAtlasSpec, AtlasRegistry, AtlasSpec
from .bids import build_bids_path, parse_bids_entities
from .environment import FreeSurferEnv
from .formats import get_handler
from .lut import LookupTable

logger = logging.getLogger(__name__)


def _load_lut(atlas: AnyAtlasSpec, env: FreeSurferEnv | None = None) -> LookupTable:
    """Load the LUT for *atlas*, generating it from cache if needed."""
    lut_path = atlas.labels_tsv_path
    if lut_path is None and isinstance(atlas, AtlasSpec):
        # Try to generate on the fly (e.g. builtin annot atlas)
        registry = AtlasRegistry()
        registry.download(atlas.name, env=env)
        lut_path = atlas.labels_tsv_path
    if lut_path is None:
        raise RuntimeError(
            f"No LUT found for atlas '{atlas.name}'. "
            "Run 'fsatlas download <name>' first, or supply --lut."
        )
    return LookupTable.from_tsv(lut_path)


# ---------------------------------------------------------------------------
# Output writer strategy
# ---------------------------------------------------------------------------

class OutputWriter(ABC):
    """Strategy for writing extraction results to disk."""

    @abstractmethod
    def write_subject(
        self, df: pd.DataFrame, subject_id: str, atlas: AnyAtlasSpec
    ) -> Path | None:
        """Write one subject's result. Returns the path written, or None on no-op."""

    @abstractmethod
    def finalize(self) -> dict[str, Path]:
        """Flush any buffered data and return a dict of {kind: path} for the output."""


class FlatWriter(OutputWriter):
    """Accumulate all subjects into memory, then write a single TSV per atlas."""

    def __init__(self, output_dir: Path, atlas: AnyAtlasSpec) -> None:
        self._output_dir = output_dir
        self._atlas = atlas
        self._frames: list[pd.DataFrame] = []

    def write_subject(self, df: pd.DataFrame, subject_id: str, atlas: AnyAtlasSpec) -> None:
        self._frames.append(df)
        return None

    def finalize(self) -> dict[str, Path]:
        if not self._frames:
            return {}
        out_df = pd.concat(self._frames, ignore_index=True)
        out_path = self._output_dir / f"{self._atlas.name}.tsv"
        out_df.to_csv(out_path, sep="\t", index=False)
        logger.info(f"Output written to {out_path} ({len(out_df)} rows)")
        return {"output": out_path}


class BidsWriter(OutputWriter):
    """Write one CSV per subject in a BIDS-like directory tree."""

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._written: list[Path] = []

    def write_subject(
        self, df: pd.DataFrame, subject_id: str, atlas: AnyAtlasSpec
    ) -> Path:
        entities = parse_bids_entities(subject_id)
        path = build_bids_path(
            self._output_dir,
            entities,
            atlas.bids_atlas_name,
            atlas.structure,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        logger.info(f"Written {path}")
        self._written.append(path)
        return path

    def finalize(self) -> dict[str, Path]:
        if not self._written:
            return {}
        # Return the first written path as "output" for summary display;
        # callers can inspect the directory for all files.
        return {"output": self._written[0]}


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def run_extraction(
    atlas: AnyAtlasSpec,
    subjects: list[str],
    env: FreeSurferEnv,
    output_dir: Path,
    force: bool = False,
    output_layout: str = "flat",
) -> dict[str, Path]:
    """Run the full extraction pipeline for one atlas across subjects.

    Steps:
      1. Load the atlas LUT (once).
      2. For each subject: validate → transfer → extract → merge with LUT.
      3. Write results according to *output_layout*:
         - ``"flat"``  (default) – all subjects concatenated into a single TSV.
         - ``"bids"``  – per-subject CSV files in a BIDS-like directory tree.

    Returns a dict with keys ``"output"`` and/or ``"failures"`` mapping to Paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load LUT once — it defines the output schema
    lut = _load_lut(atlas, env)

    # Get handler for the atlas format
    handler = get_handler(atlas.format)

    # Choose writer strategy
    if output_layout == "bids":
        writer: OutputWriter = BidsWriter(output_dir)
    else:
        writer = FlatWriter(output_dir, atlas)

    failed_subjects: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task(f"Extracting {atlas.name}", total=len(subjects))

        for subject_id in subjects:
            progress.update(task, description=f"{atlas.name} → {subject_id}")

            try:
                subject = env.find_subject(subject_id)

                missing = subject.validate()
                if missing:
                    logger.warning(f"Subject {subject_id} missing files: {missing}. Skipping.")
                    failed_subjects.append((subject_id, f"Missing: {missing}"))
                    progress.advance(task)
                    continue

                logger.info(f"Processing {subject_id} with atlas {atlas.name}")

                # Transfer atlas to subject space
                transfer_result = handler.transfer(atlas, subject, env, force)

                # Build ctab for mri_segstats if volumetric
                ctab_path: Path | None = None
                if handler.join_on == "index":
                    ctab_path = lut.to_ctab()

                try:
                    # Extract stats (raw DataFrame + eTIV)
                    if ctab_path is not None:
                        # Inject ctab into the run_segstats call via a patched transfer result
                        raw_df, tiv = _extract_with_ctab(
                            handler, atlas, subject, env, transfer_result, ctab_path, force
                        )
                    else:
                        raw_df, tiv = handler.extract(atlas, subject, env, transfer_result, force)
                finally:
                    if ctab_path is not None and ctab_path.exists():
                        ctab_path.unlink(missing_ok=True)

                # Merge with LUT → wide-format DataFrame
                result_df = lut.merge_measures(
                    raw_stats=raw_df,
                    subject_id=subject_id,
                    tiv=tiv,
                    measure_map=handler.measure_map,
                    join_on=handler.join_on,
                )
                writer.write_subject(result_df, subject_id, atlas)

            except Exception as e:
                logger.error(f"Failed for {subject_id}: {e}")
                failed_subjects.append((subject_id, str(e)))

            progress.advance(task)

    output_paths: dict[str, Path] = writer.finalize()

    if failed_subjects:
        logger.warning(f"{len(failed_subjects)} subject(s) failed:")
        for sid, reason in failed_subjects:
            logger.warning(f"  {sid}: {reason}")
        fail_name = f"{atlas.bids_atlas_name}_failures.csv"
        fail_path = output_dir / fail_name
        pd.DataFrame(failed_subjects, columns=["subject_id", "reason"]).to_csv(
            fail_path, index=False
        )
        output_paths["failures"] = fail_path

    return output_paths


def _extract_with_ctab(handler, atlas, subject, env, transfer_result, ctab_path, force):
    """Call handler.extract with the ctab injected into the segstats command.

    The NiftiHandler and GcaHandler call ``_run_segstats`` without a ctab.
    We patch the call by temporarily overriding the segstats runner.
    """
    from .extract import _parse_etiv_from_header, _parse_segstats_file, _run_segstats

    seg_path = transfer_result.paths["volume"]
    stats_path = _run_segstats(
        subject=subject,
        env=env,
        seg_path=seg_path,
        atlas_name=atlas.name,
        ctab_path=ctab_path,
        force=force,
    )
    tiv = _parse_etiv_from_header(stats_path)
    df = _parse_segstats_file(stats_path)
    return df, tiv
