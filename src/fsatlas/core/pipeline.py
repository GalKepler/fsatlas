"""Pipeline orchestrator: ties together atlas download, transfer, and extraction."""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from .. import __version__
from ..atlases.registry import AnyAtlasSpec
from .bids import BidsEntities, build_bids_path, parse_bids_entities
from .environment import FreeSurferEnv
from .formats import AtlasFormatHandler, get_handler
from .lut import LookupTable

logger = logging.getLogger(__name__)


def _load_lut(atlas: AnyAtlasSpec, env: FreeSurferEnv | None = None) -> LookupTable:
    """Load the LUT for *atlas* from the BIDS atlas directory."""
    lut_path = atlas.labels_tsv_path
    if lut_path is None:
        raise RuntimeError(
            f"No LUT found for atlas '{atlas.name}'. "
            "Ensure the BIDS atlas directory is populated. "
            "Run 'fsatlas populate' or use the Docker/Apptainer image, "
            "which includes all atlases pre-built."
        )
    return LookupTable.from_tsv(lut_path)


# ---------------------------------------------------------------------------
# Sidecar metadata builder
# ---------------------------------------------------------------------------

def build_sidecar(
    atlas: AnyAtlasSpec,
    handler: AtlasFormatHandler,
    env: FreeSurferEnv,
    entities: BidsEntities | None = None,
    commands_run: list[list[str]] | None = None,
) -> dict[str, Any]:
    """Build a metadata sidecar dict describing an fsatlas output file.

    Parameters
    ----------
    atlas:
        The atlas spec used for extraction.
    handler:
        The format handler that performed transfer and extraction.
    env:
        FreeSurfer environment (used to record the FS version).
    entities:
        Optional BIDS entities for per-subject outputs (adds sub/ses fields).
    commands_run:
        Actual command invocations executed for this output (transfer + extract).
        When None, falls back to listing the tool names from the handler.
    """
    lut_path = atlas.labels_tsv_path
    sidecar: dict[str, Any] = {
        "atlas_name": atlas.name,
        "atlas_description": atlas.description,
        "atlas_format": atlas.format,
        "atlas_type": atlas.type,
        "atlas_space": atlas.space,
        "atlas_citation": atlas.citation,
        "lut_file": str(lut_path) if lut_path is not None else None,
        "measures": list(handler.measure_map.values()),
        "commands_run": (
            [" ".join(c) for c in commands_run]
            if commands_run is not None
            else list(handler.commands)
        ),
        "freesurfer_version": env.version,
        "generated_by": {
            "name": "fsatlas",
            "version": __version__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if entities is not None:
        sidecar["subject"] = f"sub-{entities.sub}"
        if entities.ses is not None:
            sidecar["session"] = f"ses-{entities.ses}"
    return sidecar


def _write_sidecar(path: Path, data: dict[str, Any]) -> None:
    """Write *data* as a JSON sidecar next to *path* (replaces extension with .json)."""
    sidecar_path = path.with_suffix(".json")
    with open(sidecar_path, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Sidecar written to {sidecar_path}")


# ---------------------------------------------------------------------------
# Output writer strategy
# ---------------------------------------------------------------------------

class OutputWriter(ABC):
    """Strategy for writing extraction results to disk."""

    @abstractmethod
    def write_subject(
        self,
        df: pd.DataFrame,
        subject_id: str,
        atlas: AnyAtlasSpec,
        commands_run: list[list[str]] | None = None,
    ) -> Path | None:
        """Write one subject's result. Returns the path written, or None on no-op."""

    @abstractmethod
    def finalize(self) -> dict[str, Path]:
        """Flush any buffered data and return a dict of {kind: path} for the output."""


class FlatWriter(OutputWriter):
    """Accumulate all subjects into memory, then write a single TSV per atlas."""

    def __init__(
        self,
        output_dir: Path,
        atlas: AnyAtlasSpec,
        handler: AtlasFormatHandler | None = None,
        env: FreeSurferEnv | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._atlas = atlas
        self._handler = handler
        self._env = env
        self._frames: list[pd.DataFrame] = []
        self._all_commands: dict[str, list[list[str]]] = {}
        self._lock = threading.Lock()

    def write_subject(
        self,
        df: pd.DataFrame,
        subject_id: str,
        atlas: AnyAtlasSpec,
        commands_run: list[list[str]] | None = None,
    ) -> None:
        with self._lock:
            self._frames.append(df)
            if commands_run:
                self._all_commands.setdefault(subject_id, []).extend(commands_run)
        return None

    def finalize(self) -> dict[str, Path]:
        if not self._frames:
            return {}
        out_df = pd.concat(self._frames, ignore_index=True)
        out_path = self._output_dir / f"{self._atlas.name}.tsv"
        out_df.to_csv(out_path, sep="\t", index=False)
        logger.info(f"Output written to {out_path} ({len(out_df)} rows)")
        if self._handler is not None and self._env is not None:
            sidecar = build_sidecar(self._atlas, self._handler, self._env)
            if self._all_commands:
                sidecar["commands_run"] = {
                    sid: [" ".join(c) for c in cmds]
                    for sid, cmds in self._all_commands.items()
                }
            _write_sidecar(out_path, sidecar)
        return {"output": out_path}


class BidsWriter(OutputWriter):
    """Write one CSV per subject in a BIDS-like directory tree."""

    def __init__(
        self,
        output_dir: Path,
        handler: AtlasFormatHandler | None = None,
        env: FreeSurferEnv | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._handler = handler
        self._env = env
        self._written: list[Path] = []
        self._lock = threading.Lock()

    def write_subject(
        self,
        df: pd.DataFrame,
        subject_id: str,
        atlas: AnyAtlasSpec,
        commands_run: list[list[str]] | None = None,
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
        if self._handler is not None and self._env is not None:
            _write_sidecar(
                path,
                build_sidecar(
                    atlas, self._handler, self._env,
                    entities=entities, commands_run=commands_run,
                ),
            )
        with self._lock:
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

def _process_one_subject(
    subject_id: str,
    atlas: AnyAtlasSpec,
    env: FreeSurferEnv,
    handler,
    lut: LookupTable,
    force: bool,
) -> tuple[pd.DataFrame, list[list[str]]]:
    """Process a single subject: validate → transfer → extract → merge with LUT.

    Returns ``(result_df, commands_run)``. Raises on any failure.
    """
    subject = env.find_subject(subject_id)
    missing = subject.validate()
    if missing:
        raise ValueError(f"Missing files: {missing}")

    logger.info(f"Processing {subject_id} with atlas {atlas.name}")

    transfer_result = handler.transfer(atlas, subject, env, force)

    ctab_path: Path | None = None
    if handler.join_on == "index":
        ctab_path = lut.to_ctab()

    try:
        if ctab_path is not None:
            raw_df, header_measures = _extract_with_ctab(
                handler, atlas, subject, env, transfer_result, ctab_path, force
            )
        else:
            raw_df, header_measures = handler.extract(atlas, subject, env, transfer_result, force)
    finally:
        if ctab_path is not None and ctab_path.exists():
            ctab_path.unlink(missing_ok=True)

    result_df = lut.merge_measures(
        raw_stats=raw_df,
        subject_id=subject_id,
        header_measures=header_measures,
        measure_map=handler.measure_map,
        join_on=handler.join_on,
    )
    return result_df, transfer_result.commands_run


def run_extraction(
    atlas: AnyAtlasSpec,
    subjects: list[str],
    env: FreeSurferEnv,
    output_dir: Path,
    force: bool = False,
    output_layout: str = "flat",
    jobs: int = 1,
    registration_backend: str = "easyreg",
) -> dict[str, Path]:
    """Run the full extraction pipeline for one atlas across subjects.

    Steps:
      1. Load the atlas LUT (once).
      2. For each subject: validate → transfer → extract → merge with LUT.
      3. Write results according to *output_layout*:
         - ``"flat"``  (default) – all subjects concatenated into a single TSV.
         - ``"bids"``  – per-subject CSV files in a BIDS-like directory tree.

    Parameters
    ----------
    jobs:
        Number of parallel worker threads. ``1`` (default) runs sequentially.
        Values > 1 use ``ThreadPoolExecutor`` to process subjects concurrently.

    Returns a dict with keys ``"output"`` and/or ``"failures"`` mapping to Paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load LUT once — it defines the output schema
    lut = _load_lut(atlas, env)

    # Get handler for the atlas format
    handler = get_handler(atlas.format)
    if hasattr(handler, "registration_backend"):
        handler.registration_backend = registration_backend

    # Choose writer strategy
    if output_layout == "bids":
        writer: OutputWriter = BidsWriter(output_dir, handler=handler, env=env)
    else:
        writer = FlatWriter(output_dir, atlas, handler=handler, env=env)

    failed_subjects: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task(f"Extracting {atlas.name}", total=len(subjects))

        if jobs == 1:
            # Sequential path (original behaviour)
            for subject_id in subjects:
                progress.update(task, description=f"{atlas.name} → {subject_id}")
                try:
                    result_df, commands_run = _process_one_subject(
                        subject_id, atlas, env, handler, lut, force
                    )
                    writer.write_subject(result_df, subject_id, atlas, commands_run=commands_run)
                except ValueError as e:
                    logger.warning(f"Subject {subject_id} skipped: {e}")
                    failed_subjects.append((subject_id, str(e)))
                except Exception as e:
                    logger.error(f"Failed for {subject_id}: {e}")
                    failed_subjects.append((subject_id, str(e)))
                progress.advance(task)

        else:
            # Parallel path
            progress.update(task, description=f"{atlas.name} (workers={jobs})")
            with ThreadPoolExecutor(max_workers=jobs) as executor:
                future_to_subject = {
                    executor.submit(
                        _process_one_subject, sid, atlas, env, handler, lut, force
                    ): sid
                    for sid in subjects
                }
                for future in as_completed(future_to_subject):
                    sid = future_to_subject[future]
                    try:
                        result_df, commands_run = future.result()
                        writer.write_subject(
                            result_df, sid, atlas, commands_run=commands_run
                        )
                    except ValueError as e:
                        logger.warning(f"Subject {sid} skipped: {e}")
                        failed_subjects.append((sid, str(e)))
                    except Exception as e:
                        logger.error(f"Failed for {sid}: {e}")
                        failed_subjects.append((sid, str(e)))
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
    from .extract import _parse_header_measures, _parse_segstats_file, _run_segstats

    seg_path = transfer_result.paths["volume"]
    stats_path = _run_segstats(
        subject=subject,
        env=env,
        seg_path=seg_path,
        atlas_name=atlas.name,
        ctab_path=ctab_path,
        force=force,
        command_log=transfer_result.commands_run,
    )
    header_measures = _parse_header_measures(stats_path)
    df = _parse_segstats_file(stats_path)
    return df, header_measures
