import os

import pytest

from src.extractor import (
    looks_like_collection,
    normalize_entry_url,
    is_youtube_id,
    _youtube_handle,
    _friendly_error,
)
from src.validators import classify_instagram_url, is_instagram_collection_url, InstagramURLType
from src.system import (
    get_ffmpeg_location,
    has_ffmpeg,
    resolve_ffmpeg_path,
    get_system_status,
)


# --- is_youtube_id ------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("dQw4w9WgXcQ", True),
    ("abc", False),
    ("waytoolongvideoid", False),
    (None, False),
])
def test_is_youtube_id(value, expected):
    assert is_youtube_id(value) is expected


# --- normalize_entry_url ------------------------------------------------

def test_bare_video_id_becomes_watch_url():
    """Flat extraction yields only an id; yt-dlp cannot download that as a URL."""
    url = normalize_entry_url({"id": "dQw4w9WgXcQ", "url": "dQw4w9WgXcQ"}, "https://x/")
    assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_webpage_url_is_preferred():
    entry = {"id": "dQw4w9WgXcQ", "webpage_url": "https://youtu.be/dQw4w9WgXcQ"}
    assert normalize_entry_url(entry, "https://x/") == "https://youtu.be/dQw4w9WgXcQ"


def test_absolute_entry_url_is_kept():
    entry = {"url": "https://vimeo.com/12345"}
    assert normalize_entry_url(entry, "https://x/") == "https://vimeo.com/12345"


def test_relative_entry_url_falls_back_to_parent():
    assert normalize_entry_url({"url": "12345"}, "https://vimeo.com/ch") == "https://vimeo.com/ch"


def test_empty_entry_falls_back_to_parent():
    assert normalize_entry_url({}, "https://x/") == "https://x/"


# --- looks_like_collection ---------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/@TehzeebLibasOfficial/shorts", True),
    ("https://www.youtube.com/@TehzeebLibasOfficial", True),
    ("https://www.youtube.com/channel/UC123/videos", True),
    ("https://www.youtube.com/playlist?list=PL123", True),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL9", True),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", False),
    ("https://youtu.be/dQw4w9WgXcQ", False),
])
def test_looks_like_collection_youtube(url, expected):
    assert looks_like_collection(url, "YouTube") is expected


def test_non_youtube_is_never_a_collection():
    assert looks_like_collection("https://tiktok.com/@user/video/123", "TikTok") is False


# --- _youtube_handle ----------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/@TehzeebLibasOfficial", "TehzeebLibasOfficial"),
    ("https://www.youtube.com/@TehzeebLibasOfficial/shorts", "TehzeebLibasOfficial"),
    ("https://www.youtube.com/channel/UCabcdef/videos", "UCabcdef"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", None),
])
def test_youtube_handle(url, expected):
    assert _youtube_handle(url) == expected


# --- ffmpeg resolution --------------------------------------------------

def test_ffmpeg_is_resolvable():
    """A usable ffmpeg is mandatory; imageio-ffmpeg provides the fallback."""
    assert has_ffmpeg() is True
    assert resolve_ffmpeg_path()


def test_ffmpeg_location_shape():
    """
    yt-dlp's ffmpeg_location must be a string. A dict raises TypeError inside
    FFmpegMergerPP, which silently leaves streams unmerged.
    """
    location = get_ffmpeg_location()
    assert isinstance(location, str)
    assert os.path.exists(location)


def test_system_status_reports_ffmpeg_path():
    status = get_system_status()
    assert status["ffmpeg"]["status"] is True
    assert status["ffmpeg"]["path"]
    assert "Not Found" not in status["ffmpeg"]["label"]


# --- error messaging ----------------------------------------------------

def test_tab_404_gives_actionable_message():
    err = Exception("[youtube:tab] @chan/shorts: Unable to download API page: HTTP Error 404")
    msg = _friendly_error(err, "https://www.youtube.com/@chan/shorts")
    assert "404" not in msg.lower().split("browse")[-1][:20]
    assert "cookies" in msg.lower()
    assert "individual video links still download" in msg.lower()


@pytest.mark.parametrize("raw,expected", [
    ("Sign in to confirm you're not a bot", "bot check"),
    ("Unsupported URL: nope", "No downloader is available"),
    ("Private video. Sign in if you've been granted access", "private"),
    ("Video unavailable", "unavailable or was removed"),
])
def test_friendly_error_variants(raw, expected):
    assert expected.lower() in _friendly_error(Exception(raw), "http://x").lower()


def test_friendly_error_falls_back_to_raw_message():
    assert "boom" in _friendly_error(Exception("boom"), "http://x")


# --- Instagram URL Classification ----------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/username/", InstagramURLType.PROFILE),
    ("https://www.instagram.com/username/reels/", InstagramURLType.REELS),
    ("https://www.instagram.com/reel/ABC123/", InstagramURLType.REEL),
    ("https://www.instagram.com/p/ABC123/", InstagramURLType.POST),
    ("https://www.instagram.com/tv/ABC123/", InstagramURLType.TV),
    ("https://instagram.com/username/", InstagramURLType.PROFILE),
    ("https://instagram.com/username/reels/", InstagramURLType.REELS),
])
def test_classify_instagram_url(url, expected):
    assert classify_instagram_url(url) == expected


def test_is_instagram_collection_url():
    assert is_instagram_collection_url("https://www.instagram.com/username/") is True
    assert is_instagram_collection_url("https://www.instagram.com/username/reels/") is True
    assert is_instagram_collection_url("https://www.instagram.com/reel/ABC123/") is False
    assert is_instagram_collection_url("https://www.instagram.com/p/ABC123/") is False
    assert is_instagram_collection_url("https://www.instagram.com/tv/ABC123/") is False


# --- looks_like_collection for Instagram ---------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/username/", True),
    ("https://www.instagram.com/username/reels/", True),
    ("https://www.instagram.com/reel/ABC123/", False),
    ("https://www.instagram.com/p/ABC123/", False),
    ("https://www.instagram.com/tv/ABC123/", False),
])
def test_looks_like_collection_instagram(url, expected):
    # Platform will be "Instagram Profile", "Instagram Reels", etc.
    from src.validators import detect_platform
    platform = detect_platform(url)
    assert looks_like_collection(url, platform) is expected