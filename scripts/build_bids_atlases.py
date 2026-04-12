#!/usr/bin/env python3
"""Build / populate the BIDS-atlas directory.

This script is the authoritative way to populate the BIDS-atlas directory used
by fsatlas.  It is executed during Docker / Apptainer image builds (so atlases
are baked into the image), and can be run manually by users who install fsatlas
outside a container.

Usage
-----
    python scripts/build_bids_atlases.py --output-dir /opt/fsatlas/atlases
    python scripts/build_bids_atlases.py --output-dir ./my-atlases --atlas schaefer100-7
    python scripts/build_bids_atlases.py --output-dir /opt/fsatlas/atlases --force

The same logic is available via ``fsatlas populate`` once the package is installed.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Allow running as a standalone script without installing the package
# by inserting the src/ directory into the path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from fsatlas.atlases.populate import populate_all  # noqa: E402


def _find_freesurfer_home() -> Path | None:
    fsh = os.environ.get("FREESURFER_HOME")
    if fsh:
        p = Path(fsh)
        if p.is_dir():
            return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate the fsatlas BIDS-atlas directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output-dir", "-o",
        required=True,
        type=Path,
        help="Destination BIDS-atlas directory.",
    )
    parser.add_argument(
        "--atlas", "-a",
        action="append",
        dest="atlases",
        default=None,
        metavar="NAME",
        help="Atlas name to populate (repeat for multiple). Default: all.",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Re-download / re-generate even if files already exist.",
    )
    parser.add_argument(
        "--freesurfer-home",
        type=Path,
        default=None,
        help=(
            "Path to FREESURFER_HOME. Required for built-in atlases (dkt, desikan, "
            "destrieux, aseg). Defaults to $FREESURFER_HOME."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    freesurfer_home = args.freesurfer_home or _find_freesurfer_home()
    if freesurfer_home is None:
        logging.warning(
            "FREESURFER_HOME not set — built-in atlas LUTs (dkt, desikan, destrieux, aseg) "
            "will be skipped. Set --freesurfer-home or $FREESURFER_HOME to include them."
        )

    populate_all(
        output_dir=args.output_dir,
        atlas_names=args.atlases,
        force=args.force,
        freesurfer_home=freesurfer_home,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
