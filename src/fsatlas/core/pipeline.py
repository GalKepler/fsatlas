"""Pipeline orchestrator: ties together atlas download, transfer, and extraction."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from ..atlases.registry import AtlasRegistry, AtlasSpec, CustomAtlasSpec
from .environment import FreeSurferEnv
from .extract import extract_cortical_stats, extract_volumetric_stats
from .transfer import transfer_atlas

logger = logging.getLogger(__name__)

AnyAtlasSpec = AtlasSpec | CustomAtlasSpec


def run_extraction(
    atlas: AnyAtlasSpec,
    subjects: list[str],
    env: FreeSurferEnv,
    output_dir: Path,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Run the full extraction pipeline for one atlas across subjects.

    Steps per subject:
      1. Validate subject files
      2. Transfer atlas to subject space (if needed)
      3. Extract stats
      4. Append to results

    Args:
        atlas: Atlas to extract from.
        subjects: List of subject IDs.
        env: FreeSurfer environment.
        output_dir: Where to write output TSVs.
        overwrite: Re-run transfer/extraction even if outputs exist.

    Returns:
        Dict with keys "cortical" and/or "subcortical" mapping to output TSV paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cortical_frames: list[pd.DataFrame] = []
    volumetric_frames: list[pd.DataFrame] = []
    failed_subjects: list[tuple[str, str]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
    ) as progress:
        task = progress.add_task(
            f"Extracting {atlas.name}",
            total=len(subjects),
        )

        for subject_id in subjects:
            progress.update(task, description=f"{atlas.name} → {subject_id}")

            try:
                subject = env.find_subject(subject_id)

                # Validate essential files
                missing = subject.validate()
                if missing:
                    logger.warning(
                        f"Subject {subject_id} missing files: {missing}. Skipping."
                    )
                    failed_subjects.append((subject_id, f"Missing: {missing}"))
                    progress.advance(task)
                    continue

                # Transfer
                logger.info(f"Processing {subject_id} with atlas {atlas.name}")
                transfer_result = transfer_atlas(atlas, subject, env, overwrite)

                # Extract
                if atlas.type == "surface":
                    df = extract_cortical_stats(atlas, subject, env, transfer_result)
                    cortical_frames.append(df)
                elif atlas.type == "volumetric":
                    df = extract_volumetric_stats(atlas, subject, env, transfer_result)
                    volumetric_frames.append(df)

            except Exception as e:
                logger.error(f"Failed for {subject_id}: {e}")
                failed_subjects.append((subject_id, str(e)))

            progress.advance(task)

    # Write outputs
    output_paths: dict[str, Path] = {}

    if cortical_frames:
        cortical_df = pd.concat(cortical_frames, ignore_index=True)
        cortical_path = output_dir / f"{atlas.name}_cortical.tsv"
        cortical_df.to_csv(cortical_path, sep="\t", index=False)
        logger.info(f"Cortical stats written to {cortical_path} ({len(cortical_df)} rows)")
        output_paths["cortical"] = cortical_path

    if volumetric_frames:
        volumetric_df = pd.concat(volumetric_frames, ignore_index=True)
        volumetric_path = output_dir / f"{atlas.name}_subcortical.tsv"
        volumetric_df.to_csv(volumetric_path, sep="\t", index=False)
        logger.info(
            f"Subcortical stats written to {volumetric_path} ({len(volumetric_df)} rows)"
        )
        output_paths["subcortical"] = volumetric_path

    # Report failures
    if failed_subjects:
        logger.warning(f"{len(failed_subjects)} subject(s) failed:")
        for sid, reason in failed_subjects:
            logger.warning(f"  {sid}: {reason}")

        # Write failures log
        fail_path = output_dir / f"{atlas.name}_failures.tsv"
        pd.DataFrame(failed_subjects, columns=["subject_id", "reason"]).to_csv(
            fail_path, sep="\t", index=False
        )
        output_paths["failures"] = fail_path

    return output_paths
