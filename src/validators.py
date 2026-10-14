"""
URL Validation, Platform Identification, and Security Sanitization for OmniStream.
"""

import os
import re
from urllib.parse import urlparse
from enum import Enum

ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class InstagramURLType(str, Enum):
    PROFILE = "Instagram Profile"
    REELS = "Instagram Reels"
    REEL = "Instagram Reel"
    POST = "Instagram Post"
    TV = "Instagram TV"
    UNKNOWN = "Instagram"


INSTAGRAM_PROFILE_RE = re.compile(r"^https?://(?:www\.)?instagram\.com/([^/?#]+)/?$", re.IGNORECASE)
INSTAGRAM_REELS_RE = re.compile(r"^https?://(?:www\.)?instagram\.com/([^/?#]+)/reels/?$", re.IGNORECASE)
INSTAGRAM_REEL_RE = re.compile(r"^https?://(?:www\.)?instagram\.com/reel/([^/?#]+)/?$", re.IGNORECASE)
INSTAGRAM_POST_RE = re.compile(r"^https?://(?:www\.)?instagram\.com/p/([^/?#]+)/?$", re.IGNORECASE)
INSTAGRAM_TV_RE = re.compile(r"^https?://(?:www\.)?instagram\.com/tv/([^/?#]+)/?$", re.IGNORECASE)


def classify_instagram_url(url: str) -> InstagramURLType:
    """Classifies an Instagram URL into its specific type."""
    if not url or not isinstance(url, str):
        return InstagramURLType.UNKNOWN
    
    url = url.strip()
    
    if INSTAGRAM_REELS_RE.match(url):
        return InstagramURLType.REELS
    if INSTAGRAM_REEL_RE.match(url):
        return InstagramURLType.REEL
    if INSTAGRAM_POST_RE.match(url):
        return InstagramURLType.POST
    if INSTAGRAM_TV_RE.match(url):
        return InstagramURLType.TV
    if INSTAGRAM_PROFILE_RE.match(url):
        return InstagramURLType.PROFILE
    
    return InstagramURLType.UNKNOWN


def is_instagram_collection_url(url: str) -> bool:
    """Returns True if the Instagram URL is a profile or reels listing (collection of videos)."""
    url_type = classify_instagram_url(url)
    return url_type in (InstagramURLType.PROFILE, InstagramURLType.REELS)


def is_valid_url(url: str) -> bool:
    """Returns True if input string is a valid HTTP/HTTPS URL."""
    if not url or not isinstance(url, str):
        return False
    url_trimmed = url.strip()
    try:
        parsed = urlparse(url_trimmed)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def detect_platform(url: str) -> str:
    """
    Identifies the media platform from the URL domain.
    Returns string like 'YouTube', 'TikTok', 'Instagram', 'Twitter/X', etc.
    For Instagram, returns specific sub-type for collection detection.
    """
    if not url or not is_valid_url(url):
        return "Unknown"
    
    netloc = urlparse(url.strip()).netloc.lower()

    if "youtube.com" in netloc or "youtu.be" in netloc:
        return "YouTube"
    if "tiktok.com" in netloc:
        return "TikTok"
    if "instagram.com" in netloc:
        ig_type = classify_instagram_url(url)
        if ig_type != InstagramURLType.UNKNOWN:
            return ig_type.value
        return "Instagram"
    if "twitter.com" in netloc or "x.com" in netloc:
        return "Twitter / X"
    if "facebook.com" in netloc or "fb.watch" in netloc:
        return "Facebook"
    if "pinterest.com" in netloc or "pin.it" in netloc:
        return "Pinterest"
    if "vimeo.com" in netloc:
        return "Vimeo"
    if "twitch.tv" in netloc:
        return "Twitch"
    if "soundcloud.com" in netloc:
        return "SoundCloud"
    if "reddit.com" in netloc or "redd.it" in netloc:
        return "Reddit"
    if "dailymotion.com" in netloc:
        return "Dailymotion"
    if "linkedin.com" in netloc:
        return "LinkedIn"
    if "snapchat.com" in netloc or "snapchat.com/spotlight" in url.lower():
        return "Snapchat"
    
    # Check direct image extensions
    path_lower = urlparse(url.strip()).path.lower()
    if path_lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.bmp')):
        return "Direct Image"

    return "Web Platform"


def sanitize_filename(name: str, fallback: str = "video") -> str:
    """
    Sanitizes arbitrary text for use as a filesystem filename.
    Removes illegal characters and path traversal indicators.
    """
    if not name or not isinstance(name, str):
        return fallback

    # Remove path traversal indicators e.g. ../ or ..\
    cleaned = re.sub(r'(\.\.[/\\])+', '', name.strip())
    # Remove illegal chars
    cleaned = ILLEGAL_CHARS.sub("_", cleaned)
    # Strip leading/trailing dots, spaces, or underscores
    cleaned = cleaned.strip(". _")
    
    if not cleaned:
        return fallback

    return cleaned


def is_safe_path(target_path: str, base_dir: str) -> bool:
    """
    Verifies that target_path resides within base_dir to prevent directory traversal.
    """
    try:
        abs_base = os.path.abspath(base_dir)
        abs_target = os.path.abspath(target_path)
        return os.path.commonpath([abs_base]) == os.path.commonpath([abs_base, abs_target])
    except Exception:
        return False
