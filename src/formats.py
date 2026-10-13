"""
Format Selection, Resolution Mapping, and yt-dlp Format Builder for OmniStream.
"""

from typing import List, Dict, Any, Optional

RESOLUTION_PRESETS = [
    "Best Available",
    "4K (2160p)",
    "1440p",
    "1080p",
    "720p",
    "480p",
    "360p",
]

AUDIO_CODECS = ["MP3", "M4A", "WAV", "Opus"]
AUDIO_QUALITIES = ["320 kbps", "256 kbps", "192 kbps", "128 kbps"]


def filter_available_resolutions(raw_formats: List[Dict[str, Any]]) -> List[str]:
    """
    Extracts distinct available video heights from raw yt-dlp format dictionaries
    and maps them to friendly resolution preset choices.
    """
    if not raw_formats:
        return RESOLUTION_PRESETS

    heights = set()
    for f in raw_formats:
        h = f.get("height")
        if h and isinstance(h, int) and h > 0:
            heights.add(h)

    if not heights:
        return ["Best Available"]

    available = ["Best Available"]
    if any(h >= 2160 for h in heights):
        available.append("4K (2160p)")
    if any(1440 <= h < 2160 for h in heights):
        available.append("1440p")
    if any(1080 <= h < 1440 for h in heights):
        available.append("1080p")
    if any(720 <= h < 1080 for h in heights):
        available.append("720p")
    if any(480 <= h < 720 for h in heights):
        available.append("480p")
    if any(360 <= h < 480 for h in heights):
        available.append("360p")

    return available


def get_resolution_height_target(quality_key: str) -> Optional[int]:
    """Maps friendly resolution label to numeric pixel height ceiling."""
    if "4K" in quality_key or "2160" in quality_key:
        return 2160
    if "1440" in quality_key:
        return 1440
    if "1080" in quality_key:
        return 1080
    if "720" in quality_key:
        return 720
    if "480" in quality_key:
        return 480
    if "360" in quality_key:
        return 360
    return None


def build_ytdlp_format_string(media_type: str, quality_key: str, raw_format_id: Optional[str] = None) -> str:
    """
    Constructs internal yt-dlp format selector string.
    """
    if raw_format_id:
        return raw_format_id

    if media_type == "Audio":
        return "bestaudio/best"

    if media_type == "Image":
        return "best"

    # Video mode
    if not quality_key or quality_key == "Best Available":
        return "bestvideo+bestaudio/best"

    height_target = get_resolution_height_target(quality_key)
    if height_target:
        return (
            f"bestvideo[height<={height_target}]+bestaudio/"
            f"best[height<={height_target}]/best"
        )

    return "bestvideo+bestaudio/best"


def parse_raw_formats(raw_formats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parses and formats raw format lists for advanced format inspection UI.
    """
    parsed = []
    if not raw_formats:
        return parsed

    for f in raw_formats:
        fmt_id = f.get("format_id", "")
        ext = f.get("ext", "")
        resolution = f.get("resolution") or (f"{f.get('width')}x{f.get('height')}" if f.get("height") else "audio only")
        note = f.get("format_note", "")
        fps = f.get("fps")
        fps_str = f" @ {fps}fps" if fps else ""
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        filesize = f.get("filesize") or f.get("filesize_approx")
        
        display_label = f"[{fmt_id}] {ext} - {resolution}{fps_str} ({note or vcodec})"
        
        parsed.append({
            "format_id": fmt_id,
            "ext": ext,
            "resolution": resolution,
            "display_label": display_label,
            "vcodec": vcodec,
            "acodec": acodec,
            "filesize": filesize,
        })
    return parsed
