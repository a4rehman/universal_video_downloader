"""
Shared cookie-option resolution for OmniStream.

Modern Chrome/Edge encrypt cookies with App-Bound Encryption (v20), which
yt-dlp cannot decrypt (see yt-dlp#10927). The reliable workaround is a
Netscape-format cookies.txt exported from the browser. This module centralises
how cookie options are applied so the desktop and web UIs stay in sync.
"""

import os
from typing import Any, Dict, Optional

# Actionable guidance surfaced to users when cookie extraction fails.
COOKIES_TXT_HELP = (
    "To download from Instagram/Facebook you need valid login cookies. "
    "Install a browser extension such as 'Get cookies.txt LOCALLY', open the "
    "site while logged in, export the cookies to a .txt file, then set that "
    "file path in Settings → Cookies File. Close your browser first if you "
    "prefer automatic browser-cookie extraction instead."
)


def resolve_cookies_file(cookies_file: Optional[str]) -> Optional[str]:
    """
    Validates and normalises a user-supplied cookies.txt path.

    Returns an absolute path when the file exists and is non-empty, else None.
    An empty/blank setting is treated as "not configured".
    """
    if not cookies_file:
        return None
    path = os.path.expandvars(str(cookies_file).strip().strip('"'))
    if not path:
        return None
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return None
    return path


def apply_cookie_opts(
    ydl_opts: Dict[str, Any],
    cookies_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Applies cookie options to a yt-dlp options dict.

    Priority: an explicit cookies.txt file wins over browser-cookie extraction,
    because the file works even when the browser is running and bypasses
    App-Bound Encryption. Mutates and returns `ydl_opts` for convenience.
    """
    resolved_file = resolve_cookies_file(cookies_file)
    if resolved_file:
        ydl_opts['cookiefile'] = resolved_file
        return ydl_opts

    if cookies_browser:
        ydl_opts['cookiesfrombrowser'] = (cookies_browser,)
    return ydl_opts


def describe_cookie_source(
    cookies_browser: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> Optional[str]:
    """Returns a short human-readable label for the active cookie source, if any."""
    if resolve_cookies_file(cookies_file):
        return "cookies.txt file"
    if cookies_browser:
        return f"{cookies_browser} browser"
    return None
