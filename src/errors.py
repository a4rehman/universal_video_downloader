"""
Structured Error Taxonomy for OmniStream.
Converts technical exceptions into user-friendly diagnostic messages and categories.
"""

from enum import Enum
from typing import Tuple, Dict, Any, Optional


class ErrorCategory(str, Enum):
    INVALID_URL = "INVALID_URL"
    UNSUPPORTED_URL = "UNSUPPORTED_URL"
    EXTRACTOR_ERROR = "EXTRACTOR_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    FORMAT_UNAVAILABLE = "FORMAT_UNAVAILABLE"
    FFMPEG_ERROR = "FFMPEG_ERROR"
    PERMISSION_ERROR = "PERMISSION_ERROR"
    DISK_ERROR = "DISK_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    UNKNOWN = "UNKNOWN"


class OmniStreamError(Exception):
    """Base exception class for OmniStream application errors."""
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.UNKNOWN, technical_details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.category = category
        self.technical_details = technical_details or message


class InvalidURLError(OmniStreamError):
    def __init__(self, message: str = "Invalid URL provided.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.INVALID_URL, details)


class UnsupportedURLError(OmniStreamError):
    def __init__(self, message: str = "This platform or URL format is not supported.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.UNSUPPORTED_URL, details)


class ExtractorError(OmniStreamError):
    def __init__(self, message: str = "Failed to extract media information.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.EXTRACTOR_ERROR, details)


class NetworkError(OmniStreamError):
    def __init__(self, message: str = "Network connection failed. Check your internet connection.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.NETWORK_ERROR, details)


class FormatUnavailableError(OmniStreamError):
    def __init__(self, message: str = "The requested quality or format is not available.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.FORMAT_UNAVAILABLE, details)


class FFmpegError(OmniStreamError):
    def __init__(self, message: str = "FFmpeg processing failed or FFmpeg is missing.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.FFMPEG_ERROR, details)


class PermissionError(OmniStreamError):
    def __init__(self, message: str = "Permission denied when writing file to target path.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.PERMISSION_ERROR, details)


class DiskSpaceError(OmniStreamError):
    def __init__(self, message: str = "Insufficient disk space in target directory.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.DISK_ERROR, details)


class TimeoutError(OmniStreamError):
    def __init__(self, message: str = "Operation timed out.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.TIMEOUT, details)


class RateLimitError(OmniStreamError):
    def __init__(self, message: str = "Rate limited or bot check triggered by target server.", details: Optional[str] = None):
        super().__init__(message, ErrorCategory.RATE_LIMIT, details)


def map_exception_to_user_message(err: Exception) -> Dict[str, Any]:
    """
    Transforms raw technical exceptions into clean user-friendly diagnostic objects.
    Returns dict with keys: category, title, user_message, tip, technical_details.
    """
    if isinstance(err, OmniStreamError):
        cat = err.category
        tech = err.technical_details
        msg = err.message
    else:
        tech = str(err)
        msg = str(err)
        cat = ErrorCategory.UNKNOWN

    raw_lower = tech.lower()

    if cat == ErrorCategory.INVALID_URL or "is not a valid url" in raw_lower or "invalid url" in raw_lower:
        return {
            "category": ErrorCategory.INVALID_URL,
            "title": "Invalid URL",
            "user_message": "The provided URL appears to be incomplete or malformed.",
            "tip": "Double-check the web address in your browser and paste the full link.",
            "technical_details": tech,
        }

    if cat == ErrorCategory.RATE_LIMIT or any(k in raw_lower for k in ("not a bot", "sign in to confirm", "po_token", "login_required", "botcheck")):
        return {
            "category": ErrorCategory.RATE_LIMIT,
            "title": "Bot Check / Rate Limit",
            "user_message": "The platform is blocking requests from datacenter/public IPs or requires bot verification.",
            "tip": "Wait a few minutes, try 'Best Available' format, or select browser cookies in Settings.",
            "technical_details": tech,
        }

    if cat == ErrorCategory.FFMPEG_ERROR or "ffmpeg" in raw_lower or "ffprobe" in raw_lower:
        return {
            "category": ErrorCategory.FFMPEG_ERROR,
            "title": "FFmpeg Issue",
            "user_message": "FFmpeg is required to merge video/audio streams or convert audio formats.",
            "tip": "Ensure FFmpeg is installed on your system or select 'Best Available' format.",
            "technical_details": tech,
        }

    if cat == ErrorCategory.FORMAT_UNAVAILABLE or "requested format is not available" in raw_lower or "format unavailable" in raw_lower:
        return {
            "category": ErrorCategory.FORMAT_UNAVAILABLE,
            "title": "Format Not Available",
            "user_message": "The selected video resolution or audio codec is not offered for this item.",
            "tip": "Try selecting 'Best Available' or choose a different resolution.",
            "technical_details": tech,
        }

    if cat == ErrorCategory.NETWORK_ERROR or any(k in raw_lower for k in ("connection refused", "name resolution", "timed out", "unreachable", "network is unreachable", "no internet")):
        return {
            "category": ErrorCategory.NETWORK_ERROR,
            "title": "Network Error",
            "user_message": "Unable to connect to the target platform server.",
            "tip": "Check your internet connection or proxy settings and try again.",
            "technical_details": tech,
        }

    if cat == ErrorCategory.PERMISSION_ERROR or "permission denied" in raw_lower or "access is denied" in raw_lower:
        return {
            "category": ErrorCategory.PERMISSION_ERROR,
            "title": "Permission Denied",
            "user_message": "Cannot save file to the specified target directory.",
            "tip": "Choose a different output folder in Settings (e.g. your Downloads folder).",
            "technical_details": tech,
        }

    if "could not copy" in raw_lower and "cookie" in raw_lower:
        return {
            "category": ErrorCategory.PERMISSION_ERROR,
            "title": "Browser Cookie Database Locked",
            "user_message": "OmniStream could not read cookies because your browser is currently running and locking its database.",
            "tip": "Close Chrome / Edge completely (including background tasks in the system tray) and try again.",
            "technical_details": tech,
        }

    if (
        "facebook.com/login" in raw_lower
        or (
            "facebook" in raw_lower
            and (
                "login" in raw_lower
                or "unsupported url" in raw_lower
                # yt-dlp's Facebook extractor fails to parse most Reels/watch
                # pages without an authenticated session.
                or "cannot parse data" in raw_lower
            )
        )
    ):
        return {
            "category": ErrorCategory.PERMISSION_ERROR,
            "title": "Facebook Login Required",
            "user_message": "Facebook requires an active sign-in to view this video, profile, or Reels listing.",
            "tip": "Set a cookies.txt file in Settings (export it with a browser extension while logged into Facebook).",
            "technical_details": tech,
        }

    if "tiktok" in raw_lower and (
        "secondary user id" in raw_lower or "ip address is blocked" in raw_lower or "login" in raw_lower
    ):
        return {
            "category": ErrorCategory.PERMISSION_ERROR,
            "title": "TikTok Login Required",
            "user_message": "TikTok blocked this profile or video without a logged-in session.",
            "tip": "Set a cookies.txt file in Settings (export it with a browser extension while logged into TikTok).",
            "technical_details": tech,
        }

    if "unsupported url" in raw_lower or "no suitable extractor" in raw_lower:
        return {
            "category": ErrorCategory.UNSUPPORTED_URL,
            "title": "Unsupported Platform URL",
            "user_message": "yt-dlp could not find a suitable extractor for this web page.",
            "tip": "Verify if the URL points directly to media content or a supported site.",
            "technical_details": tech,
        }

    return {
        "category": cat,
        "title": "Download Error",
        "user_message": msg if len(msg) < 150 else "An unexpected error occurred during processing.",
        "tip": "Try choosing 'Best Available' mode or check the technical log below.",
        "technical_details": tech,
    }
