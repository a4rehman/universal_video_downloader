import pytest
from src.validators import is_valid_url, detect_platform, sanitize_filename, is_safe_path


def test_is_valid_url():
    assert is_valid_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_valid_url("http://example.com/video.mp4") is True
    assert is_valid_url("not a url") is False
    assert is_valid_url("") is False
    assert is_valid_url(None) is False


def test_detect_platform():
    assert detect_platform("https://www.youtube.com/watch?v=123") == "YouTube"
    assert detect_platform("https://youtu.be/123") == "YouTube"
    assert detect_platform("https://www.tiktok.com/@user/video/123") == "TikTok"
    assert detect_platform("https://www.instagram.com/p/123/") == "Instagram Post"
    assert detect_platform("https://www.instagram.com/reel/123/") == "Instagram Reel"
    assert detect_platform("https://www.instagram.com/username/reels/") == "Instagram Reels"
    assert detect_platform("https://www.instagram.com/username/") == "Instagram Profile"
    assert detect_platform("https://x.com/user/status/123") == "Twitter / X"
    assert detect_platform("https://example.com/image.png") == "Direct Image"
    assert detect_platform("https://example.com/page") == "Web Platform"


def test_sanitize_filename():
    assert sanitize_filename("a:b*c?d/e\\f") == "a_b_c_d_e_f"
    assert sanitize_filename("../../etc/passwd") == "etc_passwd"
    assert sanitize_filename("") == "video"
    assert sanitize_filename(None, fallback="default") == "default"


def test_is_safe_path():
    base = "/tmp/downloads"
    assert is_safe_path("/tmp/downloads/video.mp4", base) is True
    assert is_safe_path("/tmp/downloads/subfolder/video.mp4", base) is True
    assert is_safe_path("/etc/passwd", base) is False
