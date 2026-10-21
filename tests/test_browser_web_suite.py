"""
Automated tests for browser-first Streamlit web application and core media services.
Validates imports, platform classification, Instagram collection and individual Reel flows,
queue management and duplicate prevention, download success/failure handling, and security sanitization.
All external network interactions are mocked.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.validators import (
    is_valid_url,
    detect_platform,
    classify_instagram_url,
    is_instagram_collection_url,
    InstagramURLType,
    sanitize_filename,
)
from src.extractor import extract_media_info, looks_like_collection, channel_tab_urls
from src.media import MediaMetadata, PlaylistItem, JobStatus, AdvancedOptions
from src.queue import QueueManager
from src.downloader import download_media, build_output_template, locate_output_file
from src.instagram_scraper import InstagramReelsScraper, extract_instagram_reels_from_profile


# ==============================================================================
# 1. Streamlit Application Startup & Imports
# ==============================================================================

def test_streamlit_app_and_core_modules_import():
    """Verifies that app.py and all essential web modules import cleanly."""
    import app
    assert hasattr(app, "render_hero")
    assert hasattr(app, "inject_custom_css")

    from src import downloader, extractor, filesystem, formats, history, queue, system, ui, validators
    assert downloader is not None
    assert extractor is not None
    assert queue is not None


# ==============================================================================
# 2. URL Validation & Multi-Platform Detection
# ==============================================================================

@pytest.mark.parametrize("url,expected_valid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
    ("https://youtu.be/dQw4w9WgXcQ", True),
    ("https://www.tiktok.com/@user/video/123456789", True),
    ("https://www.instagram.com/reel/C123456789/", True),
    ("https://www.instagram.com/p/C123456789/", True),
    ("https://www.instagram.com/username/", True),
    ("https://www.instagram.com/username/reels/", True),
    ("https://www.facebook.com/watch/?v=123456789", True),
    ("https://x.com/user/status/123456789", True),
    ("ftp://invalid.com", False),
    ("not-a-url", False),
    ("", False),
    (None, False),
])
def test_url_validation(url, expected_valid):
    assert is_valid_url(url) is expected_valid


@pytest.mark.parametrize("url,expected_platform", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube"),
    ("https://youtu.be/dQw4w9WgXcQ", "YouTube"),
    ("https://www.tiktok.com/@user/video/123456789", "TikTok"),
    ("https://www.facebook.com/watch/?v=123456789", "Facebook"),
    ("https://www.facebook.com/reel/123456789", "Facebook"),
    ("https://twitter.com/user/status/123", "Twitter / X"),
    ("https://x.com/user/status/123", "Twitter / X"),
    ("https://vimeo.com/123456789", "Vimeo"),
    ("https://www.instagram.com/reel/C123456789/", "Instagram Reel"),
    ("https://www.instagram.com/p/C123456789/", "Instagram Post"),
    ("https://www.instagram.com/username/", "Instagram Profile"),
    ("https://www.instagram.com/username/reels/", "Instagram Reels"),
])
def test_platform_detection(url, expected_platform):
    assert detect_platform(url) == expected_platform


# ==============================================================================
# 3. Instagram Classification & Collection Handling
# ==============================================================================

def test_instagram_classification_types():
    assert classify_instagram_url("https://www.instagram.com/cristiano/") == InstagramURLType.PROFILE
    assert classify_instagram_url("https://www.instagram.com/cristiano/reels/") == InstagramURLType.REELS
    assert classify_instagram_url("https://www.instagram.com/reel/C123abc/") == InstagramURLType.REEL
    assert classify_instagram_url("https://www.instagram.com/p/C123abc/") == InstagramURLType.POST
    assert classify_instagram_url("https://www.instagram.com/tv/C123abc/") == InstagramURLType.TV


def test_instagram_collection_identification():
    assert is_instagram_collection_url("https://www.instagram.com/username/") is True
    assert is_instagram_collection_url("https://www.instagram.com/username/reels/") is True
    # Individual Reels and Posts must NEVER be identified as collections
    assert is_instagram_collection_url("https://www.instagram.com/reel/C123abc/") is False
    assert is_instagram_collection_url("https://www.instagram.com/p/C123abc/") is False


def test_instagram_empty_result_handling(monkeypatch):
    """
    When Instagram blocks anonymous access or discovers no Reels,
    extract_media_info must return an empty playlist structure rather than crashing,
    and must NEVER return a single video object with the profile URL.
    """
    # Mock scraper to simulate anonymous access blocked
    class MockBlockedScraper:
        def __init__(self):
            self.last_error = "Login required"
        def extract_reel_urls(self, url, max_reels=50):
            return []

    monkeypatch.setattr("src.instagram_scraper.InstagramReelsScraper", MockBlockedScraper)
    monkeypatch.setattr("src.extractor._extract_instagram_reels", lambda *a, **kw: None)

    meta = extract_media_info("https://www.instagram.com/restricted_user/reels/")
    assert meta.is_playlist is True
    assert meta.playlist_items == []
    assert meta.playlist_count == 0
    assert "restricted_user" in meta.title or "Instagram" in meta.title


def test_instagram_discovery_with_accessible_reels(monkeypatch):
    """
    When Instagram Reels are discovered, each reel must be populated as an individual PlaylistItem.
    """
    discovered = [
        "https://www.instagram.com/reel/ReelA123/",
        "https://www.instagram.com/reel/ReelB456/",
    ]

    class MockWorkingScraper:
        def __init__(self):
            self.last_error = None
        def extract_reel_urls(self, url, max_reels=50):
            return discovered

    monkeypatch.setattr("src.extractor._extract_instagram_reels", lambda *a, **kw: None)
    monkeypatch.setattr("src.extractor.InstagramReelsScraper", MockWorkingScraper)
    monkeypatch.setattr("src.instagram_scraper.InstagramReelsScraper", MockWorkingScraper)

    meta = extract_media_info("https://www.instagram.com/sample_creator/reels/")
    assert meta.is_playlist is True
    assert meta.playlist_count == 2
    assert [p.url for p in meta.playlist_items] == discovered


# ==============================================================================
# 4. Queue Management & Duplicate Prevention
# ==============================================================================

def test_queue_creation_and_status(monkeypatch):
    qm = QueueManager(max_concurrency=2)
    monkeypatch.setattr("src.queue.download_media", lambda *a, **kw: (True, "video.mp4"))
    monkeypatch.setattr("src.queue.add_history_record", lambda **kw: None)

    job = qm.add_job("https://example.com/v1", "Test Job")
    assert job.status in (JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.COMPLETED)
    assert len(qm.get_all_jobs()) == 1


def test_queue_rejects_instagram_collection():
    qm = QueueManager(max_concurrency=2)
    with pytest.raises(ValueError) as excinfo:
        qm.add_job("https://www.instagram.com/username/reels/", "Profile Collection")
    assert "collection" in str(excinfo.value).lower()


def test_queue_duplicate_prevention(monkeypatch):
    import threading
    pause = threading.Event()

    def slow_dl(*a, **kw):
        pause.wait(timeout=2.0)
        return True, "test.mp4"

    monkeypatch.setattr("src.queue.download_media", slow_dl)
    monkeypatch.setattr("src.queue.add_history_record", lambda **kw: None)

    qm = QueueManager(max_concurrency=2)
    job1 = qm.add_job("https://example.com/unique_vid", "Vid 1")
    job2 = qm.add_job("https://example.com/unique_vid", "Vid 1 Duplicate")

    pause.set()
    assert job1.job_id == job2.job_id
    assert len(qm.get_all_jobs()) == 1


# ==============================================================================
# 5. Download Success & Positive File Verification
# ==============================================================================

def test_download_media_blocks_instagram_collection():
    ok, err = download_media("https://www.instagram.com/username/", "Video", "Best Available", "downloads")
    assert ok is False
    assert "cannot be downloaded directly as a single video" in err


def test_locate_output_file_positive_verification(tmp_path):
    out_dir = str(tmp_path)

    # Empty 0-byte file must be rejected
    zero_byte = os.path.join(out_dir, "corrupt.mp4")
    with open(zero_byte, "wb"):
        pass
    assert locate_output_file(out_dir, zero_byte) is None

    # Positive size valid file must be accepted
    real_video = os.path.join(out_dir, "real_video.mp4")
    with open(real_video, "wb") as f:
        f.write(b"SAMPLE_VIDEO_DATA_HEADER" * 100)
    assert locate_output_file(out_dir, real_video) == real_video


# ==============================================================================
# 6. Filename Sanitization & Path Security
# ==============================================================================

@pytest.mark.parametrize("raw_name,expected_clean", [
    ("video?title:with/illegal*chars", "video_title_with_illegal_chars"),
    ("hello世界_123", "hello世界_123"),
    ("", "video"),
    (None, "video"),
    ("   ", "video"),
])
def test_filename_sanitization(raw_name, expected_clean):
    assert sanitize_filename(raw_name) == expected_clean


def test_output_template_prevents_traversal():
    opts = AdvancedOptions(custom_filename="../../etc/passwd")
    tmpl = build_output_template(opts)
    assert ".." not in tmpl
    assert "/" not in tmpl
    assert tmpl.endswith(".%(ext)s")
