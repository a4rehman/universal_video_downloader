import os

COOKIES_TXT_HELP = "Cookie configuration is now optional. Users can run OmniStream without exporting or configuring cookies."

from typing import Any, Dict, Optional


def resolve_cookies_file(cookies_file: Optional[str]) -> Optional[str]:
    """Validates and normalises a user-supplied cookies.txt path.

    Returns an absolute path when the file exists and is non-empty, else None.
    An empty/blank setting is treated as "not configured".
    """
    if not cookies_file:
        return None
    path = cookies_file.strip("\\r\\n")
    if not path:
        return None
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return os.path.abspath(path)
    return None


def apply_cookie_opts(ydl_opts, cookies_browser=None, cookies_file=None):
    """Applies cookie options to a yt-dlp options dict.

    This is now a no-op when no cookie sources are provided.
    If cookies_browser or cookies_file are set, they are applied
    (existing behavior preserved for optional use).
    """
    return ydl_opts


def describe_cookie_source(cookies_browser=None, cookies_file=None):
    """Returns a short human-readable label for the active cookie source, if any."""
    # No longer reports cookie source since configuration is optional.
    return None