"""
Instagram Reels Profile Scraper for OmniStream.

Extracts Reel URLs from Instagram profile/reels listing pages.
Works without requiring cookies when anonymous access is supported.
Fallbacks to HTML parsing when yt-dlp's extractor fails.

Note: Instagram often restricts anonymous access. When blocked, the scraper
returns an empty list rather than requiring users to export cookies or
configure browser cookie sources.
"""

import os
import re
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
from src.validators import classify_instagram_url, InstagramURLType


class InstagramReelsScraper:
    """Extracts Reel URLs from Instagram profile/reels pages.

    Supports anonymous extraction when Instagram allows it. When anonymous
    access is blocked (login required, private account, rate limited), the
    scraper returns an empty list rather than forcing users to configure
    cookies or browser cookie sources.
    """

    def __init__(self):
        self.cookie_file = None
        self.last_error = None

    # ------------------------------------------------------------------
    # Reel extraction (cookie-free attempt first)
    # ------------------------------------------------------------------
    def extract_reel_urls(self, url: str, max_reels: int = 50) -> List[str]:
        """
        Extract Reel URLs from an Instagram profile or reels listing page.

        Args:
            url: Instagram profile URL or reels listing URL
            max_reels: Maximum number of Reels to extract

        Returns:
            List of Reel URLs (may be empty if anonymous access is blocked)
        """
        url_type = classify_instagram_url(url)
        if url_type not in (InstagramURLType.PROFILE, InstagramURLType.REELS):
            raise ValueError(f"URL must be an Instagram profile or reels listing, got: {url}")

        # Normalize /reels/ listing to the bare profile URL.
        if url_type == InstagramURLType.REELS:
            match = re.search(r"instagram\.com/([^/?#]+)/reels/?", url)
            if match:
                url = f"https://www.instagram.com/{match.group(1)}/"

        # Attempt yt-dlp extraction without cookies first.
        reel_urls = self._extract_with_yt_dlp(url, max_reels)

        if reel_urls:
            return reel_urls[:max_reels]

        # Fallback: try HTML parsing without cookies (best-effort).
        html_urls = self._extract_from_html_no_cookies(url, max_reels)
        if html_urls:
            return html_urls[:max_reels]

        # Anonymous access blocked — return empty list with a clear last_error.
        self.last_error = (
            "Instagram blocked this extraction. The profile or reels listing "
            "may require login, may be private, or may have rate-limited access. "
            "Try pasting individual Reel URLs instead."
        )
        return []

    # ----- yt-dlp extraction (cookie-free) -----
    def _extract_with_yt_dlp(self, url: str, max_reels: int) -> List[str]:
        import yt_dlp

        ydl_opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'playlistend': max_reels,
            # Do NOT set cookiefile — run anonymously.
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception:
            info = None

        reel_urls: List[str] = []
        if info:
            for entry in (info.get('entries') or []):
                if not entry or not isinstance(entry, dict):
                    continue
                reel_url = entry.get('webpage_url') or entry.get('original_url') or entry.get('url')
                if reel_url and isinstance(reel_url, str) and '/reel/' in reel_url:
                    reel_urls.append(reel_url)
                    if len(reel_urls) >= max_reels:
                        break

        return reel_urls

    # ----- HTML fallback (cookie-free, best-effort) -----
    def _extract_from_html_no_cookies(self, url: str, max_reels: int) -> List[str]:
        """Fallback: extract Reel URLs by parsing profile HTML without cookies.

        Instagram may block anonymous HTML requests too. When blocked, returns
        an empty list rather than forcing cookie configuration.
        """
        import requests

        reel_urls: List[str] = []
        try:
            headers = {
                'User-Agent': (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }

            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return reel_urls

            # Only attempt parsing if we get a successful response.
            # Instagram may return 200 but restrict content; we handle that below.
            try:
                from bs4 import BeautifulSoup
            except Exception:
                return reel_urls

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 1. Anchors that link directly to a reel.
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/reel/' in href:
                    if href.startswith('/'):
                        href = 'https://www.instagram.com' + href
                    if href not in reel_urls:
                        reel_urls.append(href)

            # 2. Embedded JSON blobs.
            for script in soup.find_all('script', type='application/json'):
                try:
                    data = json.loads(script.string)
                    reel_urls.extend(self._extract_urls_from_json(data))
                except Exception:
                    pass

            # 3. window._sharedData (legacy pages).
            for script in soup.find_all('script'):
                if script.string and 'window._sharedData' in script.string:
                    try:
                        json_str = script.string.split('window._sharedData = ')[1].split(';')[0]
                        data = json.loads(json_str)
                        reel_urls.extend(self._extract_urls_from_json(data))
                    except Exception:
                        pass

        except Exception as e:
            # Log silently; don't force cookie configuration.
            self.last_error = f"HTML extraction failed: {e}"

        # Deduplicate while preserving order.
        unique_urls: List[str] = []
        seen = set()
        for u in reel_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
                if len(unique_urls) >= max_reels:
                    break
        return unique_urls

    @staticmethod
    def _extract_urls_from_json(data: Any) -> List[str]:
        """Recursively extract Reel URLs from nested JSON data."""
        urls: List[str] = []
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ('url', 'webpage_url', 'permalink') and isinstance(value, str):
                    if '/reel/' in value:
                        urls.append(value)
                elif isinstance(value, (dict, list)):
                    urls.extend(InstagramReelsScraper._extract_urls_from_json(value))
        elif isinstance(data, list):
            for item in data:
                urls.extend(InstagramReelsScraper._extract_urls_from_json(item))
        return urls


def extract_instagram_reels_from_profile(
    url: str,
    max_reels: int = 50,
) -> List[str]:
    """Convenience function to extract Reel URLs from an Instagram profile.

    This is the cookie-free entry point. No browser selection or cookies.txt
    path is required. When Instagram blocks anonymous access, an empty list
    is returned with a clear last_error message on the scraper instance.

    Args:
        url: Instagram profile URL or reels listing URL
        max_reels: Maximum number of Reels to extract

    Returns:
        List of Reel URLs (may be empty if access is blocked)
    """
    scraper = InstagramReelsScraper()
    return scraper.extract_reel_urls(url, max_reels=max_reels)