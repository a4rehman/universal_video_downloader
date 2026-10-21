"""
Instagram Reels Profile Scraper for OmniStream.

Extracts Reel URLs from Instagram profile/reels listing pages.
Supports both anonymous and authenticated (cookie-based) access.

Instagram requires authentication for most access since late 2023.
When cookies are provided (via cookies.txt or browser profile), extraction
succeeds for public and followed private profiles. Without cookies, most
profiles will block anonymous access.
"""

import os
import re
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse
from src.validators import classify_instagram_url, InstagramURLType


class InstagramReelsScraper:
    """Extracts Reel URLs from Instagram profile/reels pages.

    Supports authenticated (cookie-based) and anonymous extraction.
    Anonymous access is typically blocked by Instagram; provide cookies
    (cookies.txt file or browser profile) for reliable extraction.
    """

    def __init__(
        self,
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        *args,
        **kwargs,
    ):
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.last_error = None

    # ------------------------------------------------------------------
    # Reel extraction (with optional cookies and Playwright support)
    # ------------------------------------------------------------------
    def extract_reel_urls(self, url: str, max_reels: int = 50) -> List[str]:
        """
        Extract Reel URLs from an Instagram profile or reels listing page.

        Args:
            url: Instagram profile URL or reels listing URL
            max_reels: Maximum number of Reels to extract

        Returns:
            List of Reel URLs (may be empty if access is blocked)
        """
        items = self.extract_reel_items(url, max_reels)
        return [item["url"] for item in items]

    def extract_reel_items(self, url: str, max_reels: int = 50) -> List[Dict[str, Any]]:
        """
        Extract Reel items (URL, thumbnail, title) from an Instagram profile or reels page.

        Supports authenticated (cookies) access, headless Playwright extraction for
        public profiles, and HTML parsing fallbacks.
        """
        url_type = classify_instagram_url(url)
        if url_type not in (InstagramURLType.PROFILE, InstagramURLType.REELS):
            raise ValueError(f"URL must be an Instagram profile or reels listing, got: {url}")

        # 1. If cookies are explicitly provided, attempt yt-dlp first
        if self.cookies_browser or self.cookies_file:
            norm_url = url
            if url_type == InstagramURLType.REELS:
                match = re.search(r"instagram\.com/([^/?#]+)/reels/?", url)
                if match:
                    norm_url = f"https://www.instagram.com/{match.group(1)}/"
            yt_urls = self._extract_with_yt_dlp(norm_url, max_reels)
            if yt_urls:
                return [
                    {
                        "url": u,
                        "thumbnail": None,
                        "title": f"Reel ({u.strip('/').split('/')[-1]})",
                    }
                    for u in yt_urls[:max_reels]
                ]

        # 2. Attempt Playwright headless browser extraction (handles JS rendering for public profiles)
        pw_items = self._extract_with_playwright(url, max_reels)
        if pw_items:
            return pw_items[:max_reels]

        # 3. Attempt yt-dlp without cookies (in case yt-dlp extractor works)
        norm_url = url
        if url_type == InstagramURLType.REELS:
            match = re.search(r"instagram\.com/([^/?#]+)/reels/?", url)
            if match:
                norm_url = f"https://www.instagram.com/{match.group(1)}/"
        yt_urls = self._extract_with_yt_dlp(norm_url, max_reels)
        if yt_urls:
            return [
                {
                    "url": u,
                    "thumbnail": None,
                    "title": f"Reel ({u.strip('/').split('/')[-1]})",
                }
                for u in yt_urls[:max_reels]
            ]

        # 4. Fallback: try HTML parsing (cookie-free, best-effort)
        html_urls = self._extract_from_html_no_cookies(norm_url, max_reels)
        if html_urls:
            return [
                {
                    "url": u,
                    "thumbnail": None,
                    "title": f"Reel ({u.strip('/').split('/')[-1]})",
                }
                for u in html_urls[:max_reels]
            ]

        # Access blocked — return empty list with a clear last_error.
        if self.cookies_browser or self.cookies_file:
            self.last_error = (
                "Instagram blocked this extraction even with cookies. "
                "The profile may be private, rate-limited, or the cookies may be expired. "
                "Try closing your browser completely before using browser cookies, "
                "or re-export a fresh cookies.txt and retry."
            )
        else:
            self.last_error = (
                "Instagram requires authentication or JavaScript to access profiles and reels collections. "
                "Set a browser cookie profile in Settings -> Browser Cookie Profile, "
                "or export a cookies.txt file while logged into Instagram and set its path in Settings. "
                "Alternatively, paste the direct URL of an individual Reel."
            )
        return []

    # ----- Playwright headless browser extraction -----
    def _extract_with_playwright(self, url: str, max_reels: int) -> List[Dict[str, Any]]:
        """Extract reels using Playwright headless browser."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []

        match = re.search(r"instagram\.com/([^/?#]+)", url)
        if not match:
            return []
        username = match.group(1).replace("reels", "").strip("/")
        if not username:
            return []

        target_url = f"https://www.instagram.com/{username}/reels/"
        items: List[Dict[str, Any]] = []

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                    ),
                )
                try:
                    page.goto(target_url, wait_until="networkidle", timeout=30000)
                except Exception:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(1000)

                # Instagram lazy loads reels on scroll
                max_scrolls = max(2, min(15, (max_reels // 6) + 1))
                seen_hrefs = set()
                for _ in range(max_scrolls):
                    page.mouse.wheel(0, 1000)
                    page.wait_for_timeout(1500)

                    scraped = page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll('a[href*="/reel/"]'));
                        return anchors.map(a => {
                            let href = a.href;
                            if (href.includes('?')) href = href.split('?')[0];
                            if (!href.endsWith('/')) href += '/';

                            let thumb = null;
                            const img = a.querySelector('img');
                            if (img && img.src) {
                                thumb = img.src;
                            } else {
                                const bgDiv = a.querySelector('div[style*="background-image"]');
                                if (bgDiv) {
                                    const match = bgDiv.style.backgroundImage.match(/url\\(["']?(.*?)["']?\\)/);
                                    if (match) thumb = match[1];
                                }
                            }

                            const parts = href.split('/').filter(Boolean);
                            const shortcode = parts[parts.length - 1];

                            return {
                                url: href,
                                thumbnail: thumb,
                                title: 'Reel (' + shortcode + ')'
                            };
                        });
                    }""")

                    for item in scraped:
                        h = item.get("url")
                        if h and h not in seen_hrefs:
                            seen_hrefs.add(h)
                            items.append(item)

                    if len(items) >= max_reels:
                        break

                browser.close()
        except Exception as e:
            self.last_error = str(e)

        return items[:max_reels]

    # ----- yt-dlp extraction (with optional cookies) -----
    def _extract_with_yt_dlp(self, url: str, max_reels: int) -> List[str]:
        import yt_dlp
        from src.cookies import apply_cookie_opts

        ydl_opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'playlistend': max_reels,
            'socket_timeout': 30,
        }

        # Apply cookies when configured — Instagram almost always requires auth
        apply_cookie_opts(ydl_opts, self.cookies_browser, self.cookies_file)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.last_error = str(e)
            info = None

        reel_urls: List[str] = []
        if info:
            for entry in (info.get('entries') or []):
                if not entry or not isinstance(entry, dict):
                    continue
                reel_url = entry.get('webpage_url') or entry.get('original_url') or entry.get('url')
                if reel_url and isinstance(reel_url, str) and (
                    '/reel/' in reel_url or '/p/' in reel_url
                ):
                    reel_urls.append(reel_url)
                    if len(reel_urls) >= max_reels:
                        break

        return reel_urls

    # ----- HTML fallback (cookie-free, best-effort) -----
    def _extract_from_html_no_cookies(self, url: str, max_reels: int) -> List[str]:
        """Fallback: extract Reel URLs by parsing profile HTML without cookies.

        Instagram usually blocks anonymous HTML requests. When blocked, returns
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

            try:
                from bs4 import BeautifulSoup
            except Exception:
                return reel_urls

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 1. Anchors that link directly to a reel.
            for link in soup.find_all('a', href=True):
                href = link['href']
                if '/reel/' in href or '/p/' in href:
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
                    if '/reel/' in value or '/p/' in value:
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
    cookies_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """Extract Reel URLs from an Instagram profile.

    Args:
        url: Instagram profile URL or reels listing URL
        max_reels: Maximum number of Reels to extract
        cookies_browser: Browser name to extract cookies from (e.g. 'chrome', 'firefox')
        cookies_file: Path to a cookies.txt file

    Returns:
        Tuple of (reel_urls, error_message). error_message is None on success.
    """
    scraper = InstagramReelsScraper(
        cookies_browser=cookies_browser,
        cookies_file=cookies_file,
    )
    reel_urls = scraper.extract_reel_urls(url, max_reels=max_reels)
    return reel_urls, scraper.last_error