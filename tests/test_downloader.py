import os

import pytest

from src.downloader import (
    DEFAULT_OUTPUT_TEMPLATE,
    FFMPEG_MISSING_MESSAGE,
    build_output_template,
    format_selector_needs_merge,
    locate_output_file,
    should_retry_client,
)
from src.filesystem import cleanup_stream_artifacts, is_stream_artifact
from src.media import AdvancedOptions


# --- is_stream_artifact -------------------------------------------------

@pytest.mark.parametrize("name", [
    "Tehzeeb Fana.f251.webm",
    "Tehzeeb Fana.f399.mp4",
    "Tehzeeb Fana.temp.mp4",
    "song.temp.m4a",
])
def test_stream_artifacts_are_detected(name):
    assert is_stream_artifact(name) is True


@pytest.mark.parametrize("name", [
    "Tehzeeb Fana.mp4",
    "Tehzeeb Fana.webm",
    "Tehzeeb Fana.f251.mp4.partial",
    "my.folder.video.mp4",
])
def test_final_outputs_are_not_artifacts(name):
    assert is_stream_artifact(name) is False


# --- cleanup_stream_artifacts ------------------------------------------

def test_cleanup_removes_orphan_streams_but_keeps_final_file(tmp_path):
    final = tmp_path / "Video.mp4"
    final.write_bytes(b"merged")
    orphans = [tmp_path / "Video.f251.webm", tmp_path / "Video.f399.mp4", tmp_path / "Video.temp.mp4"]
    for orphan in orphans:
        orphan.write_bytes(b"partial")

    removed = cleanup_stream_artifacts(str(tmp_path))

    assert sorted(removed) == sorted(str(p) for p in orphans)
    assert final.exists()


def test_cleanup_honours_keep_list(tmp_path):
    kept = tmp_path / "Video.f399.mp4"
    kept.write_bytes(b"x")
    other = tmp_path / "Video.f251.webm"
    other.write_bytes(b"y")

    removed = cleanup_stream_artifacts(str(tmp_path), keep={str(kept)})

    assert removed == [str(other)]
    assert kept.exists()


def test_cleanup_on_missing_directory_is_safe(tmp_path):
    assert cleanup_stream_artifacts(str(tmp_path / "nope")) == []


# --- build_output_template ---------------------------------------------

def test_default_template_used_when_empty():
    assert build_output_template(AdvancedOptions()) == DEFAULT_OUTPUT_TEMPLATE


def test_custom_filename_is_sanitized():
    opts = AdvancedOptions(custom_filename='my/video:name*')
    result = build_output_template(opts)
    assert result.endswith(".%(ext)s")
    assert not any(c in result for c in '\\/:*?"<>|')
    assert ".." not in result


def test_template_cannot_escape_output_directory():
    opts = AdvancedOptions(filename_template="../../escape/%(title)s.%(ext)s")
    template = build_output_template(opts)
    assert ".." not in template
    assert not template.startswith("/")
    # os.path.join must keep the output dir as the parent
    joined = os.path.join("/downloads", template)
    assert os.path.abspath(joined).startswith(os.path.abspath("/downloads"))


def test_legacy_template_slash_fallback_becomes_underscore():
    opts = AdvancedOptions(filename_template="%(channel,uploader&{}/|)s%(title)s.%(ext)s")
    assert "&{}_|" in build_output_template(opts)


def test_extension_suffix_is_added_once():
    opts = AdvancedOptions(filename_template="%(title)s")
    assert build_output_template(opts) == "%(title)s.%(ext)s"
    opts2 = AdvancedOptions(filename_template="%(title)s.%(ext)s")
    assert build_output_template(opts2) == "%(title)s.%(ext)s"


# --- format_selector_needs_merge ---------------------------------------

@pytest.mark.parametrize("selector,expected", [
    ("bestvideo+bestaudio/best", True),
    ("bestvideo[height<=1080]+bestaudio/best", True),
    ("137+140", True),
    ("best", False),
    ("18", False),
])
def test_format_selector_needs_merge(selector, expected):
    assert format_selector_needs_merge(selector) is expected


# --- locate_output_file -------------------------------------------------

def test_locate_output_file_ignores_intermediates(tmp_path):
    (tmp_path / "Video.f399.mp4").write_bytes(b"v")
    before = set(os.listdir(tmp_path))

    hint = str(tmp_path / "Video.mp4")
    assert locate_output_file(str(tmp_path), hint, before) is None


def test_locate_output_file_returns_hint(tmp_path):
    final = tmp_path / "Video.mp4"
    final.write_bytes(b"m")
    assert locate_output_file(str(tmp_path), str(final), set()) == str(final)


def test_locate_output_file_picks_newest_non_artifact(tmp_path):
    (tmp_path / "A.mp4").write_bytes(b"a")
    (tmp_path / "B.f137.mp4").write_bytes(b"b")
    before = set(os.listdir(tmp_path))
    (tmp_path / "B.mp4").write_bytes(b"c")

    found = locate_output_file(str(tmp_path), None, before)
    assert os.path.basename(found) == "B.mp4"


# --- should_retry_client ------------------------------------------------

@pytest.mark.parametrize("msg", [
    "Sign in to confirm you're not a bot",
    "This video requires a PO token",
    "HTTP Error 403: Forbidden",
    "Requested format is not available",
])
def test_should_retry_client_on_client_errors(msg):
    assert should_retry_client(msg) is True


@pytest.mark.parametrize("msg", [
    "Video unavailable",
    "This video has been removed by the uploader",
    "Private video. Sign in if you've been granted access",
    "This account has been terminated",
])
def test_should_not_retry_client_on_fatal_errors(msg):
    assert should_retry_client(msg) is False


def test_ffmpeg_message_mentions_install_hint():
    assert "ffmpeg" in FFMPEG_MISSING_MESSAGE.lower()
    assert "merge" in FFMPEG_MISSING_MESSAGE.lower()