"""
Tests for Phase 6 FFmpeg executable verification, positive file size checks,
and application integrity.
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from src.system import _verify_executable, resolve_ffmpeg_path, resolve_ffprobe_path, get_system_status
from src.downloader import locate_output_file
from src.filesystem import is_stream_artifact


def test_verify_executable_on_invalid_file(tmp_path):
    # Non-existent path
    assert not _verify_executable(str(tmp_path / "nonexistent_binary"))

    # Empty file
    empty_file = tmp_path / "fake_ffmpeg.exe"
    empty_file.write_text("not an executable")
    assert not _verify_executable(str(empty_file))


def test_locate_output_file_rejects_empty_file(tmp_path):
    out_dir = str(tmp_path)
    empty_video = os.path.join(out_dir, "empty_video.mp4")
    with open(empty_video, "wb") as f:
        pass  # 0 bytes

    # 0-byte file should NOT be accepted
    assert locate_output_file(out_dir, empty_video) is None

    # Positive size file SHOULD be accepted
    valid_video = os.path.join(out_dir, "valid_video.mp4")
    with open(valid_video, "wb") as f:
        f.write(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 1024)

    assert locate_output_file(out_dir, valid_video) == valid_video


def test_locate_output_file_rejects_stream_artifacts(tmp_path):
    out_dir = str(tmp_path)
    artifact = os.path.join(out_dir, "video.f251.webm")
    with open(artifact, "wb") as f:
        f.write(b"data" * 100)

    assert is_stream_artifact(artifact)
    assert locate_output_file(out_dir, artifact) is None


def test_system_status_structure():
    status = get_system_status()
    assert "yt_dlp" in status
    assert "ffmpeg" in status
    assert "ffprobe" in status
    assert "network" in status
    assert "database" in status

    db = status["database"]
    assert "status" in db
    assert "connected" in db
    assert "label" in db


def test_streamlit_app_imports_cleanly():
    # Verify app.py can be imported without crashing
    import app
    assert hasattr(app, "render_hero")
