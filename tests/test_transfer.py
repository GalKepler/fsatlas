"""Tests for fsatlas.core.transfer — thin dispatcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fsatlas.core.transfer import transfer_atlas


class TestTransferAtlas:
    def test_dispatches_to_correct_handler(self):
        atlas = MagicMock()
        atlas.format = "annot"
        subject = MagicMock()
        env = MagicMock()

        mock_handler = MagicMock()
        mock_result = MagicMock()
        mock_handler.transfer.return_value = mock_result

        # get_handler is imported inside transfer_atlas, so patch at formats module
        with patch("fsatlas.core.formats.get_handler", return_value=mock_handler) as mock_get:
            result = transfer_atlas(atlas, subject, env, overwrite=False)

        mock_get.assert_called_once_with("annot")
        mock_handler.transfer.assert_called_once_with(atlas, subject, env, False)
        assert result is mock_result

    def test_unknown_format_raises(self):
        atlas = MagicMock()
        atlas.format = "unknown_format"
        subject = MagicMock()
        env = MagicMock()
        with pytest.raises(ValueError, match="Unknown atlas format"):
            transfer_atlas(atlas, subject, env)

    def test_overwrite_passed_through(self):
        atlas = MagicMock()
        atlas.format = "nifti"
        subject = MagicMock()
        env = MagicMock()
        mock_handler = MagicMock()
        mock_handler.transfer.return_value = MagicMock()
        with patch("fsatlas.core.formats.get_handler", return_value=mock_handler):
            transfer_atlas(atlas, subject, env, overwrite=True)
        mock_handler.transfer.assert_called_once_with(atlas, subject, env, True)
