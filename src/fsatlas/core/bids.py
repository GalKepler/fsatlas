"""BIDS-like output path construction for fsatlas."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# BIDS entity label: alphanumeric only
_BIDS_LABEL_RE = re.compile(r"^[a-zA-Z0-9]+$")

# Pattern to extract sub-/ses- entities from a FreeSurfer directory name
# _BIDS_ID_RE = re.compile(
#     r"^(?P<sub>sub-[a-zA-Z0-9]+)(?:_(?P<ses>ses-[a-zA-Z0-9]+))?(?:_.*)?$"
# )


@dataclass
class BidsEntities:
    sub: str         # label only, without "sub-" prefix; e.g. "01"
    ses: str | None  # label only, without "ses-" prefix; e.g. "baseline" or None


def parse_bids_entities(subject_id: str) -> BidsEntities:
    """Parse BIDS sub-/ses- entities from a FreeSurfer subject directory name.

    Examples
    --------
    - ``'sub-01_ses-baseline'`` → ``BidsEntities("01", "baseline")``
    - ``'sub-01'``             → ``BidsEntities("01", None)``
    - ``'patient123'``         → ``BidsEntities("patient123", None)``  (with warning)
    """
    # extract subject code without using regex
    if "sub-" in subject_id:
        sub_label = subject_id.split("sub-")[1].split("_")[0]
        ses_label = None
        if "ses-" in subject_id:
            ses_label = subject_id.split("ses-")[1].split(".")[0]
            if ".long." not in subject_id:
                ses_label += ".cross"
        return BidsEntities(sub=sub_label, ses=ses_label)
    else:
        sub_label = subject_id
    

    # m = _BIDS_ID_RE.match(subject_id)
    # if m:
    #     sub_label = m.group("sub")[4:]   # strip "sub-"
    #     ses_part = m.group("ses")
    #     ses_label = ses_part[4:] if ses_part else None  # strip "ses-"
    #     # for longitudinal data, there's a .long.<subject_id> suffix. Append it to the session label to ensure uniqueness.
    #     if ".long." in subject_id and ses_label is not None:
    #         ses_label = f"{ses_label}.long"
    #     return BidsEntities(sub=sub_label, ses=ses_label)


    # Not a BIDS-formatted ID — sanitize and wrap
    safe = re.sub(r"[^a-zA-Z0-9]", "", subject_id)
    if not safe:
        safe = "unknown"
    logger.warning(
        f"Subject ID '{subject_id}' does not follow BIDS naming (sub-<label>[_ses-<label>]). "
        f"Using sub-{safe} in output paths."
    )
    return BidsEntities(sub=safe, ses=None)


def build_bids_path(
    output_dir: Path,
    entities: BidsEntities,
    atlas_bids_name: str,
    structure: str,
) -> Path:
    """Construct the full BIDS-like output CSV path.

    With session::

        output_dir/sub-{sub}/ses-{ses}/anat/
            sub-{sub}_ses-{ses}_atlas-{name}_structure-{structure}.csv

    Without session::

        output_dir/sub-{sub}/anat/atlas-{name}/
            sub-{sub}_atlas-{name}_structure-{structure}.csv
    """
    sub_dir = output_dir / f"sub-{entities.sub}"

    if entities.ses is not None:
        anat_dir = sub_dir / f"ses-{entities.ses}" / "anat" / f"atlas-{atlas_bids_name}"
        fname_parts = [
            f"sub-{entities.sub}",
            f"ses-{entities.ses}",
            f"atlas-{atlas_bids_name}",
            f"structure-{structure}",
        ]
    else:
        anat_dir = sub_dir / "anat" / f"atlas-{atlas_bids_name}"
        fname_parts = [
            f"sub-{entities.sub}",
            f"atlas-{atlas_bids_name}",
            f"structure-{structure}",
        ]

    filename = "_".join(fname_parts) + ".csv"
    return anat_dir / filename
