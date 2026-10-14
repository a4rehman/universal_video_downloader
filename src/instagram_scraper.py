"""
Instagram Reels Profile Scraper for OmniStream.

Extracts Reel URLs from Instagram profile/reels listing pages using cookies.
Works around yt-dlp's broken Instagram profile extractor.

Cookie sources, in priority order:
  1. An explicit cookies.txt file (Netscape format). This is the reliable path
     for modern Chrome/Edge, which encrypt cookies with App-Bound Encryption
     (v20) that yt-dlp cannot decrypt (yt-dlp#10927). Export it with a browser
     extension such as "Get cookies.txt LOCALLY" while logged in.
  2. yt-dlp's built-in browser-cookie extraction. Works for Firefox and for
     Chromium builds that still use the legacy DPAPI scheme.

We deliberately do NOT launch the browser or mutate the real profile to obtain
cookies. Forcing decryption against App-Bound Encryption is unreliable and, as
observed during development, can wipe the browser's cookie database.
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
from src.cookies import resolve_cookies_file, COOKIES_TXT_HELP


class InstagramReelsScraper:
    """Extracts Reel URLs from Instagram profile/reels pages using cookies."""

    def __init__(
        self,
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
    ):
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.cookie_file = None          # temp file we created (cleaned up)
        self._owns_cookie_file = False   # True when we generated it
        self.last_error = None

    # ------------------------------------------------------------------
    # Cookie acquisition
    # ------------------------------------------------------------------
    def _get_cookie_file(self) -> Optional[str]:
        """
        Resolves a cookie file to feed to yt-dlp / the HTML fallback.

        Returns a filesystem path, or None when no usable cookie source exists
        (in which case `self.last_error` explains why).
        """
        # 1. User-supplied cookies.txt wins — works regardless of ABE / running browser.
        resolved = resolve_cookies_file(self.cookies_file)
        if resolved:
            self.cookie_file = resolved
            self._owns_cookie_file = False
            return resolved

        if not self.cookies_browser:
            self.last_error = COOKIES_TXT_HELP
            return None

        # 2. yt-dlp browser-cookie extraction (Firefox / legacy Chromium).
        try:
            from yt_dlp.cookies import extract_cookies_from_browser

            jar = extract_cookies_from_browser(
                browser_name=self.cookies_browser,
                profile=None,
            )
            if jar:
                temp_file = os.path.join(
                    tempfile.gettempdir(), f"omnistream_ig_cookies_{os.getpid()}.txt"
                )
                ig_count = 0
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write("# Netscape HTTP Cookie File\n")
                    for cookie in jar:
                        domain = cookie.domain
                        flag = "TRUE" if domain.startswith(".") else "FALSE"
                        path = cookie.path or "/"
                        secure = "TRUE" if cookie.secure else "FALSE"
                        expiry = str(int(cookie.expires)) if cookie.expires else "0"
                        f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{expiry}\t{cookie.name}\t{cookie.value}\n")
                        if 'instagram' in domain:
                            ig_count += 1

                if ig_count > 0:
                    self.cookie_file = temp_file
                    self._owns_cookie_file = True
                    return temp_file

                # Cookies extracted but none for Instagram — not useful here.
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
                self.last_error = (
                    f"No Instagram cookies found in '{self.cookies_browser}'. "
                    f"Make sure you are logged into instagram.com in that browser. " + COOKIES_TXT_HELP
                )
                return None

            self.last_error = (
                f"Could not read cookies from '{self.cookies_browser}'. "
                f"Close the browser completely and retry, or use a cookies.txt file. " + COOKIES_TXT_HELP
            )
            return None

        except Exception as e:
            # Common with modern Chrome/Edge: App-Bound Encryption blocks decryption.
            self.last_error = (
                f"Browser-cookie extraction failed ({e}). "
                f"Modern Chrome/Edge encrypt cookies in a way yt-dlp cannot read. " + COOKIES_TXT_HELP
            )
            return None

    def _cleanup_cookie_file(self):
        """Removes the temp cookie file we generated (never a user-supplied one)."""
        if self._owns_cookie_file and self.cookie_file and os.path.exists(self.cookie_file):
            try:
                os.remove(self.cookie_file)
            except Exception:
                pass
        self.cookie_file = None
        self._owns_cookie_file = False

    # ------------------------------------------------------------------
    # Reel extraction
    # ------------------------------------------------------------------
    def extract_reel_urls(self, url: str, max_reels: int = 50) -> List[str]:
        """
        Extract Reel URLs from an Instagram profile or reels listing page.

        Args:
            url: Instagram profile URL or reels listing URL
            max_reels: Maximum number of Reels to extract

        Returns:
            List of Reel URLs
        """
        url_type = classify_instagram_url(url)
        if url_type not in (InstagramURLType.PROFILE, InstagramURLType.REELS):
            raise ValueError(f"URL must be an Instagram profile or reels listing, got: {url}")

        # Normalize /reels/ listing to the bare profile URL.
        if url_type == InstagramURLType.REELS:
            match = re.search(r"instagram\.com/([^/?#]+)/reels/?", url)
            if match:
                url = f"https://www.instagram.com/{match.group(1)}/"

        cookie_file = self._get_cookie_file()
        if not cookie_file:
            detail = f" Details: {self.last_error}" if self.last_error else ""
            raise RuntimeError(
                "No usable cookies available for Instagram. " + COOKIES_TXT_HELP + detail
            )

        try:
            # Prefer yt-dlp's Instagram extractor with the resolved cookies.
            import yt_dlp

            ydl_opts = {
                'cookiefile': cookie_file,
                'extract_flat': 'in_playlist',
                'skip_download': True,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'playlistend': max_reels,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as e:
                # yt-dlp's profile extractor is often broken; fall through to HTML.
                info = None

            reel_urls: List[str] = []
            if info:
                for entry in (info.get('entries') or []):
                    if not entry or not isinstance(entry, dict):
                        continue
                    # Prefer the full webpage URL; a flat entry's `url` may be a bare id.
                    reel_url = entry.get('webpage_url') or entry.get('original_url') or entry.get('url')
                    if reel_url and isinstance(reel_url, str) and reel_url.startswith('http') and '/reel/' in reel_url:
                        reel_urls.append(reel_url)
                        if len(reel_urls) >= max_reels:
                            break

            if reel_urls:
                return reel_urls[:max_reels]

            # Fallback: parse the profile HTML directly with the same cookies.
            return self._extract_from_html(url, cookie_file, max_reels)
        finally:
            self._cleanup_cookie_file()

    # ------------------------------------------------------------------
    # HTML fallback
    # ------------------------------------------------------------------
    def _extract_from_html(self, url: str, cookie_file: str, max_reels: int) -> List[str]:
        """Fallback: extract Reel URLs by parsing the profile HTML with cookies."""
        import requests
        from bs4 import BeautifulSoup

        reel_urls: List[str] = []
        try:
            cookie_jar = requests.cookies.RequestsCookieJar()
            with open(cookie_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        domain, _flag, path, _secure, _expiry, name, value = parts[:7]
                        cookie_jar.set(name, value, domain=domain, path=path)

            headers = {
                'User-Agent': (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }

            resp = requests.get(url, headers=headers, cookies=cookie_jar, timeout=30)
            if resp.status_code != 200:
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
            print(f"HTML extraction failed: {e}")

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
    cookies_browser: Optional[str] = None,
    max_reels: int = 50,
    cookies_file: Optional[str] = None,
) -> List[str]:
    """
    Convenience function to extract Reel URLs from an Instagram profile.

    Args:
        url: Instagram profile URL or reels listing URL
        cookies_browser: Browser to extract cookies from ('chrome', 'edge', 'firefox', 'brave')
        max_reels: Maximum number of Reels to extract
        cookies_file: Optional path to a Netscape-format cookies.txt (preferred for Chrome/Edge)

    Returns:
        List of Reel URLs
    """
    scraper = InstagramReelsScraper(cookies_browser=cookies_browser, cookies_file=cookies_file)
    return scraper.extract_reel_urls(url, max_reels=max_reels)
