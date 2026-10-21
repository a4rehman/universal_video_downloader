"""
Cookie management for OmniStream.

Handles loading cookies from browser profiles or cookies.txt files,
and applying them to yt-dlp option dictionaries.
"""

import os
from typing import Any, Dict, Optional

COOKIES_TXT_HELP = (
    "To export cookies: install the 'Get cookies.txt LOCALLY' browser extension, "
    "log in to the site, then click the extension and export cookies. "
    "Save the file and set its path in Settings → Cookies File."
)


def resolve_cookies_file(cookies_file: Optional[str]) -> Optional[str]:
    """Validates and normalises a user-supplied cookies.txt path.

    Returns an absolute path when the file exists and is non-empty, else None.
    An empty/blank setting is treated as "not configured".
    Handles Windows "Copy as Path" quotes.
    """
    if not cookies_file:
        return None
    path = cookies_file.strip().strip("'\"").strip()
    if not path:
        return None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return os.path.abspath(path)
    return None


def apply_cookie_opts(
    ydl_opts: Dict[str, Any],
    cookies_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Applies cookie options to a yt-dlp options dict.

    Priority:
      1. cookies.txt file (most explicit, always works if valid)
      2. Browser cookies (convenient, requires browser to be closed)

    When neither is configured, the dict is returned unchanged (anonymous access).
    """
    resolved_file = resolve_cookies_file(cookies_file)
    if resolved_file:
        ydl_opts['cookiefile'] = resolved_file
        return ydl_opts

    if cookies_browser:
        browser = cookies_browser.strip().lower()
        if browser and browser != "none":
            ydl_opts['cookiesfrombrowser'] = (browser,)

    return ydl_opts


def describe_cookie_source(
    cookies_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> Optional[str]:
    """Returns a short human-readable label for the active cookie source, if any."""
    resolved_file = resolve_cookies_file(cookies_file)
    if resolved_file:
        return f"cookies.txt ({os.path.basename(resolved_file)})"
    if cookies_browser and cookies_browser.lower() != "none":
        return f"browser cookies ({cookies_browser})"
    return None