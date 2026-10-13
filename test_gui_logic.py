"""Tests for universal_video_downloader pure logic (no GUI instantiated)."""

import os
import sys
import io

sys.path.insert(0, os.path.dirname(__file__))

from app_gui import (
    sanitize,
    DownloadItem,
    DownloadApp,
    json_safeload,
    json_dumps,
    should_retry_client,
    resolve_ffmpeg_location,
    is_stream_artifact,
    cleanup_stream_artifacts,
    is_collection_url,
    _entry_url,
    _youtube_handle,
    FFMPEG_MISSING_MESSAGE,
    DEFAULT_OUTTMPL,
)


class DummyConfig:
    def get(self, key, default=None):
        cfg = {"download_path": os.path.expanduser("~/Downloads"), "playlist": True}
        return cfg.get(key, default)


class DummyApp:
    config = DummyConfig()
    cookie_locked = type("L", (), {"is_set": lambda self: False})()


def test_sanitize_removes_illegal_chars():
    assert ":" not in sanitize("a:b*c?d")
    assert "/" not in sanitize("dir/file")
    assert sanitize("video") == "video"


def test_sanitize_empty_falls_back():
    assert sanitize("") == "video"
    assert sanitize(None) == "video"


def test_fmt_size_units():
    item = DownloadItem(DummyApp(), "http://x", "Video", None)
    assert item._fmt_size(0) == "0.0 B"
    assert "KB" in item._fmt_size(1500)
    assert "MB" in item._fmt_size(5 * 1024 * 1024)
    assert "GB" in item._fmt_size(2 * 1024**3)


def test_shade_darkens_color():
    assert DownloadApp.shade(None, "#ffffff") == "#bfbfbf"  # 255 * 0.75 = 191
    assert DownloadApp.shade(None, "##invalid") == "#334155"  # fallback on bad input


def test_json_safeload_valid():
    assert json_safeload('{"a": 1}') == {"a": 1}


def test_json_safeload_invalid():
    assert json_safeload("not json {{{") == {}


def test_json_dumps_write():
    fh = io.StringIO()
    json_dumps({"x": 2}, fh)
    assert "x" in fh.getvalue()


def test_download_item_build_opts_video():
    item = DownloadItem(DummyApp(), "http://x", "Video", "bestvideo+bestaudio/best")
    opts = item.build_opts()
    assert opts["format"] == "bestvideo+bestaudio/best"
    assert opts["merge_output_format"] == "mp4"


def test_download_item_build_opts_audio():
    item = DownloadItem(DummyApp(), "http://x", "Audio", "192 kbps")
    opts = item.build_opts()
    assert opts["format"] == "bestaudio/best"
    assert opts["postprocessors"][0]["preferredquality"] == "192"


# --- stream merging ----------------------------------------------------

def test_ffmpeg_location_is_resolved():
    """ffmpeg must be findable, else video/audio stay as separate files."""
    location = resolve_ffmpeg_location()
    assert isinstance(location, str)
    assert os.path.exists(location)


def test_build_opts_wires_ffmpeg_location():
    item = DownloadItem(DummyApp(), "http://x", "Video", "bestvideo+bestaudio/best")
    opts = item.build_opts()
    assert "ffmpeg_location" in opts


def test_build_opts_uses_sanitizing_outtmpl():
    item = DownloadItem(DummyApp(), "http://x", "Video", "bestvideo+bestaudio/best")
    opts = item.build_opts()
    assert opts["outtmpl"].endswith(DEFAULT_OUTTMPL)
    assert opts["windowsfilenames"] is True
    assert opts["trim_file_name"] > 0


def test_stream_artifact_detection():
    assert is_stream_artifact("Fana.f251.webm")
    assert is_stream_artifact("Fana.f399.mp4")
    assert is_stream_artifact("Fana.temp.mp4")
    assert not is_stream_artifact("Fana.mp4")
    assert not is_stream_artifact("Fana.webm")


def test_cleanup_stream_artifacts_keeps_final(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        final = os.path.join(d, "Fana.mp4")
        with open(final, "wb") as fh:
            fh.write(b"merged")
        orphans = [os.path.join(d, "Fana.f251.webm"), os.path.join(d, "Fana.f399.mp4")]
        for o in orphans:
            with open(o, "wb") as fh:
                fh.write(b"partial")
        removed = cleanup_stream_artifacts(d)
        assert sorted(removed) == sorted(orphans)
        assert os.path.exists(final)


def test_resolve_output_file_skips_intermediates(tmp_path=None):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "Fana.f399.mp4"), "wb") as fh:
            fh.write(b"v")
        item = DownloadItem(DummyApp(), "http://x", "Video", None)
        assert item._resolve_output_file(d, os.path.join(d, "Fana.mp4")) is None


# --- collections (channel / playlist / shorts) -------------------------

def test_is_collection_url():
    assert is_collection_url("https://www.youtube.com/@chan/shorts")
    assert is_collection_url("https://www.youtube.com/playlist?list=PL1")
    assert is_collection_url("https://www.youtube.com/watch?v=abc&list=PL1")
    assert not is_collection_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not is_collection_url("https://youtu.be/dQw4w9WgXcQ")
    # Instagram collection URLs
    assert is_collection_url("https://www.instagram.com/username/")
    assert is_collection_url("https://www.instagram.com/username/reels/")
    assert not is_collection_url("https://www.instagram.com/reel/ABC123/")
    assert not is_collection_url("https://www.instagram.com/p/ABC123/")


def test_entry_url_from_flat_extraction():
    assert _entry_url({"id": "dQw4w9WgXcQ", "url": "dQw4w9WgXcQ"}, "http://x") \
        == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_youtube_handle_extraction():
    assert _youtube_handle("https://www.youtube.com/@tehzeeb") == "tehzeeb"
    assert _youtube_handle("https://www.youtube.com/watch?v=x") is None


def test_noplaylist_only_for_collection_items():
    single = DownloadItem(DummyApp(), "http://x/watch", "Video", "bestvideo+bestaudio/best")
    assert single.build_opts()["noplaylist"] is True

    collection = DownloadItem(DummyApp(), "http://x/@chan", "Video",
                              "bestvideo+bestaudio/best", allow_playlist=True)
    assert collection.build_opts()["noplaylist"] is False


# --- error triage ------------------------------------------------------

def test_should_retry_client_separates_fatal_errors():
    assert should_retry_client("Sign in to confirm you're not a bot")
    assert should_retry_client("This content requires a PO token")
    assert should_retry_client("HTTP Error 403: Forbidden")
    assert not should_retry_client("Video unavailable")
    assert not should_retry_client("This video has been removed by the uploader")


def test_ffmpeg_message_is_actionable():
    assert "ffmpeg" in FFMPEG_MISSING_MESSAGE.lower()
    assert "merge" in FFMPEG_MISSING_MESSAGE.lower()


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL OMNISTREAM TESTS PASSED")