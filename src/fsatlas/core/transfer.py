"""Atlas transfer: thin dispatcher to the appropriate format handler.

The actual transfer logic lives in ``formats.py``.
"""

from __future__ import annotations

import logging

from ..atlases.registry import AnyAtlasSpec
from .environment import FreeSurferEnv, SubjectPaths

logger = logging.getLogger(__name__)


def transfer_atlas(
    atlas: AnyAtlasSpec,
    subject: SubjectPaths,
    env: FreeSurferEnv,
    overwrite: bool = False,
):
    """Transfer any atlas to subject space via the appropriate format handler.

    Returns a ``TransferResult`` (from ``formats.py``).
    """
    from .formats import get_handler
    handler = get_handler(atlas.format)
    return handler.transfer(atlas, subject, env, overwrite)
