"""
Filesystem operations, path handling, size formatting, and temp file management for OmniStream.
"""

import os
import re
import shutil
import tempfile
import time
from typing import Optional, List, Set

# yt-dlp names per-stream intermediates "<title>.f137.mp4" / "<title>.temp.mp4"
# and removes them after a successful merge. When ffmpeg is unavailable (or the
# merge fails) these orphans are left behind, which is what produces the
# "audio and video downloaded separately" symptom.
STREAM_ARTIFACT_RE = re.compile(r"\.(?:f\d+|temp|part-frag\d*|ytdl)\.[A-Za-z0-9]{1,5}$")


def get_default_download_directory() -> str:
    """Returns a safe default download directory path."""
    user_downloads = os.path.expanduser("~/Downloads")
    if os.path.exists(user_downloads) and os.access(user_downloads, os.W_OK):
        return os.path.join(user_downloads, "OmniStream")
    
    current_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(current_dir, exist_ok=True)
    return current_dir


def ensure_directory_exists(path: str) -> str:
    """Creates directory path if it does not exist and returns absolute path."""
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    return abs_path


def format_bytes(bytes_count: Optional[float]) -> str:
    """Formats byte counts into human-readable strings (e.g., '14.2 MB')."""
    if bytes_count is None:
        return "?"
    try:
        b = float(bytes_count)
        if b < 0:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if b < 1024.0 or unit == "TB":
                return f"{b:.1f} {unit}"
            b /= 1024.0
    except Exception:
        pass
    return "0 B"


def is_stream_artifact(filename: str) -> bool:
    """True when a filename is a yt-dlp per-stream intermediate, not a final output file."""
    return bool(STREAM_ARTIFACT_RE.search(os.path.basename(filename)))


def cleanup_stream_artifacts(directory: str, max_age_seconds: int = 0, keep: Optional[Set[str]] = None) -> List[str]:
    """
    Deletes leftover per-stream intermediates ("title.f251.webm", "title.temp.mp4", ...)
    left in `directory` by failed or unmerged downloads.

    `keep` holds absolute paths of files that must never be removed, which lets
    the caller protect a valid final output file.
    Returns the list of removed paths.
    """
    removed: List[str] = []
    if not directory or not os.path.isdir(directory):
        return removed

    keep_resolved = {os.path.abspath(p) for p in (keep or set())}
    now = time.time()

    try:
        entries = os.listdir(directory)
    except Exception:
        return removed

    for name in entries:
        if not is_stream_artifact(name):
            continue

        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue

        abs_path = os.path.abspath(path)
        if abs_path in keep_resolved:
            continue

        try:
            if max_age_seconds > 0 and (now - os.path.getmtime(path)) < max_age_seconds:
                continue
            os.remove(path)
            removed.append(path)
        except Exception:
            pass

    return removed


def cleanup_temporary_files(directory: str, max_age_seconds: int = 3600) -> int:
    """
    Cleans up orphaned temporary download files (.part, .ytdl, .tmp) older than max_age_seconds.
    Returns the count of deleted files.
    """
    cleaned_count = 0
    if not os.path.exists(directory):
        return cleaned_count

    now = time.time()
    try:
        for filename in os.listdir(directory):
            if filename.endswith(('.part', '.ytdl', '.tmp', '.temp')):
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    file_age = now - os.path.getmtime(file_path)
                    if file_age > max_age_seconds:
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except Exception:
                            pass
    except Exception:
        pass
    return cleaned_count
