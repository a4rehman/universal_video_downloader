import pytest
from src.system import get_system_status, get_ytdlp_version, check_ffmpeg


def test_get_system_status():
    status = get_system_status()
    assert "yt_dlp" in status
    assert "ffmpeg" in status
    assert "ffprobe" in status
    assert "network" in status
    assert status["yt_dlp"]["status"] is True


def test_get_ytdlp_version():
    ver = get_ytdlp_version()
    assert ver != "Unknown"
