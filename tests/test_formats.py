import pytest
from src.formats import filter_available_resolutions, build_ytdlp_format_string, get_resolution_height_target


def test_filter_available_resolutions():
    formats = [
        {"height": 2160, "format_id": "1"},
        {"height": 1080, "format_id": "2"},
        {"height": 720, "format_id": "3"},
    ]
    res = filter_available_resolutions(formats)
    assert "Best Available" in res
    assert "4K (2160p)" in res
    assert "1080p" in res
    assert "720p" in res
    assert "480p" not in res


def test_build_ytdlp_format_string():
    assert build_ytdlp_format_string("Video", "Best Available") == "bestvideo+bestaudio/best"
    assert "1080" in build_ytdlp_format_string("Video", "1080p")
    assert build_ytdlp_format_string("Audio", "MP3") == "bestaudio/best"
    assert build_ytdlp_format_string("Video", "1080p", raw_format_id="137+140") == "137+140"


def test_get_resolution_height_target():
    assert get_resolution_height_target("1080p") == 1080
    assert get_resolution_height_target("4K (2160p)") == 2160
    assert get_resolution_height_target("Best Available") is None
