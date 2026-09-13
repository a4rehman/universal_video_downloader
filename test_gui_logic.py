"""Tests for universal_video_downloader pure logic (no GUI instantiated)."""

import os
import sys
import io

sys.path.insert(0, os.path.dirname(__file__))

from app_gui import sanitize, DownloadItem, DownloadApp, json_safeload, json_dumps


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


if __name__ == "__main__":
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL OMNISTREAM TESTS PASSED")